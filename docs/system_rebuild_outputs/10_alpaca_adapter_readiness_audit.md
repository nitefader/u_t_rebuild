Alpaca Adapter Readiness Audit
1. Current Interface Support
Current interfaces already support the correct high-level boundary:

Requirement	Current Support	Assessment
Internal orders created before broker submission	Yes	OrderManager.create_order() owns internal order creation.
Broker adapter receives existing internal order	Yes	BrokerAdapter.submit_order(order: InternalOrder) only accepts an InternalOrder.
Deterministic client order id	Yes	utos-{acct8}-{dep8}-{prog8}-{intent}-{seq} already exists.
Account / deployment / program attribution	Yes	InternalOrder stores account_id, deployment_id, program_id.
Broker result separated from internal order	Partial	BrokerOrderResult exists, but needs richer broker identity and fill fields.
Fake accepted / rejected / partial fill / filled	Yes	FakeBrokerAdapter supports all four.
Ledger update from broker result	Yes	BrokerSync.apply_result() updates OrderLedger.
Governor before order creation	Yes	OrderManager rejects unapproved ExecutionIntent.
No direct Alpaca dependency	Yes	No SDK dependency and no real calls.
No broker fields on InternalOrder	Mostly yes	InternalOrder rejects alpaca_order_id, broker_order_id, broker_status. Good boundary.
The architecture direction is correct: RuntimeOrchestrator → Governor → OrderManager → BrokerAdapter → BrokerSync → OrderLedger.

2. Missing Interface Capabilities
These must be added before a safe Alpaca adapter exists.

Missing Capability	Why It Matters	Required Layer
Broker account snapshot	Governor needs buying power, restrictions, status, pattern day trader flags, trading blocked flags.	Broker adapter + broker sync
Position snapshot / reconciliation	Governor needs true current positions before approving opens.	Broker adapter + reconciliation service
Open order snapshot / reconciliation	Required to prevent duplicate opens and detect missing protective orders.	Broker adapter + order ledger sync
Broker order id mapping	Current broker_reference is too vague for real broker lifecycle.	Broker result / broker order mapping
Fill event model	Partial fills need fill id, price, qty, timestamp, side, liquidity/fees if available.	Broker sync + fill ledger
Average fill price	Internal ledger tracks filled_quantity only.	Order ledger or fill ledger
Cancel order boundary	Needed for flatten, replace, stale order handling, rejected protection cleanup.	Broker adapter
Replace / cancel-replace boundary	Needed for trailing stops and bracket maintenance.	Broker adapter v2
Broker status taxonomy	Alpaca has more than accepted/rejected/partial/filled.	Broker result model
Idempotent submit handling	Retry safety requires client order id lookup before duplicate submission.	Broker adapter + sync
Rate limit / transient error classification	Needed to distinguish retryable vs fatal broker failures.	Broker adapter error model
Order request validation	Must verify order type, TIF, qty, symbol, and side before submit.	Broker adapter boundary
Protective order linkage	Need parent/child relationship for stop/tp/bracket orders.	Internal order model
Limit/stop prices on internal orders	Current InternalOrder has no limit/stop price fields.	Order model
Asset/trading restrictions	Shortability, fractionability, tradability, marginability.	Broker account/asset adapter
Account mode distinction	Paper/live must be explicit and validated.	Broker account context
Market clock/calendar	Alpaca clock may inform broker availability, but not strategy session rules.	Broker adapter metadata only
3. Boundary Risks
These would violate the Trading OS architecture and must be explicitly forbidden:

Alpaca adapter creating InternalOrder directly.
Only OrderManager may create internal orders.

Alpaca adapter approving risk.
Only PortfolioGovernor approves or rejects execution.

Alpaca adapter computing features or signals.
Market data may feed bars, but Feature Engine remains the only computation layer.

Broker account owning internal policy.
Broker account is external truth only: balances, restrictions, positions, orders, fills, buying power.

InternalOrder storing raw Alpaca payloads.
Store normalized fields and broker mapping records, not SDK objects.

Runtime bypassing Governor for opens.
Every new open must pass Governor before order creation.

Sim Lab using OrderManager, BrokerAdapter, or BrokerSync.
Sim Lab must remain simulation-only with SimulatedOrderManager.

Pipeline defaulting to FakeBrokerAdapter in production.
Fine for tests; unsafe as implicit production behavior.

BrokerSync canceling unknown orders blindly.
Unknown broker order intent must fail closed: preserve and flag.

4. V1 Requirements
V1 should be minimal, safe, and paper-first.

Requirement	Decision
Submit market orders	Required
Submit already-created InternalOrder only	Required
Use deterministic client_order_id	Required
Map Alpaca order id externally	Required
Normalize accepted/rejected/partial/filled	Required
Poll/get order status by broker order id or client order id	Required
Apply broker result through BrokerSync only	Required
Preserve account/deployment/program attribution	Required
Fetch broker account snapshot	Required
Fetch positions snapshot	Required
Fetch open orders snapshot	Required
Broker sync freshness timestamp	Required
Reject stale broker sync before opens	Already supported by Governor input
No live mode at first	Paper only for first Alpaca implementation
No bracket orders at first	Use single market order path first
No streaming trade updates at first	Poll/status sync first
V1 must support only the safest order path:

ExecutionIntent → GovernorDecision → InternalOrder → Alpaca submit → BrokerOrderResult → BrokerSync → OrderLedger

5. V2 Requirements
V2 adds operational completeness.

Requirement	Decision
Cancel order	Add adapter method
Cancel all open orders for deployment/account	Add control-plane helper, not raw adapter shortcut
Replace order	Add adapter method
Protective stop/take-profit orders	Add parent/child internal order support
Bracket order mapping	Add normalized order class support
Fill ledger	Add durable normalized fill model
Average fill price	Derive from fill ledger
Trade ledger integration	Convert fills to trades
Trade update streaming	Add broker event stream consumer
Reconciliation job	Compare ledger vs broker truth
Retry policy	Add retryable/fatal error taxonomy
Extended broker statuses	pending_cancel, canceled, expired, replaced, suspended, done_for_day
V2 is where partial fills become production-grade instead of status-only.

6. V3 Requirements
V3 is advanced broker/routing capability.

Requirement	Decision
Multi-account routing	Add account-scoped adapter registry
Live trading enablement	Require readiness gates first
Short selling support	Requires asset restrictions and borrow/shortability checks
Fractional order support	Requires asset capability checks
Options/crypto support	Separate adapter capability matrix
Advanced order classes	OCO/OTO/bracket/trailing
Smart retry queue	Persistent job queue, idempotent submit recovery
Broker outage mode	Runtime pause / stale sync escalation
Multi-broker support	Generalize adapter registry after Alpaca is stable
Audit-grade persistence	DB-backed order/fill/broker event ledgers
7. Required Interface Changes Before Alpaca
Do these before adding the Alpaca SDK.

Expand BrokerAdapter protocol.
Required methods:

submit_order(order: InternalOrder) -> BrokerOrderResult
get_order(order: InternalOrder) -> BrokerOrderResult
list_open_orders(account_id: UUID) -> tuple[BrokerOrderResult, ...]
get_account_snapshot(account_id: UUID) -> BrokerAccountSnapshot
get_positions(account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]
Do not add create_order.

Expand BrokerOrderResult.
Add normalized fields:

broker_order_id
broker_status
submitted_at
updated_at
filled_at
filled_avg_price
remaining_quantity
reject_code
raw_status
Keep raw Alpaca payload out of this model.

Add BrokerAccountSnapshot.
Minimum fields:

account_id
provider
mode: paper/live
buying_power
cash
equity
trading_blocked
account_blocked
pattern_day_trader
shorting_enabled
last_synced_at
Add BrokerPositionSnapshot.
Minimum fields:

account_id
symbol
quantity
market_value
avg_entry_price
side
last_synced_at
Add broker order mapping without polluting InternalOrder.
Use a separate mapping model:

order_id
client_order_id
broker_order_id
provider
account_id
created_at
last_synced_at
Add price fields to internal order model.
Needed before protective/bracket orders:

limit_price
stop_price
parent_order_id
order_class
extended_hours
Add BrokerSync reconciliation methods.
Required:

apply_result(result)
sync_open_orders(account_id)
sync_positions(account_id)
sync_account(account_id)
Add explicit adapter capability metadata.
Minimum:

supports_market_orders
supports_limit_orders
supports_stop_orders
supports_brackets
supports_fractional
supports_shorting
supports_streaming_trade_updates
supports_paper
supports_live
8. Recommended Implementation Sequence
Freeze current boundaries with tests.
Add tests proving:

OrderManager is only internal order creator.
BrokerAdapter cannot create orders.
Governor gates every open.
Sim Lab never imports broker/order pipeline.
Add broker snapshot models.
Add BrokerAccountSnapshot, BrokerPositionSnapshot, and BrokerOrderMapping.

Expand BrokerOrderResult.
Add broker id, broker status, average fill price, remaining qty, and timestamps.

Extend BrokerAdapter protocol.
Add read methods first: account, positions, open orders, get order.

Extend BrokerSync.
Add account/position/order freshness sync without Alpaca.

Extend FakeBrokerAdapter.
Make fake support the new protocol completely.

Add reconciliation tests.
Prove stale broker sync blocks opens and fresh broker snapshots allow opens.

Add Alpaca adapter skeleton only.
No real credentials yet. No network calls in unit tests.

Add paper-only Alpaca integration behind config.
First real path should be paper account only.

Add real submit-order integration.
Market orders only. No brackets. No live.

Add status polling.
Normalize Alpaca statuses into internal statuses.

Add positions/account sync.
Feed Governor with fresh external truth.

Add cancellation.
Required before any live trading.

Add protective/bracket support.
Only after parent/child internal order support exists.

Add live-readiness gate.
Live cannot be enabled until order, fill, cancel, reconciliation, stale sync, and protective order tests pass.