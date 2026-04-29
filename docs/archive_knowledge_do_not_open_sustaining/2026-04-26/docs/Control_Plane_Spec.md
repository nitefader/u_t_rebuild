# Control-Plane Engineering Spec

**Timestamp (ET):** 2026-04-22 11:02:07 AM ET

**Version:** 1.0  
**Status:** Approved for implementation  
**Scope:** Paper trading only — no live-safe migration required

---

## Alpaca SDK Verification (alpaca-py)

The following claims were verified against `backend/app/services/alpaca_service.py`
and the alpaca-py SDK as used in this codebase. No Alpaca behavior is assumed — only
what is observed in the existing code.

| Claim | Verified |
|---|---|
| `get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))` returns open orders | ✅ Line 313 |
| `get_all_positions()` returns all open positions as a list | ✅ Line 287 |
| `cancel_order_by_id(order_id)` takes Alpaca internal order UUID, not `client_order_id` | ✅ Line 466 |
| `cancel_orders()` cancels all open orders on the account | ✅ Line 477 |
| `close_all_positions(cancel_orders=True)` closes positions and cancels open orders atomically | ✅ Line 503 |
| Bracket legs have Alpaca status `"held"`, not `"open"` — not returned by OPEN query | ✅ Alpaca docs + SDK behavior |
| Bracket legs do NOT inherit parent `client_order_id` | ✅ Not set in `place_bracket_order()` |
| `client_order_id` limit is 128 chars | ✅ Noted in existing `build_program_client_order_id()` docstring |
| `_fmt_order()` returns `"id"` as the Alpaca order UUID for cancellation | ✅ Line 857 |
| `_fmt_order()` returns `"client_order_id"` as the program-tagged string | ✅ Line 858 |
| Position `"symbol"` and order `"symbol"` are both uppercase tickers | ✅ Lines 834, 860 |

---

## Purpose

This spec defines the exact engineering contract for the control-plane:
Global Kill, Account Pause, Program Pause, and Flatten.

It covers:
- state machine for each scope
- `client_order_id` format and intent encoding
- order intent classification table
- cancellation decision matrix
- unified entry gate function
- startup hydration sequence
- acceptance criteria per phase
- UI result contract

---

## Guiding Principle

> Pause and kill logic is about **preventing new exposure**, not canceling everything.
>
> Open positions remain managed.  
> Protective exits remain alive.  
> New entries stop immediately.  
> Stale resting entry orders are removed.

---

## Current State (as-built)

| Capability | Status | Location |
|---|---|---|
| Global kill (in-memory) | ✅ | `app/core/kill_switch.py` |
| Account-level kill (in-memory) | ✅ | `kill_switch.py` — `kill_account()` |
| Account kill persisted to DB | ✅ | `Account.is_killed` |
| Account kill rehydrated on startup | ✅ | `main.py::_restore_kill_switch_state()` |
| Global kill persisted to DB | ✅ | `KillSwitchEvent` table |
| Global kill rehydrated on startup | ❌ | Only accounts rehydrated, not global event |
| Program/deployment pause persisted | ⚠️ | `Deployment.status = "paused"` but not reloaded into kill_switch |
| Program pause rehydrated on startup | ❌ | Not implemented |
| `can_trade()` gate | ✅ | `kill_switch.can_trade()` — but scoped to strategy_id not deployment_id |
| Order intent in `client_order_id` | ❌ | Format is `{prog}-{deploy8}-{rand8}` — no intent field |
| Intent-aware order cancellation | ❌ | Only cancel-all or cancel-nothing |
| Cancellation audit events | ❌ | Not emitted |
| Governor loop checks kill switch | ⚠️ | Checks `governor_status != "halted"` but not `can_trade()` on every signal |

---

## Scope Definitions

| Scope | What it controls | Precedence |
|---|---|---|
| Global Kill | All accounts, all programs, platform-wide | Highest — overrides all |
| Account Pause | All programs on one broker account | Overrides program state for that account |
| Program Pause | One deployment on one account | Lowest — applies only to that deployment |

