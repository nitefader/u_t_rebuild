# COMPLETE ALPACA AGENT INSPECTION

This audit reviews the actual Alpaca integration and broker-control-plane behavior in the current system, not the intended architecture language. The codebase is partially consistent, partially transitional, and partially self-contradictory. The main problem is not a missing feature. The main problem is that broker truth, internal attribution, runtime control, and UI monitoring are not operating off one canonical execution model.

Primary files inspected:

- `backend/app/services/alpaca_service.py`
- `backend/app/services/alpaca_account_stream.py`
- `backend/app/services/alpaca_stream_manager.py`
- `backend/app/services/alpaca_stream_client.py`
- `backend/app/services/position_ledger.py`
- `backend/app/services/deployment_service.py`
- `backend/app/services/account_governor_loop.py`
- `backend/app/services/conflict_resolver.py`
- `backend/app/services/scale_out_service.py`
- `backend/app/core/kill_switch.py`
- `backend/app/api/routes/control.py`
- `backend/app/api/routes/monitor.py`
- `backend/app/api/routes/deployments.py`
- `backend/app/api/routes/accounts.py`
- `backend/app/brokers/alpaca_broker.py`

---

## 1. ORDER LIFECYCLE AUDIT

The intended lifecycle is:

- signal
- order intent
- execution style
- broker submission
- fill
- position update

The actual lifecycle is fragmented into multiple partially disconnected paths.

Observed execution path for opening orders:

- Strategy/runtime logic appears to originate in deployment runners and governor loops.
- `account_governor_loop.py` uses `get_kill_switch().can_open_new_position(account_id, deployment_id)` before entry processing.
- It also applies conflict resolution through `conflict_resolver.check_signal(...)`.
- Risk checks then occur inside the governor loop.
- Broker-facing calls are ultimately funneled through `alpaca_service.py`, usually via `alpaca_broker.py`.
- Order submission in `alpaca_service.place_order()` performs account-status, PDT, and rough buying-power checks before calling Alpaca.
- Fill events arrive through Alpaca trade updates websocket handling.
- Those websocket events are broadcast to the frontend through `alpaca_account_stream.py`.
- There is no demonstrated canonical write-back path from trade update event to durable broker-reconciled internal state.

This is where the lifecycle breaks:

- Signal generation and entry gating are not the same thing as order provenance. The system talks about Program, Deployment, Governor, and Strategy ownership, but the actual order attribution depends on `client_order_id`, and that scheme is inconsistent.
- `alpaca_service.py` defines one `client_order_id` convention: `{prog_abbrev}-{deploy8}-{intent}-{rand8}`.
- `position_ledger.py` defines a different “canonical” convention: `{deployment_id}_{rand8}`.
- The fill router in `position_ledger.py` can only attribute fills that use the underscore format.
- The cancellation sweep in `alpaca_service.py` can only classify intent and deployment if the dash format is used.
- `alpaca_service.place_order()` falls back to a raw UUID when `client_order_id` is missing.
- A raw UUID destroys both deployment attribution and order intent classification.

Where intent is lost or unclear:

- Any caller that omits `client_order_id` causes `alpaca_service.place_order()` to generate a raw UUID. That order becomes unattributed noise from the perspective of internal routing.
- `alpaca_broker.py` exposes broker methods that can be called without a `client_order_id`.
- `place_bracket_order()` also falls back to raw UUID when no `client_order_id` is supplied.
- `place_oco_order()` defaults the intent label to `"sl"` even though OCO is a composite exit structure that can represent take-profit plus stop-loss logic together. That is not a clean intent model.
- Child bracket legs do not receive their own internal intent metadata beyond whatever Alpaca derives from the parent relationship.
- Deployment-scoped UI pages fetch account-scoped orders and positions, which means the lifecycle presentation already loses per-deployment intent before the user even inspects it.

Where `client_order_id` is insufficient:

