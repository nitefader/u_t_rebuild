import type { ExplainerSection } from "@/components/ui/ExplainerDrawer";

export interface ExplainerEntry {
  pageSlug: string;
  pageTitle: string;
  oneLiner: string;
  sections: ExplainerSection[];
}

/**
 * Per-page Explainer content. Every active route registers an entry
 * here so the right-side help drawer is always one click away. Copy
 * is operator-grade — what the page does, where it fits, what can
 * fail, what the operator should check before trusting it.
 */
export const EXPLAINERS: Record<string, ExplainerEntry> = {
  dashboard: {
    pageSlug: "dashboard",
    pageTitle: "Dashboard",
    oneLiner:
      "Operator home — live platform health, recent signal plans, open positions / orders, and warnings.",
    sections: [
      {
        heading: "What this page reads",
        body: "GET /api/v1/system/streams (Live Stock Market Data hub + per-Account Trade Sync) and the operations overview. Composed `/api/v1/dashboard/summary` is pending Operation Turtle Shell.",
      },
      {
        heading: "What can fail",
        body: "Live stock hub down — banner. All trade syncs down — banner. Stale syncs — warning banner. Backend unreachable — operator-visible error, never silent.",
      },
      {
        heading: "Before trusting it",
        body: "Confirm the system status badge in the top-right shows the expected feed (e.g. SIP) and that the badge dot pulses green. The hub and badge must agree.",
      },
      {
        heading: "Chart Lab pin",
        body: "If you pinned a Chart Lab session, its hub card on this page subscribes to /api/v1/chart-lab/stream for that symbol. The PulseDot on the card pulses green when the WS is open and bars are flowing, info while connecting / awaiting first bar, warn when reconnecting, danger on stream error. Pin lives in localStorage on this browser only — it is not server state.",
      },
    ],
  },

  operations: {
    pageSlug: "operations",
    pageTitle: "Operations",
    oneLiner:
      "Live runtime visibility and control. Global kill, per-Account / per-Deployment pause and flatten. Decision timelines.",
    sections: [
      {
        heading: "What this page reads",
        body: "GET /api/v1/operations/overview every 5s. Plus /api/v1/system/streams for the stream cards. SignalPlan / Evaluation / Governor decision timelines tab in once Operation Turtle Shell wires those routes.",
      },
      {
        heading: "Operator controls",
        body: "Global Kill blocks every Account from opening new positions. Account / Deployment pause blocks new opens scoped to that target. Flatten requests close orders for every open position on the target. Every action is type-name-to-confirm + reason-captured.",
      },
      {
        heading: "What can fail",
        body: "Stale broker sync — Governor blocks new opens. Trade sync down — banner. System recovery in progress — banner. None of these fail silently.",
      },
    ],
  },

  accounts: {
    pageSlug: "accounts",
    pageTitle: "Accounts",
    oneLiner:
      "Broker-connected trading accounts. Provider + mode are pinned at create. Paper and live are not separate runtimes.",
    sections: [
      {
        heading: "What you can do here",
        body: "Add an Account (paper or live), edit credentials inline (encrypted at rest), rename, view detail, delete. Live accounts require type-name-to-confirm at create. From the detail drawer you submit manual orders, see open positions / broker orders / ledger summary, and read the Risk Card.",
      },
      {
        heading: "What this page reads",
        body: "GET /api/v1/broker-accounts and per-Account /api/v1/operations/accounts/{id} every 8s. The Risk Card pulls /api/v1/broker-accounts/{id}/risk-config and /restrictions for Account-scoped sizing posture and operator restrictions.",
      },
      {
        heading: "Before trusting balances",
        body: "Sync Fresh + Trade Sync Connected. If a card shows Sync Stale, broker truth may be lagging — pause new opens until fresh.",
      },
    ],
  },

  strategies: {
    pageSlug: "strategies",
    pageTitle: "Strategies",
    oneLiner:
      "v4 strategy library. Browse saved strategies, open them in the IDE, duplicate or delete.",
    sections: [
      {
        heading: "Authoring flow",
        body: "Click New strategy to open the IDE on a blank canvas, or click Edit on any card to open the head version. The IDE supports Python-style entry expressions, stops, legs, and logical exits. Save posts a new version linked to the same strategy.",
      },
      {
        heading: "Versions",
        body: "Each save appends a new version. The list page shows the head (latest) version for each strategy. Open the IDE with ?id=<version_id> to load any specific version.",
      },
      {
        heading: "Doctrine",
        body: "Strategy owns logic only. Account risk, broker credentials, and final position size do NOT live on the Strategy.",
      },
    ],
  },

  watchlists: {
    pageSlug: "watchlists",
    pageTitle: "Watchlists",
    oneLiner:
      "Saved sources of eligible symbols. Drives Deployment entries. Exits come from Account-owned Positions.",
    sections: [
      {
        heading: "Static vs Dynamic",
        body: "Static is an explicit symbol list. Dynamic Watchlists refresh from saved Screener/template lineage and create auditable snapshots. Refresh changes future entry candidates only; existing Positions remain managed by Accounts.",
      },
      {
        heading: "Snapshots",
        body: "A snapshot freezes the symbol set used by a Deployment at a moment in time. Deployments use the approved/current Watchlist snapshot as entry evidence.",
      },
    ],
  },

  deployments: {
    pageSlug: "deployments",
    pageTitle: "Deployments",
    oneLiner:
      "Running Strategy publishers. Entries come from Watchlists. Exits come from Account-owned Positions scoped to this Deployment.",
    sections: [
      {
        heading: "Lifecycle",
        body: "Draft → Active → Paused → Stopped. Edit structural fields (strategy version, watchlists, accounts) only when not Active. Subscribe / unsubscribe Accounts is allowed at any time.",
      },
      {
        heading: "Doctrine",
        body: "One Deployment publishes one SignalPlan. Multiple Accounts may evaluate independently — each can accept, reject, ignore, defer, or require operator. Deployment never tracks positions itself.",
      },
      {
        heading: "What can fail",
        body: "Deployment Blocked — see runtime status. Pause / Flatten via Operations control commands. Stop is destructive and type-name-to-confirm.",
      },
    ],
  },

  components: {
    pageSlug: "components",
    pageTitle: "Components",
    oneLiner:
      "Catalog of building blocks the platform offers Strategies and the Account decision pipeline.",
    sections: [
      {
        heading: "What this page is",
        body: "Read-only V1 catalog: condition operators, SignalPlan intents, Account participation decisions, doctrine summary. The visual rule editor lands when there is product priority.",
      },
    ],
  },

  providers: {
    pageSlug: "providers",
    pageTitle: "Providers",
    oneLiner:
      "Two buckets: Market Data Providers and AI Providers. Broker Accounts live on their own page. AI is advisory only.",
    sections: [
      {
        heading: "Market Data",
        body: "Add a provider (Alpaca for live + historical, Yahoo for historical). Validate, set role tags (default-for live_streaming / batch_historical / etc.), disable, delete.",
      },
      {
        heading: "AI Providers",
        body: "Advisory only. AI may explain. AI may not approve, reject, size, submit, cancel, or mutate broker truth. The advisory-only badge is enforced.",
      },
    ],
  },

  settings: {
    pageSlug: "settings",
    pageTitle: "Settings",
    oneLiner: "Platform preferences only. Runtime controls live in Operations.",
    sections: [
      {
        heading: "What lives here",
        body: "Default data feed for the platform live stock market data hub, FAKEPACA test stream toggle, Chart Lab default symbol and FAKEPACA pin.",
      },
      {
        heading: "Restart-required",
        body: "The platform live stock hub is keyed at backend boot. Toggling the data feed requires a backend restart for the running hub to re-register on the new feed.",
      },
    ],
  },

  "chart-lab": {
    pageSlug: "chart-lab",
    pageTitle: "Chart Lab",
    oneLiner: "Streaming bar preview surface. Research only — Chart Lab cannot submit broker orders.",
    sections: [
      {
        heading: "Stream",
        body: "WebSocket /api/v1/chart-lab/stream?symbol=… emits bar frames the chart consumes. Auto-detects flat data (FAKEPACA) and renders a line; otherwise candles.",
      },
      {
        heading: "Confidence-building, not required",
        body: "Chart Lab is operator confidence-building. Trading decisions don't need it. Strategy authoring doesn't depend on it.",
      },
    ],
  },

  "sim-lab": {
    pageSlug: "sim-lab",
    pageTitle: "Sim Lab",
    oneLiner:
      "Historical replay sessions through the production runtime spine. Same RiskResolver, Governor, and OrderManager as live — no real broker submission.",
    sections: [
      {
        heading: "What this page reads",
        body: "GET /api/v1/operations/research-evidence?evidence_type=simulation_run. Create-run UI lands when /api/v1/sim-lab is wired.",
      },
    ],
  },

  backtests: {
    pageSlug: "backtests",
    pageTitle: "Backtests",
    oneLiner:
      "Deterministic replay against historical data. Backtests share the runtime's Feature Engine, Signal Engine, RiskResolver, OrderManager — they do not trade.",
    sections: [
      {
        heading: "What this page reads",
        body: "GET /api/v1/operations/research-evidence?evidence_type=backtest_run. Create-run UI lands when /api/v1/backtests is wired.",
      },
    ],
  },

  optimization: {
    pageSlug: "optimization",
    pageTitle: "Optimization",
    oneLiner:
      "Parameter sweeps over the same runtime spine. Output is evidence — not a Strategy version until an operator promotes.",
    sections: [
      {
        heading: "What this page reads",
        body: "GET /api/v1/operations/research-evidence?evidence_type=optimization_run. Create-run UI lands when /api/v1/optimization is wired.",
      },
    ],
  },

  "walk-forward": {
    pageSlug: "walk-forward",
    pageTitle: "Walk-Forward",
    oneLiner:
      "Rolling-window validation. Walk-forward results feed Promotion eligibility evidence.",
    sections: [
      {
        heading: "What this page reads",
        body: "GET /api/v1/operations/research-evidence?evidence_type=walk_forward_run. Create-run UI lands when /api/v1/walk-forward is wired.",
      },
    ],
  },

  "data-center": {
    pageSlug: "data-center",
    pageTitle: "Data Center",
    oneLiner:
      "Historical dataset inspection. Verify the bars Strategies, Backtests, and Sim Lab consume.",
    sections: [
      {
        heading: "What this page is for",
        body: "Operator audit of stored historical bars. The chart renders candlesticks with a stacked volume strip and optional VWAP overlay. Quality badges flag stale or warning datasets.",
      },
      {
        heading: "Doctrine",
        body: "Read-only. Data Center never trades and never resamples on the operator's behalf. If a dataset shows a warning, fix it at the provider before pointing a Strategy at it.",
      },
    ],
  },

  screeners: {
    pageSlug: "screeners",
    pageTitle: "Screeners",
    oneLiner:
      "Saved discovery queries that produce candidate symbol lists. Output feeds Watchlists; Screeners themselves do not trade.",
    sections: [
      {
        heading: "What you can do here",
        body: "Browse and edit saved Screeners. Each Screener defines a universe source, criteria, and a result projection. Run a Screener to produce a candidate list; save it as a static or dynamic Watchlist for Deployment use.",
      },
      {
        heading: "Discovery schedules",
        body: "Dynamic Watchlists can re-run their Screener on a schedule. Schedule changes affect future entry candidates only — they never close existing Positions.",
      },
      {
        heading: "Doctrine",
        body: "Screener output is research evidence. It does not size, gate, or submit. Promotion to Watchlist is an explicit operator action.",
      },
    ],
  },

  "screener-detail": {
    pageSlug: "screener-detail",
    pageTitle: "Screener detail",
    oneLiner:
      "Single Screener — criteria editor, run history, and result table.",
    sections: [
      {
        heading: "Edit and run",
        body: "Tune universe and criteria, preview the resulting expression, then run the Screener. Results render as a sortable table; click any symbol to open the Chart Lab pin.",
      },
      {
        heading: "Save as Watchlist",
        body: "Once results look right, save them as a Watchlist (static or dynamic). Dynamic Watchlists keep the lineage so refreshes recompute against the same Screener.",
      },
    ],
  },

  "execution-plans": {
    pageSlug: "execution-plans",
    pageTitle: "Execution Profiles",
    oneLiner:
      "Reusable order-type, bracket, and runner rules. Deployments bind a versioned Execution Profile.",
    sections: [
      {
        heading: "What lives here",
        body: "Order class (market / limit / bracket / OCO), TIF, post-fill protective placement strategy, runner / partial-take rules. These are the order-expression knobs — what to send to the broker once the Account decides to trade.",
      },
      {
        heading: "Versioning",
        body: "Each save creates a new immutable version. Deployments pin a specific version id; existing Deployments are not affected by edits to a later version until rebound.",
      },
      {
        heading: "Doctrine",
        body: "Execution Profile owns HOW to express an order. Strategy owns the trade structure (entry/exit logic). RiskPlan owns sizing. Account owns the gate.",
      },
    ],
  },

  "risk-plans": {
    pageSlug: "risk-plans",
    pageTitle: "Risk Plans",
    oneLiner:
      "Reusable risk policy. Pinned to research runs, Account defaults, and the live runtime. Every sized SignalPlan reads from a versioned RiskPlan.",
    sections: [
      {
        heading: "What lives here",
        body: "Position-sizing rules, per-trade and per-day risk caps, concentration limits, drawdown disarm, allowed horizons. RiskPlans are versioned and bound at the Account or Deployment level.",
      },
      {
        heading: "Promotion",
        body: "Compare versions side-by-side and promote a new version to Account default. Existing Deployments keep the version they were bound to until rebound.",
      },
      {
        heading: "Doctrine",
        body: "RiskPlan produces final quantity at the RiskResolver boundary. Governor reads the same RiskPlan inputs to decide whether to gate. SignalPlans never embed sizing.",
      },
    ],
  },

  "strategy-controls": {
    pageSlug: "strategy-controls",
    pageTitle: "Strategy Controls",
    oneLiner:
      "Reusable session, timing, and concurrency rules. Deployments bind a versioned Controls version.",
    sections: [
      {
        heading: "What lives here",
        body: "Session windows, max concurrent positions per symbol / per Account, cooldown after exit, daily entry caps, manual override switches. Operator-edited; AI prompt may seed-fill the form but the operator owns final values.",
      },
      {
        heading: "Versioning",
        body: "Each save creates a new immutable version. Deployments pin a specific version id; rebind to pull a newer version into a running Deployment.",
      },
      {
        heading: "Doctrine",
        body: "StrategyControls is an operator-owned configuration layer separate from Strategy logic. Same Strategy can run under tighter or looser Controls without editing the Strategy.",
      },
    ],
  },
};