Scope precedence is strictly hierarchical. A program-level resume does not override an account-level pause. An account-level resume does not override a global kill.

---

## State Machine

### Global Kill

```
ACTIVE ──kill_all()──► KILLED
KILLED ──unkill_all()──► ACTIVE
```

Persisted in: `KillSwitchEvent` (action=`kill` | `resume`)  
In-memory: `KillSwitch._global_killed`  
Rehydrated on startup: must reload last event with `action="kill"` if no subsequent `action="resume"`

### Account Pause

```
ACTIVE ──kill_account()──► PAUSED
PAUSED ──unkill_account()──► ACTIVE
```

Persisted in: `Account.is_killed`, `Account.kill_reason`  
In-memory: `KillSwitch._account_kills[account_id]`  
Rehydrated on startup: ✅ already implemented

### Program Pause

```
RUNNING ──pause_deployment()──► PAUSED
PAUSED ──resume_deployment()──► RUNNING
RUNNING ──stop_deployment()──► STOPPED  (terminal)
```

Persisted in: `Deployment.status`  
In-memory: `KillSwitch` — currently misscoped to `strategy_id`, must change to `deployment_id`  
Rehydrated on startup: ❌ must be added

### Governor Halt (daily loss / drawdown)

```
ACTIVE ──_halt_governor()──► HALTED
HALTED ──resume (manual)──► ACTIVE
```

Persisted in: `Deployment.governor_status`, `Deployment.halt_trigger`  
Handled separately from pause — not part of this spec's scope changes.

---

## Phase 1 — client_order_id Intent Encoding

### Current format

```
{prog_abbrev}-{deploy8}-{rand8}
e.g. MACD-a3f2b1c4-d9e7f023
```

### New format

```
{prog_abbrev}-{deploy8}-{intent}-{rand8}
e.g. MACD-a3f2b1c4-open-d9e7f023
     MACD-a3f2b1c4-tp-d9e7f023
     MACD-a3f2b1c4-sl-d9e7f023
     MACD-a3f2b1c4-close-d9e7f023
     MACD-a3f2b1c4-scale-d9e7f023
```

### Intent values

| Intent | Meaning | Cancel on pause? |
|---|---|---|
| `open` | Opening a new position | ✅ Cancel |
| `close` | Closing an existing position (signal exit) | ❌ Keep |
| `tp` | Take-profit leg of a bracket | ❌ Keep |
| `sl` | Stop-loss leg of a bracket | ❌ Keep |
| `scale` | Scale-out of an existing position | ❌ Keep |
| `unknown` | Cannot be parsed | ❌ Keep (fail-closed) |

### Functions to add

```python
# app/services/alpaca_service.py

def build_program_client_order_id(
    program_name: str | None,
    deployment_id: str | None,
    intent: str = "open",   # new required-with-default parameter
) -> str:
    """
    Format: {prog_abbrev}-{deploy8}-{intent}-{rand8}
    Intent must be one of: open, close, tp, sl, scale
    Alpaca client_order_id limit is 128 chars (confirmed in SDK source).
    This format stays well under that limit at ~35 chars maximum.
    """

def parse_order_intent(client_order_id: str | None) -> str:
    """
    Extract the intent segment from a client_order_id.
    Returns one of: open, close, tp, sl, scale, unknown.
    unknown is returned for any format that cannot be parsed,
    including legacy format without intent field, None, or raw UUIDs.

    New format:  {prog}-{deploy8}-{intent}-{rand8}  → 4 dash-separated parts, intent at index 2
    Legacy format: {prog}-{deploy8}-{rand8}          → 3 parts, intent absent → "unknown"
    Raw UUID (auto-generated fallback):               → 5 hex groups → "unknown"
    None:                                             → "unknown"
    """

def parse_order_deployment_id(client_order_id: str | None) -> str | None:
    """
    Extract the deployment_id prefix (first 8 chars of deployment_id) from a
    client_order_id for scope filtering in cancel_resting_open_orders_without_positions.

    New format: index 1 is the deploy8 segment.
    Legacy or unrecognized format: returns None.

    Note: this matches on the 8-char prefix of deployment_id, not the full UUID.
    Callers must compare deploy8 == deployment_id[:8] for the match.
    """
```