- It is the only practical attribution handle in the current design, but there is no enforced, repo-wide single format.
- It does not encode symbol in the main runtime format, which makes human/operator debugging harder.
- It is not guaranteed to exist in a meaningful form because the service can generate raw UUIDs.
- It is not centrally validated before submission.
- It is not durably joined to a canonical internal order-intent table before broker submission.
- It is not enough to reconstruct bracket-child semantics, partial-fill sequencing, or stop-leg provenance by itself.

Where duplicate or conflicting orders could occur:

- `conflict_resolver.py` uses internal allocation state, not live Alpaca truth. If internal state is stale, conflicting exposure can slip through.
- Market and account streams are separate systems. There is no demonstrated authoritative reconciliation loop that blocks duplicate intent after disconnect/reconnect.
- Manual order mutation endpoints in `deployments.py` and `monitor.py` operate directly against live broker state without clearly revalidating deployment attribution.
- `monitor.py` exposes deployment-labeled close actions but acts at account scope.
- `accounts.py` exposes flatten and emergency exit directly against Alpaca positions at account scope.
- Missing or malformed `client_order_id` turns the cancellation sweep conservative. That avoids accidental cancellation, but it also preserves stale opening orders that the system can no longer classify.
- There is no demonstrated idempotency layer above Alpaca submission beyond passing `client_order_id`. Since `client_order_id` is inconsistently formed, idempotency is inconsistent too.

Structural problems in the lifecycle:

- The system has an order submission service.
- The system has a fill router.
- The system has a kill switch.
- The system has deployment-level pages.
- The system has account-level pages.
- These are not one execution model. They are adjacent systems with partial overlap.

---

## 2. ORDER INTENT CLASSIFICATION

The system claims to care about these intents:

- open
- close
- tp
- sl
- scale

The actual state of intent classification is incomplete and brittle.

What exists:

- `alpaca_service.py` defines `_VALID_INTENTS = {"open", "close", "tp", "sl", "scale"}`.
- `build_program_client_order_id(...)` can encode that intent.
- `parse_order_intent(...)` can decode intent if and only if the order ID follows the dash-separated 4-part format.
- `cancel_resting_open_orders_without_positions(...)` depends on that parser.

What is broken:

- Intent is not guaranteed on every order.
- There is no canonical internal order-intent entity that exists before broker submission.
- Intent is inferred from a string token embedded in `client_order_id`.
- That string token is only readable for one of multiple competing order ID formats.
- A raw UUID or legacy format downgrades intent to `"unknown"`.

Audit by intent type:

- `open`: Supported in the parser and used by cancellation sweep logic. Still fragile because it depends on a correctly formatted `client_order_id`.
- `close`: Supported as a string label, but many close actions use direct broker close endpoints rather than a canonical intent pipeline.
- `tp`: Exists as a label, but bracket and OCO handling do not expose a robust internal take-profit object model.
- `sl`: Exists as a label, but OCO currently defaults to `"sl"` for a composite protective structure, which is semantically lazy and potentially misleading.
- `scale`: Exists as a label, but scale management is partially implemented through stop replace and partial close flows, not a unified intent graph.

Where intent is missing:

- Any order submitted without explicit `client_order_id`.
- Any bracket order created without caller-supplied ID.
- Any direct close path that relies on Alpaca close endpoints instead of an internal order-intent record.
- Any streamed order/fill event after reconnect where the internal system did not persist the original classified intent first.
- Any UI action that acts on broker order IDs without preserving internal intent metadata.

Where intent could be misclassified:

- OCO orders defaulting to `"sl"` can make an exit structure look like “stop-loss only” when it actually contains both TP and SL legs.
- Partial closes executed through `close_position` can be operationally “scale” but may be represented only as generic close behavior.
- Replace-order flows for protective stops do not necessarily preserve explicit stop intent in an internal state machine.
- Account-level flatten creates close orders without a per-program or per-deployment intent trail.
- Deployment-level manual scale-out can end up looking like generic close behavior to downstream systems if attribution is weak.

Risk of canceling protective orders incorrectly:

- The cancellation sweep is intentionally conservative. That is the one part that avoids the dumbest failure.
- `cancel_resting_open_orders_without_positions(...)` skips `intent != "open"`.
- It also skips orders with unknown intent.
- That protects stop-loss and take-profit orders from naive mass cancellation if their `client_order_id` is unparseable.
- The price of that safety is imprecision. Unknown opening orders are also preserved.
- If a protective order is mislabeled as `"open"` due to bad caller logic, it becomes cancelable.
- If a scale or close order is mislabeled or stripped of intent, the system cannot reason about whether it is protecting, reducing, or increasing exposure.

Core conclusion on intent classification:

- The platform does not own order intent as first-class data.
- It smuggles intent inside `client_order_id`.
- That is not a reliable control-plane design for live trading.

---

## 3. POSITION AND ORDER CONSISTENCY

How positions are read from Alpaca:

- `alpaca_service.get_positions(...)` reads live broker positions through Alpaca.
- `monitor.py` returns account positions for deployment views by calling broker status/positions.
- `deployments.py` returns live Alpaca positions for live deployments.
- `accounts.py` uses broker status and order reads for account activity.

How open orders are reconciled:

- `alpaca_service.get_orders(...)` reads Alpaca open orders.
- `cancel_resting_open_orders_without_positions(...)` compares open orders against live positions.
- This reconciliation is narrow. It exists for cancellation sweeps, not full-state repair.

How internal state matches broker truth:

- It does not consistently.
- Paper deployments use `DeploymentTrade` rows as pseudo-position truth.
- Live deployments often read Alpaca positions directly.
- `position_ledger.py` attempts to reconstruct per-deployment positions from fills.
- `alpaca_account_stream.py` broadcasts events to the UI, not to a durable reconciler.
- `conflict_resolver.py` uses its own in-memory state.
- `account_governor_loop.py` has its own internal notion of open trades and allocation state.

That is not one truth model. That is multiple truths depending on route and mode.

Drift scenarios:

- Live Alpaca position exists, but `conflict_resolver` internal allocation state does not know it yet.
- Fill event arrives, UI sees it, but internal durable deployment state is not updated.
- Order submitted with raw UUID cannot be attributed back to deployment after the fact.
- `position_ledger` expects underscore IDs and therefore cannot route fill events generated with dash-form IDs.
- Deployment monitor page shows account-wide positions that do not belong to that deployment.
- A reconnect happens after missed fills, but no authoritative backfill rebuild occurs.
- A scale-out or manual close changes live quantity, but local scale state and stop-leg size lag behind.
- Paper mode uses internal trade rows while live mode uses broker truth, so feature surfaces and validation assumptions diverge.

Stale state risks:

- Websocket UI can look fresh while durable broker state is not reconciled.
- Account snapshots in `accounts.py` can silently skip refresh when credentials are missing.
- “Connected” and “current balance” surfaces can therefore represent stale or synthetic data.
- `monitor.py` and `deployments.py` appear to be near-real-time, but their scope is account truth presented as deployment truth.
- Reconnect logic exists for streams, but replay/backfill logic does not.

Reconciliation gaps:

- No single reconciliation job was identified that says: “broker is source of truth, now repair all local state.”
- No durable order ledger was identified that stores broker order ID, parent/child relationship, internal intent, deployment attribution, and latest broker status together.
- No durable fill ledger was identified as the canonical live-trading record.
- `position_ledger.py` exists but appears isolated. Search results show no active integration points consuming it.
- The fill router is effectively dead weight if nothing calls it.

Specific hard failure:

- `position_ledger.py` explicitly states that every order uses `{deployment_id}_{rand8}`.
- `alpaca_service.py` explicitly uses `{prog_abbrev}-{deploy8}-{intent}-{rand8}`.
- Both cannot be canonical at the same time.
- One of these files is lying.

---

## 4. WEBSOCKET + STREAMING AUDIT

There are two distinct streaming domains:

- account/trade update streaming
- market data streaming

### Account / order / fill streaming

What it does today:

- `alpaca_account_stream.py` starts a `TradingStream` consumer.
- It chooses one account only.
- It prefers a hardcoded named account: `Paper1_OtijiTrader_UseTest`.
- If that account is not found, it falls back to the first account with credentials.
- It forwards trade updates to the frontend websocket manager.
- It maps `fill` and `partial_fill` to `order_fill`.
- It maps `canceled`, `expired`, and `rejected` to `governor_event`.
- Everything else is still forwarded as `order_fill`.

What is wrong with that:

- One stream for one chosen account is not a platform-grade multi-account control plane.
- It is a convenience stream.
- A live trading platform cannot pretend all active broker accounts are one stream.
- The event mapping is sloppy. “Everything else becomes order_fill” is garbage classification.
- There is no durable write-back from stream event to internal canonical state.
- There is no deduplication layer.
- There is no replay or catch-up after disconnect.
- There is no verified sequencing protection.

Race conditions:

- REST polling routes can read broker state while websocket events for the same order are still in flight.
- UI can receive a fill event before internal allocation/risk state mutates.
- A cancel/replace operation can race with fill events and leave the UI or internal stop-order references behind reality.
- An account reconnect can occur after missed order state changes, but there is no evidence of a required post-reconnect broker sweep to normalize truth.

Dropped events:

- Any disconnect during Alpaca trade updates can lose events.
- The code reconnects, but reconnect alone does not recover missed updates.
- No backfill query was identified that reloads order history or fills since last timestamp.
- Missing events mean local state repair depends on ad hoc user route refreshes or later broker snapshots.

Duplicate events:

- Reconnect plus lack of dedupe can surface duplicate UI events.
- If a future backfill is added naïvely, duplicates will get worse because there is no canonical idempotent event application layer now.

Stale UI risk:

- High.
- The websocket stream is a UI push layer, not a broker-reconciliation engine.
- A stream disconnect can leave the frontend looking quiet rather than explicitly stale unless the UI separately detects freshness loss.
- Trade update stream chooses one account, so other accounts can be stale while the UI still looks “live.”

### Market data / bar streaming

What it does today:

- `alpaca_stream_manager.py` manages bar subscriptions per deployment.
- It dynamically reconciles symbol subscriptions.
- It reconnects with exponential backoff.
- It publishes bars into a market data bus.

What it does not do:

- It does not backfill missed bars after reconnect.
- It does not verify event continuity across reconnect boundaries.
- It does not store last-seen sequence or broker cursor.
- It does not prove bar completeness for strategy logic.

Market-data race conditions:

- A deployment runner can continue after reconnect without a guaranteed historical gap repair.
- Strategies depending on bar continuity can make decisions on incomplete context.
- If a bar gap occurs, backtest parity with live decisions is broken immediately.

Overall streaming verdict:

- Reconnect exists.
- Reliability semantics do not.

---

## 5. PARTIAL FILL + BRACKET ORDER HANDLING

### Partial fills

What exists:

- `alpaca_account_stream.py` forwards `partial_fill`.
- `position_ledger.FillEvent.from_alpaca_event(...)` accepts both `fill` and `partial_fill`.
- The frontend already acknowledges that partial fills may leave remaining quantity and protective orders working.

What is broken or ambiguous:

- There is no proven canonical partial-fill state machine that ties broker order status, cumulative filled quantity, remaining quantity, stop-leg size, and deployment exposure together.
- `FillEvent.from_alpaca_event(...)` derives quantity from `event["qty"]` or `order["filled_qty"]`.
- Depending on Alpaca payload semantics, that can represent per-event quantity or cumulative filled quantity.
- If treated wrong, the ledger can double count or undercount.
- Because the ledger is not clearly wired into the live reconciliation path anyway, even a correct parser would not save the platform.

Incorrect position sizing after partial fills:

- Scale stop replacement logic depends on current remaining quantity being correct.
- If a partial fill is missed, delayed, or misread as cumulative versus incremental, replacement quantities can be wrong.
- Wrong replacement quantity on a stop is not a cosmetic bug. It changes the actual live protection size.

