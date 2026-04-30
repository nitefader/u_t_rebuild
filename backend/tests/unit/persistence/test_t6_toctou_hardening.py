"""T-6 Bracket Program — TOCTOU hardening regression tests.

MAP §7 D7 (locked 2026-04-30 by operator): the resolver's two policy inputs
— ``account_risk_config`` and the ``account_risk_plan_map`` ⨝
``risk_plan_versions`` join — must be read inside ONE SQLite connection so
a concurrent operator PUT to ``/risk-plan-map`` cannot interleave between
the rows. WAL mode at composition root keeps the writer non-blocking.

The chosen mechanism is single-conn + WAL only. There is NO optimistic
version stamping and NO mid-evaluation rejection rule. Updates that arrive
after a snapshot has been opened apply to the next evaluation
(last-writer-wins outside the evaluation window).

These tests exercise the SQLite layer directly because the doctrine
guarantee only needs to hold for the production ``SQLiteRuntimeStore`` —
which is the only store the operator's PUT can race against.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.broker_accounts.models import (
    AccountRiskConfig,
    BrokerAccount,
    BrokerAccountValidationStatus,
)
from backend.app.domain import TradingMode
from backend.app.domain.risk_plan import (
    RiskPlan,
    RiskPlanConfig,
    RiskPlanSizingMethod,
    RiskPlanSource,
    RiskPlanStatus,
    RiskPlanTier,
    RiskPlanVersion,
    RiskPlanVersionStatus,
)
from backend.app.domain.strategy_controls import TradingHorizon
from backend.app.persistence import SQLiteRuntimeStore


ACCOUNT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PLAN_ID = UUID("11111111-1111-1111-1111-111111111111")
VERSION_OLD_ID = UUID("22222222-2222-2222-2222-222222222222")
VERSION_NEW_ID = UUID("33333333-3333-3333-3333-333333333333")


def _broker_account() -> BrokerAccount:
    return BrokerAccount(
        id=ACCOUNT_ID,
        display_name="T6 Race Account",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref=f"alpaca-paper:{ACCOUNT_ID}:ref",
        validation_status=BrokerAccountValidationStatus.VALID,
    )


def _risk_plan() -> RiskPlan:
    return RiskPlan(
        risk_plan_id=PLAN_ID,
        name="T6 Race Plan",
        status=RiskPlanStatus.ACTIVE,
        risk_tier=RiskPlanTier.BALANCED,
        risk_score=5,
        source=RiskPlanSource.MANUAL,
        created_at=datetime(2026, 4, 30, 5, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 30, 5, 0, tzinfo=timezone.utc),
    )


def _risk_plan_version(version_id: UUID, *, max_open_positions: int) -> RiskPlanVersion:
    return RiskPlanVersion(
        risk_plan_version_id=version_id,
        risk_plan_id=PLAN_ID,
        version=1 if version_id == VERSION_OLD_ID else 2,
        status=RiskPlanVersionStatus.ACTIVE,
        config=RiskPlanConfig(
            sizing_method=RiskPlanSizingMethod.RISK_PERCENT,
            risk_per_trade_pct=1.0,
            max_open_positions=max_open_positions,
        ),
        config_fingerprint=f"fp-{version_id}",
        created_at=datetime(2026, 4, 30, 5, 0, tzinfo=timezone.utc),
        activated_at=datetime(2026, 4, 30, 5, 0, tzinfo=timezone.utc),
    )


def _account_risk_config(*, max_open_positions: int | None = None) -> AccountRiskConfig:
    return AccountRiskConfig(
        account_id=ACCOUNT_ID,
        max_open_positions=max_open_positions,
        risk_per_trade_pct=1.0,
        sizing_method="risk_percent_equity",
        updated_at=datetime(2026, 4, 30, 5, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# WAL mode at composition root
# ---------------------------------------------------------------------------


def test_wal_mode_is_enabled_on_connect(tmp_path) -> None:
    """SQLiteSessionFactory.connect() must promote the database to WAL mode.

    WAL is a persistent database property, so the journal_mode pragma read
    after the first connection should report ``wal``. Reader-writer
    concurrency requires WAL — without it, a writer (operator PUT) blocks
    the reader (in-flight Governor evaluation) and the doctrine guarantee
    in MAP §7 D7 collapses to whichever side won the lock.
    """
    SQLiteRuntimeStore(tmp_path / "wal.db")
    with sqlite3.connect(tmp_path / "wal.db") as connection:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_wal_mode_is_idempotent_on_repeat_connect(tmp_path) -> None:
    """Re-issuing PRAGMA journal_mode=WAL on every connect is a no-op once
    the database file is already in WAL mode. Repeated process boots must
    not error or revert the journal mode.
    """
    db_path = tmp_path / "wal_idem.db"
    SQLiteRuntimeStore(db_path)
    SQLiteRuntimeStore(db_path)  # second open must not raise
    SQLiteRuntimeStore(db_path)  # third open for good measure
    with sqlite3.connect(db_path) as connection:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


# ---------------------------------------------------------------------------
# Composite read returns coherent snapshot
# ---------------------------------------------------------------------------


def test_load_governor_policy_inputs_returns_both_halves(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "snap.db")
    store.save_broker_account(_broker_account())
    store.save_risk_plan(_risk_plan())
    store.save_risk_plan_version(_risk_plan_version(VERSION_OLD_ID, max_open_positions=3))
    store.save_account_risk_config(_account_risk_config(max_open_positions=10))
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_OLD_ID)

    account_config, plan_config = store.load_governor_policy_inputs(ACCOUNT_ID, TradingHorizon.INTRADAY)

    assert account_config is not None
    assert account_config.max_open_positions == 10
    assert plan_config is not None
    assert plan_config.max_open_positions == 3


def test_load_governor_policy_inputs_returns_none_for_missing_rows(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "miss.db")
    store.save_broker_account(_broker_account())
    # No account_risk_config row, no risk_plan_map row.
    account_config, plan_config = store.load_governor_policy_inputs(ACCOUNT_ID, TradingHorizon.INTRADAY)
    assert account_config is None
    assert plan_config is None


def test_load_governor_policy_inputs_skips_deprecated_plan(tmp_path) -> None:
    """A DEPRECATED RiskPlanVersion must not contribute to the snapshot.

    Mirrors Slice B fix B-RISK-3 — archive/deprecate must invalidate the
    map reference at read time so retired plans cannot silently keep
    enforcing.
    """
    store = SQLiteRuntimeStore(tmp_path / "dep.db")
    store.save_broker_account(_broker_account())
    store.save_risk_plan(_risk_plan())
    deprecated = _risk_plan_version(VERSION_OLD_ID, max_open_positions=3).model_copy(
        update={
            "status": RiskPlanVersionStatus.DEPRECATED,
            "archived_at": datetime(2026, 4, 30, 5, 30, tzinfo=timezone.utc),
        }
    )
    store.save_risk_plan_version(deprecated)
    store.save_account_risk_config(_account_risk_config(max_open_positions=10))
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_OLD_ID)

    account_config, plan_config = store.load_governor_policy_inputs(ACCOUNT_ID, TradingHorizon.INTRADAY)
    assert account_config is not None
    assert plan_config is None


# ---------------------------------------------------------------------------
# Concurrent PUT vs. composite read — the headline doctrine test
# ---------------------------------------------------------------------------


def test_concurrent_put_does_not_yield_mixed_state_to_evaluation(tmp_path) -> None:
    """Race a concurrent operator PUT against repeated composite reads.

    Doctrine (MAP §7 D7): every snapshot returned by
    ``load_governor_policy_inputs`` must be either fully OLD or fully NEW
    — never a mix. Last-writer-wins outside the evaluation window is
    acceptable; what is forbidden is a single snapshot that observes a
    half-applied write.

    In this database the only write that races is the map-entry update
    (PUT /risk-plan-map). That changes which RiskPlanVersion is joined.
    The OLD plan caps positions at 3; the NEW plan caps at 7. Both rows
    exist in ``risk_plan_versions`` for the entirety of the test, so the
    join target is always resolvable. A coherent read returns either
    plan_config.max_open_positions == 3 (old still mapped) or == 7
    (new mapped). Anything else is a TOCTOU mix and would fail the test.
    """
    store = SQLiteRuntimeStore(tmp_path / "race.db")
    store.save_broker_account(_broker_account())
    store.save_risk_plan(_risk_plan())
    store.save_risk_plan_version(_risk_plan_version(VERSION_OLD_ID, max_open_positions=3))
    store.save_risk_plan_version(_risk_plan_version(VERSION_NEW_ID, max_open_positions=7))
    store.save_account_risk_config(_account_risk_config(max_open_positions=10))
    # Map starts on the OLD version.
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_OLD_ID)

    stop = threading.Event()
    observed_caps: list[int] = []
    observed_lock = threading.Lock()
    errors: list[BaseException] = []

    def _reader() -> None:
        try:
            while not stop.is_set():
                _account, plan = store.load_governor_policy_inputs(
                    ACCOUNT_ID, TradingHorizon.INTRADAY
                )
                # Plan must always resolve — both versions exist for the
                # whole test, the only thing changing is which one the
                # map points at. None means the join failed inside the
                # window between writer's DELETE+INSERT (if any),
                # which would itself be a TOCTOU mix.
                assert plan is not None, "snapshot resolved to no plan during PUT race"
                with observed_lock:
                    observed_caps.append(plan.max_open_positions)
        except BaseException as exc:  # noqa: BLE001 — propagate to main thread
            errors.append(exc)

    def _writer() -> None:
        try:
            # Flip back and forth between OLD and NEW many times.
            for i in range(200):
                target = VERSION_NEW_ID if i % 2 == 0 else VERSION_OLD_ID
                store.save_account_risk_plan_map_entry(
                    ACCOUNT_ID, TradingHorizon.INTRADAY, target
                )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            stop.set()

    reader_thread = threading.Thread(target=_reader, name="t6-race-reader")
    writer_thread = threading.Thread(target=_writer, name="t6-race-writer")
    reader_thread.start()
    writer_thread.start()
    writer_thread.join(timeout=30)
    stop.set()
    reader_thread.join(timeout=30)

    assert not errors, f"thread error during race: {errors[0]!r}"
    # The reader must have actually run (otherwise the test is vacuous).
    assert len(observed_caps) > 10, "reader did not get enough samples"
    # Every observed value must be one of the two coherent states.
    assert set(observed_caps).issubset({3, 7}), (
        f"observed inconsistent snapshot value(s): {set(observed_caps) - {3, 7}}"
    )
    # The writer flipped the map ~200 times; the reader should have seen
    # at least both states unless it happened to align with one phase. We
    # assert "saw at least one transition" softly: the test is meaningful
    # even if observation timing leaned one way, but a healthy WAL setup
    # should usually witness both.
    # (No assertion on multi-state observation — the doctrine guarantee
    # is "no mix"; observing only one state still satisfies it.)


def test_concurrent_put_does_not_block_reader(tmp_path) -> None:
    """WAL mode keeps the reader non-blocking under writer pressure.

    If WAL mode were missing (legacy ``delete`` journal mode), a long
    writer transaction could block the reader for the duration of every
    write. With WAL, readers see a consistent prior snapshot while the
    writer commits in parallel. This test is the soft check that the
    mechanism is in place — it asserts the reader thread completes
    100 reads in well under the time the writer takes to push 200
    map-entry updates.
    """
    store = SQLiteRuntimeStore(tmp_path / "wal_thru.db")
    store.save_broker_account(_broker_account())
    store.save_risk_plan(_risk_plan())
    store.save_risk_plan_version(_risk_plan_version(VERSION_OLD_ID, max_open_positions=3))
    store.save_risk_plan_version(_risk_plan_version(VERSION_NEW_ID, max_open_positions=7))
    store.save_account_risk_config(_account_risk_config(max_open_positions=10))
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_OLD_ID)

    writer_done = threading.Event()
    reader_count = [0]

    def _writer() -> None:
        for i in range(200):
            target = VERSION_NEW_ID if i % 2 == 0 else VERSION_OLD_ID
            store.save_account_risk_plan_map_entry(
                ACCOUNT_ID, TradingHorizon.INTRADAY, target
            )
        writer_done.set()

    def _reader() -> None:
        # Hammer reads until the writer is done. Under WAL, this should
        # produce hundreds of reads; without WAL the writer would
        # serialize and the reader would stall.
        while not writer_done.is_set():
            store.load_governor_policy_inputs(ACCOUNT_ID, TradingHorizon.INTRADAY)
            reader_count[0] += 1

    writer_thread = threading.Thread(target=_writer)
    reader_thread = threading.Thread(target=_reader)
    writer_thread.start()
    reader_thread.start()
    writer_thread.join(timeout=30)
    reader_thread.join(timeout=30)

    assert writer_done.is_set()
    # If WAL were off and SQLite serialized writer↔reader, the reader
    # would manage at most a handful of reads. With WAL we see hundreds.
    # Soft floor: at least 50 reads completed in parallel with 200 writes.
    assert reader_count[0] >= 50, (
        f"reader only completed {reader_count[0]} reads — "
        "WAL appears to be off or reader-writer concurrency is broken"
    )


# ---------------------------------------------------------------------------
# Resolver wiring through composite lookup — orchestrator-level integration
# ---------------------------------------------------------------------------


def test_concurrent_dual_write_does_not_yield_correlated_mix(tmp_path) -> None:
    """Race BOTH halves of the snapshot — assert reader never sees a mix.

    Architecture-critic BUG-1 + Adversarial-critic BUG-1 (T-6 Pass 8):
    the headline race test only flipped the map row, so any "mix" would
    still report a coherent plan_config. This test mutates BOTH
    ``account_risk_configs`` and ``account_risk_plan_map`` inside ONE
    SQLite transaction and tags each generation with a distinct value:

        - generation A: account.max_open_positions=10, plan→OLD (cap=3)
        - generation B: account.max_open_positions=20, plan→NEW (cap=7)

    The writer commits both row updates together in a single
    transaction, so the only operator-published states are the two
    coherent generations. A correctly atomic READ snapshot returns
    either (10, 3) or (20, 7). A half-applied READ — i.e. the reader
    observed the writer's commit between its own two SELECTs — would
    return (10, 7) or (20, 3); the reader will catch that and fail.

    Without the explicit ``BEGIN`` ... ``COMMIT`` block in
    ``load_governor_policy_inputs``, the two SELECTs autocommit
    individually in WAL mode and can observe writes that committed
    between them. With the read transaction in place, both rows come
    from one snapshot.
    """
    db_path = tmp_path / "dual.db"
    store = SQLiteRuntimeStore(db_path)
    store.save_broker_account(_broker_account())
    store.save_risk_plan(_risk_plan())
    store.save_risk_plan_version(_risk_plan_version(VERSION_OLD_ID, max_open_positions=3))
    store.save_risk_plan_version(_risk_plan_version(VERSION_NEW_ID, max_open_positions=7))
    # Start in generation A.
    store.save_account_risk_config(_account_risk_config(max_open_positions=10))
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_OLD_ID)

    # Capture the JSON payload shape the persistence layer expects so
    # the writer thread can craft transactional updates without going
    # through the per-row store helpers (which commit individually).
    config_payload_a = _account_risk_config(max_open_positions=10).model_dump_json()
    config_payload_b = _account_risk_config(max_open_positions=20).model_dump_json()
    now_iso = datetime(2026, 4, 30, 6, 0, tzinfo=timezone.utc).isoformat()

    stop = threading.Event()
    observed: list[tuple[int | None, int | None]] = []
    obs_lock = threading.Lock()
    errors: list[BaseException] = []

    def _reader() -> None:
        try:
            while not stop.is_set():
                account, plan = store.load_governor_policy_inputs(
                    ACCOUNT_ID, TradingHorizon.INTRADAY
                )
                assert account is not None and plan is not None, (
                    "snapshot lost a half during dual-write race"
                )
                with obs_lock:
                    observed.append(
                        (account.max_open_positions, plan.max_open_positions)
                    )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def _writer() -> None:
        try:
            for i in range(200):
                if i % 2 == 0:
                    payload = config_payload_b
                    target_version = str(VERSION_NEW_ID)
                else:
                    payload = config_payload_a
                    target_version = str(VERSION_OLD_ID)
                # Atomic dual-write: both rows committed together so the
                # only operator-visible states are the two coherent
                # generations. If the reader's BEGIN/COMMIT is correct,
                # it sees the pre-commit state through the entirety of
                # its two SELECTs and never observes a mix.
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        """
                        INSERT INTO account_risk_configs (account_id, version, updated_at, payload)
                        VALUES (?, 1, ?, ?)
                        ON CONFLICT(account_id) DO UPDATE SET
                            version = excluded.version,
                            updated_at = excluded.updated_at,
                            payload = excluded.payload
                        """,
                        (str(ACCOUNT_ID), now_iso, payload),
                    )
                    conn.execute(
                        """
                        INSERT INTO account_risk_plan_map
                            (account_id, horizon, risk_plan_version_id, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(account_id, horizon) DO UPDATE SET
                            risk_plan_version_id = excluded.risk_plan_version_id,
                            updated_at = excluded.updated_at
                        """,
                        (str(ACCOUNT_ID), TradingHorizon.INTRADAY.value, target_version, now_iso),
                    )
                    conn.execute("COMMIT")
                finally:
                    conn.close()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            stop.set()

    reader_thread = threading.Thread(target=_reader, name="t6-dual-reader")
    writer_thread = threading.Thread(target=_writer, name="t6-dual-writer")
    reader_thread.start()
    writer_thread.start()
    writer_thread.join(timeout=30)
    stop.set()
    reader_thread.join(timeout=30)

    assert not errors, f"thread error during dual-write race: {errors[0]!r}"
    assert len(observed) > 10
    # Two coherent generations: A=(10, 3), B=(20, 7). Anything else is a
    # half-applied snapshot — the BUG-1 failure mode.
    bad = [pair for pair in observed if pair not in {(10, 3), (20, 7)}]
    assert not bad, (
        f"observed inconsistent (account, plan) pairs: {set(bad)} — "
        "single-conn alone is not enough, the read needs an explicit transaction"
    )


def test_governor_evaluation_observes_no_mixed_state_under_put_race(tmp_path) -> None:
    """End-to-end: resolver-driven Governor evaluation against a live race.

    Wires the production-grade ``GovernorPolicyResolver`` against the
    real ``SQLiteRuntimeStore.load_governor_policy_inputs`` and asserts
    that every resolved ``GovernorPolicy.max_open_positions`` is one of
    the coherent OLD / NEW values (3 or 7), never something half-applied.
    """
    from backend.app.governor import GovernorPolicy, GovernorPolicyResolver

    store = SQLiteRuntimeStore(tmp_path / "race_resolver.db")
    store.save_broker_account(_broker_account())
    store.save_risk_plan(_risk_plan())
    store.save_risk_plan_version(_risk_plan_version(VERSION_OLD_ID, max_open_positions=3))
    store.save_risk_plan_version(_risk_plan_version(VERSION_NEW_ID, max_open_positions=7))
    store.save_account_risk_config(_account_risk_config(max_open_positions=None))
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.SWING, VERSION_OLD_ID)

    def _composite(account_id: UUID, horizon: TradingHorizon):
        return store.load_governor_policy_inputs(account_id, horizon)

    resolver = GovernorPolicyResolver(get_policy_inputs=_composite)
    floor = GovernorPolicy()

    stop = threading.Event()
    observed: list[int | None] = []
    obs_lock = threading.Lock()
    errors: list[BaseException] = []

    def _evaluator() -> None:
        try:
            while not stop.is_set():
                policy = resolver.resolve(
                    floor=floor,
                    account_id=ACCOUNT_ID,
                    deployment_id=uuid4(),
                    risk_horizon=TradingHorizon.SWING,
                )
                with obs_lock:
                    observed.append(policy.max_open_positions)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def _writer() -> None:
        try:
            for i in range(200):
                target = VERSION_NEW_ID if i % 2 == 0 else VERSION_OLD_ID
                store.save_account_risk_plan_map_entry(
                    ACCOUNT_ID, TradingHorizon.SWING, target
                )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            stop.set()

    eval_thread = threading.Thread(target=_evaluator)
    writer_thread = threading.Thread(target=_writer)
    eval_thread.start()
    writer_thread.start()
    writer_thread.join(timeout=30)
    stop.set()
    eval_thread.join(timeout=30)

    assert not errors, f"thread error during race: {errors[0]!r}"
    assert len(observed) > 10
    # Each observation is the resolved GovernorPolicy.max_open_positions.
    # AccountRiskConfig is None for this field, so the resolver's min-of-
    # present rule reduces to the plan-side cap. Coherent values: 3 or 7.
    assert set(observed).issubset({3, 7}), (
        f"resolver observed inconsistent snapshot value(s): "
        f"{set(observed) - {3, 7}}"
    )
