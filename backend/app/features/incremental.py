from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .frames import FeatureAvailability, FeatureFrame, FeatureFrameSet, FeatureSnapshot, FeatureValue, NormalizedBar
from .key import make_feature_key
from .planner import FeaturePlan
from .registry import FeatureRegistry, registry
from .spec import FeatureNamespace, FeatureScope, FeatureSpec


class IncrementalFeatureEngineError(ValueError):
    """Raised when incremental feature updates cannot proceed safely."""


class UnsupportedBatchFeatureError(ValueError):
    """Raised when a feature kind/namespace/scope is not implemented by the canonical engine."""


SUPPORTED_BATCH_KINDS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "sma",
        "ema",
        "rsi",
        "atr",
        "vwap",
        "highest",
        "lowest",
        "down_streak",
        "ibs",
        "roc",
        "swing_high",
        "swing_low",
        "fvg_up",
        "fvg_down",
        "supertrend",
        "tenkan_sen",
        "kijun_sen",
        "senkou_a",
        "senkou_b",
        "chikou_span",
        "macd",
        "support",
        "resistance",
    }
)


_ET_ZONE = ZoneInfo("America/New_York")


def _et_session_date(timestamp: datetime) -> date:
    return timestamp.astimezone(_ET_ZONE).date()


@dataclass
class _FeatureState:
    spec: FeatureSpec
    feature_key: str
    warmup: int
    index: int = -1

    # SMA rolling window
    source_window: deque[float] = field(default_factory=deque)
    rolling_sum: float = 0.0

    # EMA running value
    previous_ema: float | None = None

    # highest / lowest monotonic deque
    monotonic_window: deque[tuple[int, float]] = field(default_factory=deque)

    # Output ringbuffer for `lookback` shift
    base_history: deque[FeatureValue] = field(default_factory=deque)

    # RSI Wilder state
    rsi_previous_close: float | None = None
    rsi_gain_sum: float = 0.0
    rsi_loss_sum: float = 0.0
    rsi_avg_gain: float | None = None
    rsi_avg_loss: float | None = None
    rsi_change_count: int = 0

    # ATR Wilder state
    atr_previous_close: float | None = None
    atr_tr_sum: float = 0.0
    atr_avg: float | None = None

    # VWAP session-bucketed state
    vwap_session_key: date | None = None
    vwap_cum_pv: float = 0.0
    vwap_cum_v: float = 0.0

    # down_streak running counter
    streak_previous_close: float | None = None
    streak_count: int = 0

    # ROC: rolling close history of size length+1
    roc_close_history: deque[float] = field(default_factory=deque)

    # Swing high/low pivot ringbuffer of size 2*lookback+1 (high or low values)
    swing_window: deque[float] = field(default_factory=deque)

    # FVG up/down: 3-bar trailing buffer of (high, low) tuples
    fvg_history: deque[tuple[float, float]] = field(default_factory=deque)

    # Supertrend state — composes ATR Wilder state above; trend line + direction
    supertrend_value: float | None = None
    supertrend_direction: int = 1  # 1 = up, -1 = down
    supertrend_upper: float | None = None
    supertrend_lower: float | None = None

    # Ichimoku Tenkan/Kijun/Senkou-B share monotonic windows for highest+lowest
    ichimoku_high_window: deque[tuple[int, float]] = field(default_factory=deque)
    ichimoku_low_window: deque[tuple[int, float]] = field(default_factory=deque)
    # Senkou-A reuses Tenkan + Kijun running values
    ichimoku_tenkan_high: deque[tuple[int, float]] = field(default_factory=deque)
    ichimoku_tenkan_low: deque[tuple[int, float]] = field(default_factory=deque)
    ichimoku_kijun_high: deque[tuple[int, float]] = field(default_factory=deque)
    ichimoku_kijun_low: deque[tuple[int, float]] = field(default_factory=deque)

    # Chikou span: history of close values
    chikou_close_history: deque[float] = field(default_factory=deque)

    # MACD: three EMA states (fast / slow / signal-of-line)
    macd_fast_ema: float | None = None
    macd_slow_ema: float | None = None
    macd_signal_ema: float | None = None

    # Support/Resistance: pivot history (timestamp_index, value)
    sr_pivot_low_history: list[tuple[int, float]] = field(default_factory=list)
    sr_pivot_high_history: list[tuple[int, float]] = field(default_factory=list)
    sr_low_window: deque[float] = field(default_factory=deque)
    sr_high_window: deque[float] = field(default_factory=deque)
    sr_close_history: deque[float] = field(default_factory=deque)

    def update(self, bar: NormalizedBar) -> FeatureValue:
        self.index += 1
        base_value = self._compute_base_value(bar)
        self.base_history.append(base_value)
        while len(self.base_history) > self.spec.lookback + 1:
            self.base_history.popleft()
        if len(self.base_history) <= self.spec.lookback:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return self.base_history[-(self.spec.lookback + 1)]

    def _compute_base_value(self, bar: NormalizedBar) -> FeatureValue:
        if self.spec.kind in {"open", "high", "low", "close", "volume"}:
            return FeatureValue(value=self._source_value(bar), availability=FeatureAvailability.AVAILABLE)
        if self.spec.kind == "sma":
            return self._update_sma(bar)
        if self.spec.kind == "ema":
            return self._update_ema(bar)
        if self.spec.kind == "rsi":
            return self._update_rsi(bar)
        if self.spec.kind == "atr":
            return self._update_atr(bar)
        if self.spec.kind == "vwap":
            return self._update_vwap(bar)
        if self.spec.kind == "highest":
            return self._update_extreme(bar, highest=True)
        if self.spec.kind == "lowest":
            return self._update_extreme(bar, highest=False)
        if self.spec.kind == "down_streak":
            return self._update_down_streak(bar)
        if self.spec.kind == "ibs":
            return self._update_ibs(bar)
        if self.spec.kind == "roc":
            return self._update_roc(bar)
        if self.spec.kind == "swing_high":
            return self._update_swing(bar, highest=True)
        if self.spec.kind == "swing_low":
            return self._update_swing(bar, highest=False)
        if self.spec.kind == "fvg_up":
            return self._update_fvg(bar, up=True)
        if self.spec.kind == "fvg_down":
            return self._update_fvg(bar, up=False)
        if self.spec.kind == "supertrend":
            return self._update_supertrend(bar)
        if self.spec.kind == "tenkan_sen":
            return self._update_ichimoku_double(bar, length_param="length")
        if self.spec.kind == "kijun_sen":
            return self._update_ichimoku_double(bar, length_param="length")
        if self.spec.kind == "senkou_a":
            return self._update_senkou_a(bar)
        if self.spec.kind == "senkou_b":
            return self._update_ichimoku_double(bar, length_param="length")
        if self.spec.kind == "chikou_span":
            return self._update_chikou(bar)
        if self.spec.kind == "macd":
            return self._update_macd(bar)
        if self.spec.kind == "support":
            return self._update_support_resistance(bar, want_resistance=False)
        if self.spec.kind == "resistance":
            return self._update_support_resistance(bar, want_resistance=True)
        raise UnsupportedBatchFeatureError(f"unsupported feature '{self.spec.kind}'")

    def _source_value(self, bar: NormalizedBar) -> float:
        source = str(self.spec.params.get("source", self.spec.source))
        if source not in {"open", "high", "low", "close", "volume"}:
            raise UnsupportedBatchFeatureError(f"unsupported source '{source}' for feature '{self.spec.kind}'")
        return float(getattr(bar, source))

    def _update_sma(self, bar: NormalizedBar) -> FeatureValue:
        length = int(self.spec.params["length"])
        value = self._source_value(bar)
        self.source_window.append(value)
        self.rolling_sum += value
        if len(self.source_window) > length:
            self.rolling_sum -= self.source_window.popleft()
        if len(self.source_window) < length:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return FeatureValue(value=self.rolling_sum / length, availability=FeatureAvailability.AVAILABLE)

    def _update_ema(self, bar: NormalizedBar) -> FeatureValue:
        length = int(self.spec.params["length"])
        alpha = 2 / (length + 1)
        source_value = self._source_value(bar)
        self.previous_ema = (
            source_value
            if self.previous_ema is None
            else alpha * source_value + (1 - alpha) * self.previous_ema
        )
        if self.index < self.warmup - 1:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return FeatureValue(value=self.previous_ema, availability=FeatureAvailability.AVAILABLE)

    def _update_rsi(self, bar: NormalizedBar) -> FeatureValue:
        length = int(self.spec.params["length"])
        close = self._source_value(bar)
        if self.rsi_previous_close is None:
            self.rsi_previous_close = close
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        change = close - self.rsi_previous_close
        self.rsi_previous_close = close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        self.rsi_change_count += 1
        if self.rsi_change_count <= length:
            self.rsi_gain_sum += gain
            self.rsi_loss_sum += loss
            if self.rsi_change_count < length:
                return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
            self.rsi_avg_gain = self.rsi_gain_sum / length
            self.rsi_avg_loss = self.rsi_loss_sum / length
        else:
            assert self.rsi_avg_gain is not None and self.rsi_avg_loss is not None
            self.rsi_avg_gain = (self.rsi_avg_gain * (length - 1) + gain) / length
            self.rsi_avg_loss = (self.rsi_avg_loss * (length - 1) + loss) / length
        rsi_value = (
            100.0
            if self.rsi_avg_loss == 0.0
            else 100.0 - 100.0 / (1.0 + self.rsi_avg_gain / self.rsi_avg_loss)
        )
        if self.index < self.warmup - 1:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return FeatureValue(value=rsi_value, availability=FeatureAvailability.AVAILABLE)

    def _update_atr(self, bar: NormalizedBar) -> FeatureValue:
        length = int(self.spec.params["length"])
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        if self.atr_previous_close is None:
            tr = high - low
        else:
            tr = max(
                high - low,
                abs(high - self.atr_previous_close),
                abs(low - self.atr_previous_close),
            )
        self.atr_previous_close = close
        if self.index < length:
            self.atr_tr_sum += tr
            if self.index < length - 1:
                return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
            self.atr_avg = self.atr_tr_sum / length
        else:
            assert self.atr_avg is not None
            self.atr_avg = (self.atr_avg * (length - 1) + tr) / length
        if self.index < self.warmup - 1:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return FeatureValue(value=self.atr_avg, availability=FeatureAvailability.AVAILABLE)

    def _update_vwap(self, bar: NormalizedBar) -> FeatureValue:
        session = str(self.spec.params.get("session", "regular"))
        if session != "regular":
            raise UnsupportedBatchFeatureError(
                f"vwap session '{session}' is not supported; only 'regular' is implemented"
            )
        bucket = _et_session_date(bar.timestamp)
        if self.vwap_session_key != bucket:
            self.vwap_cum_pv = 0.0
            self.vwap_cum_v = 0.0
            self.vwap_session_key = bucket
        typical = (float(bar.high) + float(bar.low) + float(bar.close)) / 3.0
        volume = float(bar.volume)
        self.vwap_cum_pv += typical * volume
        self.vwap_cum_v += volume
        if self.vwap_cum_v == 0.0:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return FeatureValue(value=self.vwap_cum_pv / self.vwap_cum_v, availability=FeatureAvailability.AVAILABLE)

    def _update_extreme(self, bar: NormalizedBar, *, highest: bool) -> FeatureValue:
        length = int(self.spec.params["length"])
        source_value = self._source_value(bar)
        should_remove = (
            (lambda existing: existing <= source_value)
            if highest
            else (lambda existing: existing >= source_value)
        )
        while self.monotonic_window and should_remove(self.monotonic_window[-1][1]):
            self.monotonic_window.pop()
        self.monotonic_window.append((self.index, source_value))
        min_index = self.index - length + 1
        while self.monotonic_window and self.monotonic_window[0][0] < min_index:
            self.monotonic_window.popleft()
        if self.index < length - 1:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return FeatureValue(value=self.monotonic_window[0][1], availability=FeatureAvailability.AVAILABLE)

    def _update_down_streak(self, bar: NormalizedBar) -> FeatureValue:
        close = float(bar.close)
        if self.streak_previous_close is None:
            self.streak_previous_close = close
            return FeatureValue(value=0.0, availability=FeatureAvailability.AVAILABLE)
        if close < self.streak_previous_close:
            self.streak_count += 1
        else:
            self.streak_count = 0
        self.streak_previous_close = close
        return FeatureValue(value=float(self.streak_count), availability=FeatureAvailability.AVAILABLE)

    def _update_ibs(self, bar: NormalizedBar) -> FeatureValue:
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        denom = high - low
        if denom <= 0:
            return FeatureValue(value=0.5, availability=FeatureAvailability.AVAILABLE)
        return FeatureValue(value=(close - low) / denom, availability=FeatureAvailability.AVAILABLE)

    def _update_roc(self, bar: NormalizedBar) -> FeatureValue:
        length = int(self.spec.params["length"])
        close = float(bar.close)
        self.roc_close_history.append(close)
        while len(self.roc_close_history) > length + 1:
            self.roc_close_history.popleft()
        if len(self.roc_close_history) < length + 1:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        prior = self.roc_close_history[0]
        if prior == 0:
            return FeatureValue(value=0.0, availability=FeatureAvailability.AVAILABLE)
        return FeatureValue(value=(close - prior) / prior, availability=FeatureAvailability.AVAILABLE)

    def _update_swing(self, bar: NormalizedBar, *, highest: bool) -> FeatureValue:
        lookback = int(self.spec.params["lookback"])
        window_size = 2 * lookback + 1
        value = float(bar.high) if highest else float(bar.low)
        self.swing_window.append(value)
        if len(self.swing_window) > window_size:
            self.swing_window.popleft()
        if len(self.swing_window) < window_size:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        center = self.swing_window[lookback]
        if highest:
            confirmed = all(center >= other for other in self.swing_window)
        else:
            confirmed = all(center <= other for other in self.swing_window)
        if not confirmed:
            return FeatureValue(value=None, availability=FeatureAvailability.AVAILABLE)
        return FeatureValue(value=center, availability=FeatureAvailability.AVAILABLE)

    def _update_fvg(self, bar: NormalizedBar, *, up: bool) -> FeatureValue:
        min_size_pct = float(self.spec.params.get("min_size_pct", 0.0))
        self.fvg_history.append((float(bar.high), float(bar.low)))
        while len(self.fvg_history) > 3:
            self.fvg_history.popleft()
        if len(self.fvg_history) < 3:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        bar_minus_2 = self.fvg_history[0]
        bar_now = self.fvg_history[2]
        if up:
            gap = bar_now[1] - bar_minus_2[0]
        else:
            gap = bar_minus_2[1] - bar_now[0]
        if gap <= 0:
            return FeatureValue(value=0.0, availability=FeatureAvailability.AVAILABLE)
        ref_price = bar_now[0] if up else bar_now[1]
        if ref_price > 0 and (gap / ref_price * 100.0) < min_size_pct:
            return FeatureValue(value=0.0, availability=FeatureAvailability.AVAILABLE)
        return FeatureValue(value=gap, availability=FeatureAvailability.AVAILABLE)

    def _update_supertrend(self, bar: NormalizedBar) -> FeatureValue:
        length = int(self.spec.params["length"])
        multiplier = float(self.spec.params["multiplier"])
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        # Reuse ATR Wilder calc (composes the existing ATR state below).
        if self.atr_previous_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self.atr_previous_close), abs(low - self.atr_previous_close))
        self.atr_previous_close = close
        if self.index < length:
            self.atr_tr_sum += tr
            if self.index < length - 1:
                return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
            self.atr_avg = self.atr_tr_sum / length
        else:
            assert self.atr_avg is not None
            self.atr_avg = (self.atr_avg * (length - 1) + tr) / length
        atr = self.atr_avg
        median = (high + low) / 2.0
        upper = median + multiplier * atr
        lower = median - multiplier * atr
        if self.supertrend_upper is None or self.supertrend_lower is None:
            self.supertrend_upper = upper
            self.supertrend_lower = lower
            self.supertrend_value = lower
            self.supertrend_direction = 1
            return FeatureValue(value=lower, availability=FeatureAvailability.AVAILABLE)
        # Lock direction: lower bands ratchet up; upper bands ratchet down.
        prev_close_for_band = self.atr_previous_close  # already advanced — use current close instead
        prev_close_for_band = close
        new_upper = upper if (upper < self.supertrend_upper or prev_close_for_band > self.supertrend_upper) else self.supertrend_upper
        new_lower = lower if (lower > self.supertrend_lower or prev_close_for_band < self.supertrend_lower) else self.supertrend_lower
        if self.supertrend_direction == 1 and close < new_lower:
            self.supertrend_direction = -1
        elif self.supertrend_direction == -1 and close > new_upper:
            self.supertrend_direction = 1
        self.supertrend_upper = new_upper
        self.supertrend_lower = new_lower
        self.supertrend_value = new_lower if self.supertrend_direction == 1 else new_upper
        return FeatureValue(value=self.supertrend_value, availability=FeatureAvailability.AVAILABLE)

    def _update_ichimoku_double(self, bar: NormalizedBar, *, length_param: str) -> FeatureValue:
        length = int(self.spec.params[length_param])
        high = float(bar.high)
        low = float(bar.low)
        # Maintain monotonic windows for highest(high, length) and lowest(low, length).
        while self.ichimoku_high_window and self.ichimoku_high_window[-1][1] <= high:
            self.ichimoku_high_window.pop()
        self.ichimoku_high_window.append((self.index, high))
        while self.ichimoku_low_window and self.ichimoku_low_window[-1][1] >= low:
            self.ichimoku_low_window.pop()
        self.ichimoku_low_window.append((self.index, low))
        min_idx = self.index - length + 1
        while self.ichimoku_high_window and self.ichimoku_high_window[0][0] < min_idx:
            self.ichimoku_high_window.popleft()
        while self.ichimoku_low_window and self.ichimoku_low_window[0][0] < min_idx:
            self.ichimoku_low_window.popleft()
        if self.index < length - 1:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        result = (self.ichimoku_high_window[0][1] + self.ichimoku_low_window[0][1]) / 2.0
        return FeatureValue(value=result, availability=FeatureAvailability.AVAILABLE)

    def _update_senkou_a(self, bar: NormalizedBar) -> FeatureValue:
        tenkan_length = int(self.spec.params["tenkan_length"])
        kijun_length = int(self.spec.params["kijun_length"])
        high = float(bar.high)
        low = float(bar.low)
        for window, value, is_high in (
            (self.ichimoku_tenkan_high, high, True),
            (self.ichimoku_tenkan_low, low, False),
            (self.ichimoku_kijun_high, high, True),
            (self.ichimoku_kijun_low, low, False),
        ):
            while window and ((is_high and window[-1][1] <= value) or (not is_high and window[-1][1] >= value)):
                window.pop()
            window.append((self.index, value))
        for window, length in (
            (self.ichimoku_tenkan_high, tenkan_length),
            (self.ichimoku_tenkan_low, tenkan_length),
            (self.ichimoku_kijun_high, kijun_length),
            (self.ichimoku_kijun_low, kijun_length),
        ):
            min_idx = self.index - length + 1
            while window and window[0][0] < min_idx:
                window.popleft()
        if self.index < max(tenkan_length, kijun_length) - 1:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        tenkan = (self.ichimoku_tenkan_high[0][1] + self.ichimoku_tenkan_low[0][1]) / 2.0
        kijun = (self.ichimoku_kijun_high[0][1] + self.ichimoku_kijun_low[0][1]) / 2.0
        return FeatureValue(value=(tenkan + kijun) / 2.0, availability=FeatureAvailability.AVAILABLE)

    def _update_chikou(self, bar: NormalizedBar) -> FeatureValue:
        displacement = int(self.spec.params["displacement"])
        close = float(bar.close)
        self.chikou_close_history.append(close)
        while len(self.chikou_close_history) > displacement + 1:
            self.chikou_close_history.popleft()
        if len(self.chikou_close_history) < displacement + 1:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return FeatureValue(value=self.chikou_close_history[0], availability=FeatureAvailability.AVAILABLE)

    def _update_macd(self, bar: NormalizedBar) -> FeatureValue:
        fast_length = int(self.spec.params["fast_length"])
        slow_length = int(self.spec.params["slow_length"])
        signal_length = int(self.spec.params["signal_length"])
        output = str(self.spec.params["output"]).lower()
        if output not in {"line", "signal", "histogram"}:
            raise UnsupportedBatchFeatureError(f"macd output must be line/signal/histogram, got {output!r}")
        close = float(bar.close)
        fast_alpha = 2.0 / (fast_length + 1)
        slow_alpha = 2.0 / (slow_length + 1)
        signal_alpha = 2.0 / (signal_length + 1)
        self.macd_fast_ema = close if self.macd_fast_ema is None else fast_alpha * close + (1 - fast_alpha) * self.macd_fast_ema
        self.macd_slow_ema = close if self.macd_slow_ema is None else slow_alpha * close + (1 - slow_alpha) * self.macd_slow_ema
        line = self.macd_fast_ema - self.macd_slow_ema
        if self.index < slow_length - 1:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        self.macd_signal_ema = line if self.macd_signal_ema is None else signal_alpha * line + (1 - signal_alpha) * self.macd_signal_ema
        if output == "line":
            return FeatureValue(value=line, availability=FeatureAvailability.AVAILABLE)
        if self.index < slow_length + signal_length - 2:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        if output == "signal":
            return FeatureValue(value=self.macd_signal_ema, availability=FeatureAvailability.AVAILABLE)
        return FeatureValue(value=line - self.macd_signal_ema, availability=FeatureAvailability.AVAILABLE)

    def _update_support_resistance(self, bar: NormalizedBar, *, want_resistance: bool) -> FeatureValue:
        lookback = int(self.spec.params["lookback"])
        pivot_strength = int(self.spec.params["pivot_strength"])
        level_count = int(self.spec.params["level_count"])
        cluster_pct = float(self.spec.params["cluster_pct"])
        output_index = int(self.spec.params["output_index"])
        window_size = 2 * pivot_strength + 1
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        self.sr_high_window.append(high)
        self.sr_low_window.append(low)
        self.sr_close_history.append(close)
        if len(self.sr_high_window) > window_size:
            self.sr_high_window.popleft()
        if len(self.sr_low_window) > window_size:
            self.sr_low_window.popleft()
        if len(self.sr_close_history) > lookback:
            self.sr_close_history.popleft()
        # Detect a confirmed pivot at center of the window.
        if len(self.sr_high_window) == window_size:
            center_high = self.sr_high_window[pivot_strength]
            center_low = self.sr_low_window[pivot_strength]
            if all(center_high >= h for h in self.sr_high_window):
                self.sr_pivot_high_history.append((self.index - pivot_strength, center_high))
            if all(center_low <= ll for ll in self.sr_low_window):
                self.sr_pivot_low_history.append((self.index - pivot_strength, center_low))
        # Drop pivots older than `lookback` bars.
        oldest_allowed = self.index - lookback
        self.sr_pivot_high_history = [pv for pv in self.sr_pivot_high_history if pv[0] >= oldest_allowed]
        self.sr_pivot_low_history = [pv for pv in self.sr_pivot_low_history if pv[0] >= oldest_allowed]
        # Cluster + select levels by proximity to current close.
        pivots = self.sr_pivot_high_history if want_resistance else self.sr_pivot_low_history
        if not pivots:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        clustered = _cluster_levels([p[1] for p in pivots], cluster_pct / 100.0)
        if want_resistance:
            candidates = sorted(level for level in clustered if level > close)
        else:
            candidates = sorted((level for level in clustered if level < close), reverse=True)
        if output_index >= len(candidates) or output_index >= level_count:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return FeatureValue(value=candidates[output_index], availability=FeatureAvailability.AVAILABLE)