### Bracket parent/child relationships

What exists:

- `place_bracket_order()` uses Alpaca native bracket format. That part is correct.
- Parent order carries `client_order_id`.
- Alpaca manages bracket legs.

What is weak:

- The system does not persist a strong internal parent-child order graph before submission.
- Child-leg attribution depends on broker behavior and later reads, not an internal source-of-truth table.
- If downstream logic relies on `client_order_id`, it is only clearly present on the parent.
- Manual stop replacement flows operate on specific order IDs but do not obviously maintain a canonical relational model between entry, stop, tp, and scale state.

Stop-loss and take-profit persistence risks:

- On reconnect, the system has no demonstrated bracket graph rebuild step.
- If UI/manual actions mutate stops, internal state can drift from Alpaca leg IDs.
- If a bracket partially fills or closes in stages, there is no explicit authoritative repair routine to validate that the remaining protective leg matches remaining exposure.

Orphaned orders:

- A partial close plus failed stop resize can leave oversized or stale protective orders.
- A reconnect without backfill can leave the platform unaware of which protective leg is still live.
- An order with unknown intent is intentionally preserved by cancellation sweep, which is safer than blind cancellation, but it also means stale orphaned opening orders can remain.

Incorrect UI representation:

- Deployment pages can show account-wide positions/orders and imply deployment ownership.
- Partial-fill status can therefore be visually correct at account level but wrong at deployment level.
- Child bracket legs are not modeled as first-class UI entities with provenance. They are just broker objects read back later.

Bottom line on partial fills and brackets:

- Native bracket submission is the one piece that is not amateur hour.
- Everything after submission is weaker than it needs to be.

---

## 6. CONTROL PLANE ENFORCEMENT

Required control surfaces:

- global kill
- account pause
- program pause
- flatten behavior

### Global kill

What works:

- `control.py` persists global kill state.
- It runs a cancellation sweep across enabled accounts.
- The sweep is intent-aware and tries to preserve protective/reducing orders.

What is weak:

- The runtime still contains legacy and modern gating side by side.
- Some code paths use `can_open_new_position(account_id, deployment_id)`.
- Some code paths still use `can_trade(account_id, strategy_id)`.
- Those are not equivalent.

### Account pause

What works:

- `accounts.py` and `control.py` can mark account scope as killed/paused.
- `kill_switch.py` supports account-level kills.

What is weak:

- Not every order/position mutation path clearly routes through the same gate.
- Account-level flatten and emergency exit directly call `close_all_positions(config)`.
- That may be operationally acceptable for emergency liquidation, but it still means the broker mutation path is route-owned, not governor-owned.

### Program pause

What works:

- `kill_switch.py` has deployment pause.
- `control.py` pause-deployment route uses deployment scope and performs deployment-scoped cancellation sweep.

What is weak:

- `monitor.py` still enforces with legacy `can_trade(account_id, strategy_id)`.
- `deployment_service.py` also still uses legacy `can_trade`.
- Strategy-level kill/pause is deprecated but still alive in the kill switch.
- The repo is in a mixed old/new state and therefore control semantics are split.

### Flatten behavior

What exists:

- `accounts.py` exposes flatten and emergency exit at account scope.
- `monitor.py` exposes deployment-labeled close-position and close-all.
- `deployments.py` exposes scale-out and stop-modification actions.

What is wrong:

- Deployment close-all in `monitor.py` calls broker `close_all_positions()` for the account after a legacy kill-switch check. That is account-level liquidation masquerading as deployment-level control.
- Deployment position and order endpoints are account-scoped for live Alpaca data, so deployment-level flatten cannot be trusted as truly deployment-scoped unless there is ironclad attribution. There is not.
- Manual scale-out and stop-replace controls in `deployments.py` appear to act directly against live Alpaca order/position state without obvious governor-approval enforcement.

Verify: new opens are blocked correctly