### Acceptance criteria

- `build_program_client_order_id("MACD SPY", "abc12345", "open")` → contains `-open-`
- `build_program_client_order_id("MACD SPY", "abc12345", "tp")` → contains `-tp-`
- `parse_order_intent("MACD-abc12345-open-d9e7f023")` → `"open"`
- `parse_order_intent("MACD-abc12345-sl-d9e7f023")` → `"sl"`
- `parse_order_intent("MACD-a3f2b1c4-d9e7f023")` → `"unknown"` (legacy format)
- `parse_order_intent(None)` → `"unknown"`
- `parse_order_intent("garbage")` → `"unknown"`
- Total length stays under 128 chars (Alpaca limit)

---

## Phase 2 — Startup Kill-State Hydration

### Gap

`_restore_kill_switch_state()` in `main.py` reloads `Account.is_killed` but does not reload the global kill state from `KillSwitchEvent`.

### Fix

Extend `_restore_kill_switch_state()` to:

1. Load the most recent `KillSwitchEvent` with `scope="global"`
2. If the last event has `action="kill"` and no subsequent `action="resume"`, call `ks.kill_all(reason=..., triggered_by="system")`
3. Load all `Deployment` rows with `status="paused"` and register them in kill_switch scoped to `deployment_id`

### Startup sequence (after fix)

```
1. create_all_tables()
2. _run_schema_migrations()
3. seed_default_data()
4. _restore_kill_switch_state()
   a. reload global kill from KillSwitchEvent
   b. reload account kills from Account.is_killed  ← already done
   c. reload program pauses from Deployment.status="paused"  ← new
5. start_watchlist_scheduler()
6. start_account_governor_loop()
7. start_alpaca_account_stream()
```

No order submission can occur before step 4 completes.

### Acceptance criteria

- Kill global, restart server, `ks.is_globally_killed` is `True` before governor loop starts
- Pause a deployment, restart server, that deployment cannot open new positions before governor loop starts
- Resume global kill, restart server, `ks.is_globally_killed` is `False`

---

## Phase 3 — Unified Entry Gate

### Current problem

Kill checks are scattered:
- `governor_service.halt_governor()` sets `governor_status = "halted"`
- `account_governor_loop.py` checks `Deployment.governor_status != "halted"`
- `kill_switch.can_trade()` exists but takes `strategy_id` not `deployment_id`
- No single function enforces all three scopes in order

### New function

```python
# app/core/kill_switch.py

def can_open_new_position(
    account_id: str,
    deployment_id: str,
    symbol: str,
    side: str,  # "buy" | "sell"
) -> tuple[bool, str]:
    """
    Single gate for all order-opening paths.
    Checks scopes in precedence order: global → account → deployment.

    Returns (True, "ok") or (False, reason_string).

    This is the ONLY function that should gate new position-opening orders.
    All callers must use this and must not duplicate the logic.
    """
    if self._global_killed:
        return False, f"global_kill: {self._global_kill_reason}"
    if self.is_account_killed(account_id):
        return False, f"account_paused: {account_id}"
    if self.is_deployment_paused(deployment_id):
        return False, f"program_paused: {deployment_id}"
    return True, "ok"
```

`can_trade()` is kept for backward compatibility but deprecated — all new code uses `can_open_new_position()`.

### All paths that must use this gate

| Path | File | Current state |
|---|---|---|
| Governor loop signal evaluation | `account_governor_loop.py` | Uses `governor_status` check only |
| Deployment start/resume | `deployment_service.py` | No gate |
| Monitor manual order entry | `api/routes/control.py` or monitor routes | No gate |
| Any future broker wrapper | `alpaca_service.py` | No gate at submission level |

### Acceptance criteria