def _cluster_levels(levels: list[float], cluster_pct: float) -> list[float]:
    if not levels:
        return []
    sorted_levels = sorted(levels)
    clusters: list[list[float]] = [[sorted_levels[0]]]
    for level in sorted_levels[1:]:
        anchor = clusters[-1][0]
        if anchor != 0 and abs(level - anchor) / abs(anchor) <= cluster_pct:
            clusters[-1].append(level)
        else:
            clusters.append([level])
    return [sum(cluster) / len(cluster) for cluster in clusters]


@dataclass
class _FrameState:
    symbol: str
    timeframe: str
    snapshots: list[FeatureSnapshot] = field(default_factory=list)
    last_timestamp: datetime | None = None


class FeatureCache:
    """Rolling state for incremental feature updates.

    The cache is intentionally in-memory and transport-agnostic. A websocket or
    broker adapter can feed completed bars later, but this layer only knows bars.
    """

    def __init__(self) -> None:
        self._frames: dict[tuple[str, str], _FrameState] = {}
        self._feature_states: dict[tuple[str, str, str], _FeatureState] = {}
        self.processed_bar_count = 0

    def frame_for(self, symbol: str, timeframe: str) -> FeatureFrame:
        state = self._frames[(symbol.upper(), timeframe)]
        return FeatureFrame(symbol=state.symbol, timeframe=state.timeframe, snapshots=tuple(state.snapshots))

    def latest_snapshot_at_or_before(
        self,
        *,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
    ) -> FeatureSnapshot | None:
        state = self._frames.get((symbol.upper(), timeframe))
        if state is None:
            return None
        latest: FeatureSnapshot | None = None
        for snapshot in state.snapshots:
            if snapshot.timestamp <= timestamp:
                latest = snapshot
            else:
                break
        return latest

    def _frame_state(self, symbol: str, timeframe: str) -> _FrameState:
        key = (symbol.upper(), timeframe)
        if key not in self._frames:
            self._frames[key] = _FrameState(symbol=symbol.upper(), timeframe=timeframe)
        return self._frames[key]

    def _feature_state(
        self,
        *,
        symbol: str,
        timeframe: str,
        spec: FeatureSpec,
        feature_key: str,
        feature_registry: FeatureRegistry,
    ) -> _FeatureState:
        key = (symbol.upper(), timeframe, feature_key)
        if key not in self._feature_states:
            self._feature_states[key] = _FeatureState(
                spec=spec,
                feature_key=feature_key,
                warmup=feature_registry.warmup_bars(spec),
            )
        return self._feature_states[key]


class IncrementalFeatureUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    frame: FeatureFrame
    snapshot: FeatureSnapshot


class IncrementalFeatureEngine:
    def __init__(self, feature_registry: FeatureRegistry = registry) -> None:
        self._registry = feature_registry

    def update(
        self,
        *,
        plan: FeaturePlan,
        bar: NormalizedBar,
        cache: FeatureCache,
    ) -> IncrementalFeatureUpdate:
        self._validate_supported(plan.feature_specs)
        normalized_bar = bar.model_copy(update={"symbol": bar.symbol.upper()})
        if normalized_bar.symbol not in plan.symbols:
            raise IncrementalFeatureEngineError(f"bar symbol '{normalized_bar.symbol}' is not in feature plan")
        if normalized_bar.timeframe not in plan.timeframes:
            raise IncrementalFeatureEngineError(f"bar timeframe '{normalized_bar.timeframe}' is not in feature plan")

        frame_state = cache._frame_state(normalized_bar.symbol, normalized_bar.timeframe)
        if frame_state.last_timestamp is not None and normalized_bar.timestamp <= frame_state.last_timestamp:
            raise IncrementalFeatureEngineError("incremental updates require strictly increasing completed bars")

        values: dict[str, FeatureValue] = {}
        for spec, feature_key in zip(plan.feature_specs, plan.feature_keys, strict=True):
            if spec.timeframe != normalized_bar.timeframe:
                continue
            feature_state = cache._feature_state(
                symbol=normalized_bar.symbol,
                timeframe=normalized_bar.timeframe,
                spec=spec,
                feature_key=feature_key,
                feature_registry=self._registry,
            )
            values[feature_key] = feature_state.update(normalized_bar)

        snapshot = FeatureSnapshot(
            symbol=normalized_bar.symbol,
            timeframe=normalized_bar.timeframe,
            timestamp=normalized_bar.timestamp,
            values=values,
        )
        frame_state.snapshots.append(snapshot)
        frame_state.last_timestamp = normalized_bar.timestamp
        cache.processed_bar_count += 1
        return IncrementalFeatureUpdate(
            frame=FeatureFrame(
                symbol=frame_state.symbol,
                timeframe=frame_state.timeframe,
                snapshots=tuple(frame_state.snapshots),
            ),
            snapshot=snapshot,
        )

    def compute(self, plan: FeaturePlan, bars: Sequence[NormalizedBar]) -> FeatureFrameSet:
        bars_by_group: dict[tuple[str, str], list[NormalizedBar]] = defaultdict(list)
        for bar in bars:
            bars_by_group[(bar.symbol.upper(), bar.timeframe)].append(bar)
        cache = FeatureCache()
        frames: list[FeatureFrame] = []
        for symbol in plan.symbols:
            for timeframe in plan.timeframes:
                if not any(spec.timeframe == timeframe for spec in plan.feature_specs):
                    continue
                group_bars = sorted(
                    bars_by_group.get((symbol.upper(), timeframe), []),
                    key=lambda item: item.timestamp,
                )
                if not group_bars:
                    continue
                for bar in group_bars:
                    self.update(plan=plan, bar=bar, cache=cache)
                frames.append(cache.frame_for(symbol.upper(), timeframe))
        return FeatureFrameSet(frames=tuple(frames))

    def _validate_supported(self, specs: tuple[FeatureSpec, ...]) -> None:
        unsupported = [
            f"{spec.timeframe}.{spec.kind}"
            for spec in specs
            if spec.kind not in SUPPORTED_BATCH_KINDS
            or spec.namespace not in {FeatureNamespace.PRICE, FeatureNamespace.TECHNICAL}
            or spec.scope != FeatureScope.SYMBOL
        ]
        if unsupported:
            raise UnsupportedBatchFeatureError(f"unsupported feature(s): {unsupported}")