- Sometimes.
- `account_governor_loop.py` uses `can_open_new_position`.
- `control.py` resume-deployment checks `can_open_new_position`.
- `deployment_service.py` and `monitor.py` still use `can_trade`.
- Therefore new opens are not blocked through one canonical enforcement path. The answer is not “yes.” The answer is “inconsistently.”

Verify: protective orders are preserved

- The cancellation sweep tries to preserve them by skipping intents other than `open`.
- It also conservatively preserves unknown intents.
- That is good as a safety default.
- It is still vulnerable to bad intent metadata or missing provenance.

Verify: cancel logic is intent-aware

- Yes, in `cancel_resting_open_orders_without_positions(...)`.
- No, as a platform-wide statement, because intent awareness depends on `client_order_id` parsing and there is no universal guaranteed format.

Unsafe behavior:

- Legacy and current kill-switch APIs both exist.
- Deployment-labeled control routes act on account-wide broker truth.
- Direct broker close/replace operations exist outside a single governor approval choke point.
- Per-deployment liquidation is not truly enforced at per-deployment scope for live Alpaca positions.

Inconsistent enforcement paths:

- `account_governor_loop.py` uses `can_open_new_position`.
- `deployment_service.py` uses `can_trade`.
- `monitor.py` uses `can_trade`.
- `accounts.py` flatten/emergency exit bypass per-deployment governor reasoning entirely.
- `deployments.py` manual stop/scale actions appear route-owned.

This is the exact kind of split-brain control plane that behaves fine in demos and fails under stress.

---

## 7. FAILURE MODES

### API failures

What happens today:

- `alpaca_service.py` usually returns `{"error": ...}` rather than raising a rich typed exception through the stack.
- Routes and callers may then decide how much meaning to preserve.
- Some account snapshot failures are only logged.

What SHOULD happen:

- Order submission failures should fail closed for opening orders.
- Protective-order maintenance failures should escalate immediately and mark the affected deployment/account degraded.
- Operator surfaces should show exact broker error, last successful sync time, and whether internal state is now untrusted.

### Websocket disconnects

What happens today:

- Account stream and market-data stream reconnect with exponential backoff.
- No authoritative backfill/reconciliation step was found after reconnect.

What SHOULD happen:

- Fail closed for new automated opens if trade-update continuity is required for safe attribution and stop management.
- On reconnect, force broker backfill:
- reload open orders
- reload positions
- reload recent fills/order activities since last confirmed timestamp
- repair internal state before marking stream healthy

### Stale broker sync

What happens today:

- Multiple routes read broker state on demand.
- Some account snapshots silently skip when credentials are missing.
- Deployment and monitor pages can present account truth as deployment truth.

What SHOULD happen:

- Broker truth should remain authoritative.
- Every consumer should know the freshness timestamp and provenance of what it is rendering.
- If sync freshness exceeds threshold, the system should explicitly degrade, not quietly continue acting confident.

### Invalid credentials

What happens today:

- Some endpoints return config/validation errors.
- Some account snapshot paths silently skip and return no refresh.
- The account stream simply sleeps if no credentials are found.

What SHOULD happen:

- Invalid or missing live credentials should fail closed for trading.
- Account UI should mark broker disconnected, not “kind of connected but stale.”
- No silent skip for a broker-backed account that is expected to sync.

### Rejected orders

What happens today:

- Account stream maps `rejected` to `governor_event` for UI broadcast.
- `alpaca_service` returns error payloads on REST rejection.
- No canonical rejection ledger or durable retry/repair state machine was identified.

What SHOULD happen:

- A rejected opening order should not remain as pending internal exposure.
- Protective-order rejection should trigger urgent degradation because the position may now be naked.
- Rejections should be persisted with cause, timestamp, deployment, account, and related position/order graph.

### Rate limiting

What happens today:

- There is a local bucket limiter in `alpaca_service.py`.
- Exceeding it raises `AlpacaRateLimitError`.
- There is no robust Alpaca 429-aware exponential retry for REST operations.

What SHOULD happen:

- Controlled exponential backoff with bounded retries for safe idempotent reads.
- Very careful retry semantics for writes.
- Explicit operator telemetry when the platform is rate limited.