- Global kill active → `can_open_new_position()` returns `False` for all accounts/deployments
- Account paused → returns `False` for that account only, other accounts unaffected
- Deployment paused → returns `False` for that deployment only, other deployments on same account unaffected
- All four paths above call `can_open_new_position()` before any order submission
- No path calls `alpaca_service.submit_order()` for opening orders without passing through the gate first

---

## Phase 4 — Intent-Aware Order Cancellation

This is the core of the spec. Depends on Phase 1 (intent in `client_order_id`).

### Alpaca order status facts (verified against SDK)

`get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))` returns orders with Alpaca
status `"new"`, `"partially_filled"`, `"done_for_day"`, `"accepted"`, `"pending_new"`,
`"accepted_for_bidding"`. It does **not** return orders with status `"held"`.

Bracket order legs (the `tp` and `sl` child orders) have Alpaca status `"held"` — they
are contingent on the parent order and will not appear in an `OPEN` query. This means:

- The parent bracket order (the opening market order) **will** appear in the `OPEN` result.
- The `tp` and `sl` legs are **not** returned by `QueryOrderStatus.OPEN`.
- Therefore, Phase 4 cancellation naturally cannot cancel bracket legs — they are invisible
  to the query. This is the correct safe behavior and requires no special handling.

The `client_order_id` on bracket legs: Alpaca does **not** automatically propagate the
parent's `client_order_id` to child legs. Each leg has its own `id` (UUID) and `client_order_id`
is `null` unless explicitly set at submission time. Since `place_bracket_order()` only sets
`client_order_id` on the parent, bracket legs will have `client_order_id=None` → `parse_order_intent()`
returns `"unknown"` → they are kept and flagged. This is the correct conservative outcome.

Positions are fetched via `client.get_all_positions()` which returns all currently open positions.
The `symbol` field on a position object matches the `symbol` field on an order object (both are
uppercase ticker strings). The position lookup is a simple `symbol in open_positions_set` check.

`cancel_order_by_id(order_id)` takes the Alpaca internal order UUID (the `id` field, not
`client_order_id`). The `_fmt_order()` helper returns this as `"id"` in the dict. The
cancellation sweep must use the `"id"` field, not `"client_order_id"`, when calling
`cancel_order_by_id()`.

### Function signature

```python
# app/services/alpaca_service.py

async def cancel_resting_open_orders_without_positions(
    config: AlpacaClientConfig,
    scope: str,                    # "global" | "account" | "deployment"
    deployment_id: str | None,     # required when scope="deployment"
    dry_run: bool = False,
) -> CancellationResult:
    """
    Cancel only resting orders that are opening new exposure
    and are not backed by an already-open position.

    Uses QueryOrderStatus.OPEN — bracket legs (status="held") are not returned
    by this query and cannot be canceled by this function. This is intentional.

    Steps:
    1. Fetch all open orders via get_orders(config, "open")  → list[dict]
    2. Fetch all open positions via get_positions(config)     → list[dict]
       Build a set: open_symbols = {p["symbol"] for p in positions}
    3. For each open order dict:
       a. Parse intent from order["client_order_id"]
       b. If scope="deployment": skip orders whose client_order_id doesn't
          parse to the target deployment_id
       c. If intent != "open": classify as protective/reducing → skip
       d. If intent == "open" and order["symbol"] in open_symbols:
          conservative skip — may be scale-in
       e. If intent == "open" and order["symbol"] not in open_symbols:
          safe to cancel → cancel via cancel_order(config, order["id"])
       f. If intent == "unknown": skip and flag for review
    4. Return CancellationResult
    5. Emit structured log entry for every cancel and every skip
    """
```

### CancellationResult schema

```python
@dataclass
class CancellationResult:
    scope: str
    canceled: list[OrderAuditEntry]     # orders canceled
    skipped_protective: list[OrderAuditEntry]   # kept — sl/tp/close/scale
    skipped_has_position: list[OrderAuditEntry] # kept — open intent but position exists
    skipped_unknown: list[OrderAuditEntry]      # kept — unparseable, treated conservatively
    errors: list[str]                   # cancel attempts that failed
    dry_run: bool
```

### OrderAuditEntry schema