### Partial success during kill / cancel sweeps

What happens today:

- Cancellation sweep aggregates results and keeps going.
- Flatten returns both orders and errors.

What SHOULD happen:

- Partial success should explicitly move account/deployment state to degraded.
- Operators should know exactly which orders were canceled, skipped, or failed.
- Protective-order preservation should be reported clearly, not inferred.

### Broker/internal divergence

What happens today:

- No single automatic repair path was found.
- Divergence is handled opportunistically through route reads and manual inspection.

What SHOULD happen:

- Fail closed for new opening automation when divergence is detected beyond tolerance.
- Trigger immediate broker reconciliation.
- Persist divergence incidents as audit events.

---

## 8. PROVENANCE AND SOURCE OF TRUTH

Which system is the source of truth?

Current real answer:

- broker for live balances, positions, and open orders
- database for deployments, accounts, approvals, and paper trades
- websocket event stream for UI freshness
- in-memory resolver/governor state for some runtime conflict logic
- `position_ledger.py` for a hypothetical fill-based deployment ledger that is not clearly integrated

That is not a source-of-truth model. That is a collage.

Broker:

- Alpaca is the only credible source of truth for live positions, open orders, fills, PDT state, buying power, and broker restrictions.
- The code often treats broker reads that way.
- It does not consistently propagate broker truth into one durable internal model.

Internal state:

- Internal runtime logic still makes decisions from in-memory state.
- `conflict_resolver.py` is not broker-authoritative.
- `account_governor_loop.py` maintains runtime-local notions of open trades and allocation state.

Cache / websocket:

- Frontend websocket stream is just a transport.
- It should not be allowed to become implied truth.
- Right now it risks doing exactly that.

Ambiguity:

- Live deployment position pages use Alpaca account positions directly.
- Paper deployment position pages use `DeploymentTrade` rows.
- The same UI concept means different underlying truth by mode.
- That makes cross-mode consistency analysis weaker by default.

Conflicting states:

- Broker can say one thing.
- In-memory conflict resolver can say another.
- UI can still show a recent event without canonical state repair.
- `position_ledger.py` can believe a fill belongs to nobody because the ID format changed.

Missing timestamps:

- Many returned objects include broker timestamps from Alpaca formatting.
- There is no visible, mandatory “last broker reconciliation timestamp” across control-plane surfaces.
- There is no mandatory “last trade-update event applied” timestamp that gates trust.
- There is no obvious “last full order/position consistency audit” timestamp.

Core provenance problem:

- The platform has not decided whether it is broker-led with internal derived state, or internal-led with broker synchronization.
- In live trading, it must be broker-led.
- The current implementation still behaves like both, depending on the file.

---

## 9. ALPACA-SPECIFIC RISKS

### PDT violations

Current handling:

- `alpaca_service.place_order()` checks `day_trade_count`, `pattern_day_trader`, equity, and `time_in_force == "day"`.

Problems:

- The check is simplistic.
- It is not a full strategy/session-aware day-trade prevention model.
- It assumes a narrow interpretation and leaves edge-case brokerage behavior to Alpaca.
- It lives at submission time instead of existing as a broader operator-visible restriction surface.

### Insufficient buying power

Current handling:

- Market buys only require buying power to be greater than zero.
- Limit buys compare estimated cost against buying power.

Problems:

- Market-order buying power logic is crude.
- It does not estimate actual exposure robustly.
- It does not model bracket-leg implications or post-fill protective structure changes.
- It is not enough for live safety.

### Market hours violations

Current handling:

- No comprehensive market-hours enforcement model was identified in the Alpaca submission layer itself.
- Some logic may exist elsewhere in strategy controls, but live Alpaca-specific order-eligibility enforcement is not clearly centralized here.

Problems:

- Extended-hours compatibility varies by order type.
- The platform should not rely on Alpaca rejections as its main market-hours validator.
- Missing explicit order-type plus session compatibility checks create avoidable rejected orders and confused operators.