```python
@dataclass
class OrderAuditEntry:
    order_id: str
    client_order_id: str | None
    symbol: str
    side: str
    qty: float
    intent: str          # parsed intent
    reason: str          # why canceled or skipped
    deployment_id: str | None  # parsed from client_order_id if available
```

### Cancellation decision matrix

| Intent | Open position in symbol? | Action | Reason |
|---|---|---|---|
| `open` | No | **CANCEL** | Resting entry with no backing position |
| `open` | Yes | Skip | Conservative — may be scale-in |
| `close` | Any | Skip | Reducing exposure |
| `tp` | Any | Skip | Protective exit |
| `sl` | Any | Skip | Protective exit |
| `scale` | Any | Skip | Reducing exposure |
| `unknown` | Any | Skip + flag | Cannot classify — fail-closed |

### Scope filtering

When `scope="deployment"`, only cancel orders where `parse_order_deployment_id(order["client_order_id"]) == deployment_id[:8]`. Orders from other deployments on the same account are untouched. Orders with `client_order_id=None` or unparseable ids are treated as `"unknown"` intent and kept.

When `scope="account"`, cancel all qualifying `open`-intent orders on the account regardless of which deployment placed them.

When `scope="global"`, iterate all configured accounts (caller's responsibility to pass the right configs) and apply account-scope cancellation on each.

### Acceptance criteria

- A resting `open`-intent order for a symbol with no open position is canceled
- A resting `sl`-intent order is never canceled regardless of scope
- A resting `tp`-intent order is never canceled regardless of scope
- A resting `open`-intent order where a position exists in that symbol is skipped
- An order with unparseable `client_order_id` is skipped and flagged
- `CancellationResult` accurately counts all four outcome buckets
- `dry_run=True` returns the result without actually canceling anything
- Each cancel emits a structured audit event with `order_id`, `symbol`, `intent`, `reason`
- Each skip emits a structured audit event with reason

---

## Phase 5 — Program Pause Scoped to Deployment

### Current problem

`kill_switch.pause_strategy()` takes `strategy_id` — wrong scope. Two deployments of the same strategy would both be paused. Deployment is the correct runtime scope.

### Changes

```python
# app/core/kill_switch.py

# Add:
def pause_deployment(self, deployment_id: str, triggered_by: str = "user") -> None:
    self._deployment_pauses[deployment_id] = {"paused": True}
    self._log("deployment", deployment_id, "pause", "paused", triggered_by)

def resume_deployment(self, deployment_id: str, triggered_by: str = "user") -> None:
    self._deployment_pauses[deployment_id] = {"paused": False}
    self._log("deployment", deployment_id, "resume", None, triggered_by)

def is_deployment_paused(self, deployment_id: str) -> bool:
    return self._deployment_pauses.get(deployment_id, {}).get("paused", False)

# can_open_new_position() uses is_deployment_paused() — already specified in Phase 3
```

`pause_strategy()` and `resume_strategy()` are kept for backward compatibility but emit a deprecation warning.

### Persistence

`Deployment.status = "paused"` already exists and is the DB source of truth.  
Startup hydration (Phase 2) loads these into `_deployment_pauses`.

### Acceptance criteria

- Pausing deployment A does not affect deployment B of the same strategy
- Pausing an account pauses all deployments on that account regardless of individual deployment state
- `is_deployment_paused("dep-A")` → `True` only for dep-A after `pause_deployment("dep-A")`
- After restart, paused deployments are paused again before governor loop starts

---

## Phase 6 — UI Result Messaging

Every control-plane action (kill, pause, resume, flatten) must return a structured result that the UI renders explicitly.

### API response contract

All control actions must return:

```json
{
  "action": "global_kill | account_pause | program_pause | flatten",
  "scope": "global | account | deployment",
  "scope_id": "account_id or deployment_id or null",
  "positions_untouched": [
    { "symbol": "AAPL", "qty": 100, "side": "long" }
  ],
  "orders_canceled": [
    { "order_id": "...", "symbol": "AAPL", "intent": "open", "reason": "resting entry with no position" }
  ],
  "orders_skipped_protective": [
    { "order_id": "...", "symbol": "AAPL", "intent": "sl", "reason": "protective exit — kept" }
  ],
  "orders_skipped_unknown": [
    { "order_id": "...", "symbol": "AAPL", "intent": "unknown", "reason": "unattributed — kept conservatively" }
  ],
  "errors": [],
  "kill_state_fetch_failed": false
}
```

### UI rules

- If `kill_state_fetch_failed` is `true`, the UI must show an explicit error. It must **never** show a "safe" or "success" state.
- `positions_untouched` must be shown as a positive confirmation: "X positions remain open and protected."
- `orders_canceled` shows what was cleaned up.
- `orders_skipped_protective` shows that protective exits survived — this is the safety proof.
- `orders_skipped_unknown` shows flagged orders that need operator review.
- If any `errors` exist, show them individually — do not aggregate to a generic failure.

### Button label mapping

| Old label | New label |
|---|---|
| HALT ALL | Stop New Opens (Global) |
| Halt Account | Pause Account |
| Halt Deployment | Pause Program |
| Flatten | Close Positions |

---

## Rollout Order

```
Phase 1  client_order_id intent encoding
         → additive only, no existing behavior changes
         → restart paper accounts clean (paper — no migration needed)

Phase 2  Startup kill-state hydration
         → fix global kill rehydration from KillSwitchEvent
         → add deployment pause rehydration

Phase 3  can_open_new_position() unified gate
         → add function to kill_switch.py
         → wire all four entry paths through it
         → remove duplicate checks

Phase 4  Intent-aware order cancellation
         → depends on Phase 1
         → implement cancel_resting_open_orders_without_positions()
         → wire into kill_all, account pause, program pause handlers
         → add dry_run support for testing

Phase 5  Program pause scoped to deployment
         → add pause_deployment() / resume_deployment() to kill_switch
         → deprecate pause_strategy()
         → confirm startup hydration covers it (Phase 2)

Phase 6  UI result messaging
         → update all control action API responses to return CancellationResult
         → update frontend kill/pause/resume dialogs to render the result
```

---

## Hard Rules (Non-Negotiable)

1. No code path may call `alpaca_service.submit_order()` for position-opening orders without first calling `can_open_new_position()`.
2. `cancel_resting_open_orders_without_positions()` must never cancel an order with intent `sl`, `tp`, `close`, or `scale`.
3. Orders with `unknown` intent are always kept and flagged — never canceled.
4. Kill state must be persisted before the cancellation sweep begins. If the sweep fails, the kill state is still active.
5. The UI must not show a success state if the kill-state fetch fails.
6. A program-level resume does not override an account-level pause.
7. An account-level resume does not override a global kill.

---

## Test Acceptance Matrix

| Scenario | Expected result |
|---|---|
| Global kill → open order with no position | Canceled |
| Global kill → sl order | Kept |
| Global kill → tp order | Kept |
| Global kill → open order with existing position | Kept (conservative) |
| Global kill → unknown client_order_id | Kept, flagged |
| Account pause → open order on that account | Canceled |
| Account pause → open order on different account | Untouched |
| Program pause → open order from that deployment | Canceled |
| Program pause → open order from different deployment, same account | Untouched |
| Restart after global kill | `is_globally_killed=True` before governor starts |
| Restart after account pause | Account still paused before governor starts |
| Restart after program pause | Deployment still paused before governor starts |
| Restart after global resume | `is_globally_killed=False` |
| `dry_run=True` on cancellation | Returns result, no orders actually canceled |
| `can_open_new_position()` under global kill | Returns `(False, "global_kill: ...")` |
| `can_open_new_position()` under account pause | Returns `(False, "account_paused: ...")` |
| `can_open_new_position()` under program pause | Returns `(False, "program_paused: ...")` |
| Two deployments same strategy, pause one | Only paused deployment blocked |
| UI: kill-state fetch fails | Shows error, not "safe" |
| UI: protective orders survived | Explicitly listed in result |