### Order type incompatibilities

Current handling:

- Native bracket support exists.
- OCO support exists.
- Replace-order exists.

Problems:

- There is no unified order-capability matrix that says which order types are valid for:
- live vs paper
- regular vs extended hours
- bracket vs non-bracket
- replaceable vs non-replaceable states
- scale-out scenarios

### Long/short conflict constraints

Current handling:

- The architecture says the Governor must prevent conflicting long/short positions.
- The actual live conflict path relies partly on `conflict_resolver.py`, which is internal-state based.

Problems:

- Without broker-authoritative reconciliation, Alpaca’s “no conflicting positions” constraint can still be violated operationally by stale internal state or parallel flows.

### Bracket-leg management

Current handling:

- Alpaca native bracket submission is used.

Problems:

- Child-leg attribution and persistence are not modeled strongly enough internally.
- That is dangerous when doing manual replace flows, scale-out, or reconnect recovery.

### Cancel/replace semantics

Current handling:

- `replace_order()` exists and is used by scale-out/manual stop management.

Problems:

- Replace semantics are not tied to a canonical order graph.
- If the referenced order ID is stale or already filled/canceled, the local state machine can become nonsense quickly.

### Multi-account live operations

Current handling:

- Account trade stream chooses one account.

Problems:

- That is fundamentally inadequate for a multi-account Alpaca platform.
- It guarantees blind spots.

---

## FINAL VERDICT

### Top 5 critical risks in the Alpaca integration

1. `client_order_id` is not canonical. The system has competing attribution schemes and a raw-UUID fallback. That breaks deployment attribution, intent classification, cancellation precision, and any hope of reliable fill routing.

2. Trade-update streaming is UI-facing, not state-authoritative. Fills and order-state events are broadcast to the frontend, but no durable, broker-reconciled live order/fill ledger was identified.

3. Control-plane enforcement is split between old and new gates. `can_open_new_position(...)` exists, but important paths still use legacy `can_trade(...)`, and several broker mutation routes operate outside a single governor choke point.

4. Deployment-level live views and controls are not truly deployment-scoped. They often read or act on account-wide Alpaca truth while presenting deployment labels, which is a recipe for wrong operator decisions.

5. Reconnect logic exists without continuity repair. Streams reconnect, but there is no demonstrated mandatory backfill/reconciliation pass for missed orders, fills, positions, or bars.

### What MUST be fixed before live trading is safe

1. Enforce one and only one `client_order_id` format across the platform, with mandatory fields for deployment attribution and explicit intent. Remove raw UUID fallback for platform-submitted orders.

2. Create a canonical live-trading order/fill provenance model:
- internal order intent record before submission
- broker order ID
- parent/child relationship
- deployment/program/account attribution
- latest broker status
- timestamps for submitted, acknowledged, partially filled, filled, canceled, replaced, rejected

3. Make broker truth authoritative and implement mandatory reconciliation:
- on startup
- on reconnect
- after critical failures
- after manual control actions

4. Replace all legacy kill-switch enforcement paths with one gate model and force all opening-order submissions through it. Then separately define allowed close/protective actions under kill/pause/flatten semantics.

5. Remove fake deployment scoping over account-wide broker actions. If the platform cannot prove broker objects belong to one deployment, it must not expose those controls as deployment-specific.

6. Wire trade-update events into durable state application, not just websocket broadcast.

7. Add multi-account account-stream handling. One chosen account stream is not acceptable for a real control plane.

### What can wait

- Better operator dashboards once the underlying state model is trustworthy.
- More sophisticated market-hours/order-capability policy tables after provenance and reconciliation are fixed.
- Nicer UI explanations of partial fills and bracket legs after the order graph is made real.
- Advanced scale-out ergonomics after stop/position synchronization is made reliable.

The core issue is simple: the platform does not yet have a single canonical live execution model for Alpaca. It has pieces of one. That is not enough. Until attribution, reconciliation, and enforcement are unified, live trading safety is conditional and fragile.
