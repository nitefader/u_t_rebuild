# STRUCTURAL PROBLEMS AUDIT

This audit is about structural failure.

It is not a feature list.

It is not a roadmap.

It is a direct statement of why the platform feels stitched together instead of designed as one coherent system.

## 1. Naming Problems

- `Account`, `Broker Account`, `Account Monitor`, and `accounts` all refer to different layers of the same concept and the system does not enforce the distinction.
- `Portfolio Governor`, `Account Governor`, `Governor`, `Strategy Governor`, and `Strategy Controls` are all active names in the codebase and docs. That is not terminology drift. That is taxonomy failure.
- `Strategy Governor` is dead wrong if the canonical concept is `Strategy Controls`. The repo still uses both.
- `governor.py` handles account-level portfolio governor behavior, while `strategy_governors.py` handles strategy controls. Two unrelated concepts share the same word.
- `Program`, `TradingProgram`, and `ProgramBacklogItem` collide. One is a deployable trading artifact. One is just a planning ticket. Same word, different universe.
- `Deployment` is used as a runtime trading instance and also as the persistence stand-in for the portfolio governor. That name is carrying two jobs and it breaks mental models.
- `Risk Profile` sounds canonical, but `Account` still owns inline risk fields. The name says one thing. The data model says another.
- `Execution Style` exists, but `execution_policy` still exists on `TradingProgram`. The system literally has two names for execution ownership because it never fully committed.
- `Watchlist`, `Universe`, `SymbolUniverseSnapshot`, `watchlist_subscriptions`, and `live_universe_*` all refer to overlapping symbol-set concepts with no stable naming hierarchy.
- `Backtest`, `Run`, `BacktestRun`, and `RunHistory`, and `RunDetails` are inconsistently scoped. The user is forced to guess whether a "run" means backtest only or any execution artifact.
- `Sim Lab`, `Simulation`, `SimulationSession`, and `BacktestStepper` show the same underlying truth: simulation is real enough to matter, but naming still treats it like a toy layer.
- `Services` is vague garbage. The page mixes data-service and AI-service records behind a single generic label.
- `Logs`, `Logs & Alerts`, `Issues`, `Roadmap`, `Journeys`, and `Feature Build` are all packed into `LogsPanel`. The title lies.
- `Monitor`, `Live Monitor`, `Deployment Manager`, `Account Monitor`, and `Account Governor` all claim authority over active runtime state.
- `security` route means credential management, not actual security posture. That is a misleading label.
- `lab` route points to `OptimizationLab`, while `simulation` points to `SimulationLab`, and `charts` points to `ChartLab`. The naming is hobby-project loose for a platform that claims production-grade intent.
- `services/data` and `services/ai` are sub-routes of `Services`, but there is also `/data` which means cached market data. Same word family, different domain.
- `control` route family handles kill/pause/flatten semantics, while `governor` handles account governance, while `accounts` also exposes control-ish actions. The naming split hides enforcement boundaries.
- `promote to paper`, `deploy`, `allocation`, `start deployment`, and `bootstrap governor` are all adjacent actions that do not map cleanly to one lifecycle vocabulary.
- The platform exposes canonical architecture docs with clean names and live code with dirty names. That gap is itself a naming problem.

## 2. Page Overlap Problems

- `AccountMonitor` and `AccountGovernor` overlap heavily. Both pages want to be the control center for account-scoped runtime management.
- `DeploymentManager` and `AccountGovernor` overlap heavily. Both pages deal with starting, pausing, stopping, viewing trades, and understanding deployment state.
- `LiveMonitor` overlaps with both `AccountMonitor` and `DeploymentManager`. All three pages are trying to answer "what is running right now?"
- `BacktestLauncher`, `RunHistory`, and `RunDetails` are coherent as a trio. The problem is that `OptimizationLab`, `SimulationLab`, and `TradingPrograms` can all launch or redirect into the same flows, creating lateral sprawl instead of a straight workflow.
- `SimulationLab` and `ChartLab` overlap on data visualization, indicator inspection, and exploratory analysis.
- `SimulationLab` and `Backtest` overlap on validating strategy behavior against market data.
- `OptimizationLab` overlaps with backtest analysis, deployment readiness, and program creation. It is not just optimization anymore.
- `StrategyCreator`, `StrategyEditor`, `StrategyDetails`, and `Strategies` form a reasonable CRUD set, but `TradingPrograms` also acts like a composition editor over strategy-adjacent objects, so strategy-authoring intent bleeds into program assembly.
- `RiskProfiles`, `ExecutionStyles`, `StrategyControls`, and `WatchlistLibrary` are all component-library pages, but `TradingPrograms` duplicates browse/select/compose workflows for all of them.
- `Dashboard` duplicates onboarding steps, quick actions, deployment summary, account summary, kill status, and recent runs. It is trying to compensate for the rest of the nav being unclear.
- `LogsPanel` is not one page. It is multiple product-management and audit pages disguised as one tabbed screen.
- `Services` overlaps with `CredentialManager`. Both touch credentials/configuration. One is account-scoped, the other is provider-scoped. That distinction is not obvious in the nav.
- `DataManager` overlaps with `ChartLab` because one page downloads data and the other page immediately depends on that same cache without sharing a clear workflow shell.
- `EventCalendar` overlaps with strategy authoring because event filters live conceptually with strategy controls, but the page sits out as its own island.
- `TradingPrograms` overlaps with `Deployments` because it is not just configuration anymore; it includes actions that kick users toward simulation, backtest, and deployment.
- The route aliases prove the overlap is not accidental:
- `/deployments`, `/portfolio-governors`, and `/governor` all hit the same page component.
- `/broker-accounts` and `/accounts` both hit `AccountMonitor`.
- `/governors` and `/strategy-controls` both hit the same component.
- Multiple labels, same page, different implied meanings. That is how users stop trusting navigation.

## 3. Backend / Domain Problems

- The platform has a canonical domain model on paper and a split-brain domain model in code.
- `Portfolio Governor` is not a first-class ORM entity. It is serialized from `Deployment`. That is a structural defect, not a naming nit.
- `Deployment` owns runtime lifecycle, promotion lineage, governor status, risk link, poll config, collision snapshot, daily lockout state, and observability. It is doing too much.
- `AccountAllocation` also owns runtime-ish lifecycle state, promotion state, capital allocation, conflict resolution, and broker mode. That means the system has two competing runtime units.
- `TradingProgram.execution_policy` duplicates `ExecutionStyle`.
- `Account` inline risk fields duplicate `RiskProfile`.
- `StrategyVersion.config` still carries fields that belong to strategy controls, risk, and execution when resolved overlays are applied. The versioned artifact is not clean.
- `resolve_program_to_config()` explicitly flattens Strategy Controls, Execution Style, and Risk Profile back into one config blob. That function is a domain-boundary destroyer.
- `duration_mode` exists on `StrategyVersion`, `StrategyControls`, and `TradingProgram`. Duplicated state across domain layers is a rot source.
- `Watchlist`, `WatchlistMembership`, `watchlist_subscriptions`, and `SymbolUniverseSnapshot` represent a half-finished migration from watchlist-centric to universe-centric modeling.
- `EventFilter` and `StrategyControls` both own event/earnings blackout behavior. Ownership is split because the system never chose one home.
- `RunMetrics.walk_forward` and `ValidationEvidence.walk_forward` duplicate research evidence.
- `Trade` and `DeploymentTrade` are parallel models with overlapping fields and no clear shared abstraction.
- Orders are central to the platform, but there is no first-class persistent `Order` entity. The system relies on broker responses, service dataclasses, and monitor responses. That is weak for auditability and dangerous for control-plane reasoning.
- `DataService` mixes data credentials and AI credentials. Those are not the same domain.
- The `data.py` route owns both market-data fetch/cache endpoints and watchlist endpoints. That is backend leakage and sloppy module boundaries.
- `governor.py` owns governor routes and also account risk-profile attach/detach routes. That is another module-boundary leak.
- `monitor.py` exposes deployment detail and also has `/accounts`-related runtime endpoints. Again: blurred ownership.
- There are too many service seams with overlapping concerns:
- `deployment_service`
- `governor_service`
- `account_governor_loop`
- `conflict_resolver`
- `position_ledger`
- `alpaca_service`
- `paper_broker`
- `promotion_service`
- The problem is not having many services. The problem is that the repo does not make their authority boundaries obvious.
- `alpaca_service` is supposed to be the only broker caller. Good. But enforcement depends on convention plus scattered call sites, not a brutally enforced boundary contract.
- The feature system is architecturally central but still only partially canonical. There is a `FeatureSpec`, `FeatureRequirement`, and `FeaturePlan`, but strategy config still relies heavily on raw string refs and ad hoc config shape.
- Simulation is important enough to have a full API, WebSocket loop, and feature-plan preview, but it has no durable model. That means it is product-critical but structurally second-class.
- The system keeps inventing JSON sidecars instead of proper aggregates:
- `config`
- `parameters`
- `poll_config`
- `promotion_review_payload`
- `collision_state_snapshot`
- `objective_config`
- `constraints`
- `covariance_model`
- This is flexible in the short term and corrosive in the long term.

## 4. Workflow Problems

- The platform claims a clean lifecycle: Backtest -> Paper -> Live. The actual workflow is not clean.
- The user can start from Strategies, Programs, Backtest, Simulation, Optimization Lab, Dashboard quick actions, or Account Governor hot-add. Too many entry points means no canonical path.
- Program creation is not naturally downstream of strategy validation. It is a separate composition exercise that the user has to rediscover.
- Backtest success does not map cleanly to program readiness.
- Program readiness does not map cleanly to deployment readiness.
- Deployment readiness does not map cleanly to governor allocation readiness.
- Promotion exists in both deployment-centric and program-allocation-centric forms. That is a circular flow waiting to happen.
- The user can create a strategy with embedded risk/execution-ish config, then separately create Strategy Controls, Risk Profile, Execution Style, and Watchlist, then separately compose a Program, then separately allocate it, then separately manage deployments. That is too many steps for one trading thesis.
- The page links prove this fragmentation:
- `RunDetails` links to Programs
- Programs links to Simulation and Backtest
- Programs links to Deployments
- BacktestLauncher asks for programs
- OptimizationLab pushes to deployments
- Dashboard pushes to deployments
- This is not one flow. It is a loop maze.
- There is no single "Build -> Validate -> Promote -> Operate" shell.
- First-time setup is split across Accounts, Security, Services, Data, Strategy pages, and maybe Watchlists depending on how the user builds the thesis.
- The system expects users to understand component composition before it gives them a stable operational workflow.
- Promotion semantics are overloaded:
- promote strategy version
- promote run to paper
- promote deployment to live
- promote allocation to live
- The user should not have to decode which artifact is being promoted each time.
- Account setup and governor bootstrap are separate actions. That means account readiness is not self-contained.
- Data dependency is underexplained. Chart Lab depends on cached data. Backtests fetch data dynamically. Simulation can auto-resolve providers. Different flows, different assumptions.
- There are too many prerequisite loops:
- create account before deployment
- attach risk profile after account if you want reusable risk
- create services if you want shared credentials
- create watchlists if you want program symbol resolution
- create program if you want composition purity
- or skip program and run direct backtest/simulation from strategy version
- That is not guided progression. That is architectural exposure dumped on the user.
- Circularity is built into the flow:
- Strategy -> Backtest -> Program -> Backtest with program -> Deployments -> Monitor -> modify strategy -> new version -> backtest again
- The loop is fine. The problem is that the system does not clearly mark which artifact is canonical at each step.

## 5. Runtime Consistency Problems

- Backtest, simulation, paper, and live are not guaranteed to behave the same way, and the codebase openly admits that.
- Backtest is durable and metric-heavy.
- Simulation is in-memory and stepper-driven.
- Paper/live are deployment/broker-driven.
- Those are three separate execution stacks pretending to be one continuum.
- Backtest uses `BacktestEngine`.
- Simulation uses `BacktestStepper`.
- Paper/live use `paper_broker`, `deployment_service`, runtime loops, broker APIs, and monitor routes.
- If the same strategy is evaluated by different engines, drift is always a risk.
- Feature computation is still at risk of inconsistency:
- raw strategy refs
- preview-based feature planning
- runtime indicator cache/cerebro systems
- backtest-time indicator computation
- simulation-time stepper preparation
- That is too many places for subtle divergence.
- Multi-timeframe behavior is especially exposed to drift because alternate timeframe fetch and indicator preparation exist in backtest orchestration but runtime feature planning is still evolving.
- Data-provider behavior can differ across modes:
- backtest provider recommendation
- simulation auto-resolution
- data manager fetch rules
- chart lab cache dependency
- That means the same user intent can pull different data paths.
- Date-range behavior differs:
- simulation clamps date ranges
- backtest explicitly does not clamp
- That alone can create "same strategy, same timeframe, different result shape" confusion.
- Runtime order behavior differs sharply:
- backtest fill assumptions are config-driven
- simulation is stepper-driven
- paper broker is internal simulation
- live broker is Alpaca truth
- The platform still has go-live concerns around execution truthfulness for a reason.
- Promotion semantics are not runtime-consistent:
- deployment promotion
- allocation promotion
- strategy version promotion
- backtest-run promotion provenance
- The state machine is fragmented across artifacts.
- Kill/pause enforcement consistency is still fragile because enforcement paths are spread across kill switch, control routes, governor logic, deployment status, and broker cancellation behavior.
- Monitor pages may show broker truth, deployment truth, or cached UI truth depending on which panel the user is on.
- The repo memory already flagged that functional stability was not the same as go-live readiness because backtest realism and promotion semantics were still synthetic. That remains a structural runtime-consistency problem.

## 6. UX / Navigation Problems

- The left nav is grouped, but the groups do not match the actual workflow.
- The system needs a hierarchy like Build / Validate / Operate / Govern / Admin.
- Instead it has a mixed list of entities, labs, control screens, and utilities.
- Build-ish items:
- Strategies
- Watchlists
- Risk Profiles
- Strategy Controls
- Execution Styles
- Validate-ish items:
- Sim Lab
- Backtest
- Chart Lab
- Optimization Lab
- Operate-ish items:
- Programs
- Deployments
- Live Monitor
- Govern-ish items:
- Accounts
- Account Governor
- Logs
- Admin-ish items:
- Services
- Data
- Events
- Backup
- The actual menu does not enforce that logic cleanly. It leaves the user to infer it.
- `Deployments` label is misleading because the route goes to `AccountGovernorPage`, not `DeploymentManager`.
- There is no obvious top-level distinction between design-time configuration pages and runtime control pages.
- There is no obvious distinction between analysis labs and production operations.
- There is no obvious distinction between supporting data/config pages and core trading workflow pages.
- Route aliases make the nav feel unstable:
- `/accounts` and `/broker-accounts`
- `/governor`, `/portfolio-governors`, `/deployments`
- `/governors` and `/strategy-controls`
- If multiple URLs map to the same page, either the labels are wrong or the page is overloaded. In this system, both are true.
- Dashboard compensates for the bad hierarchy by acting like a pseudo-wizard. That is a red flag. Dashboards should summarize, not repair navigation.
- `LogsPanel` is doing the work of architecture docs, issue ledger, roadmap viewer, validation tracker, and risk-event log. That belongs in a dedicated operations/admin information architecture, not one stuffed page.
- `Services` and `Data` are adjacent but semantically weak. New users will not know whether broker credentials belong in `Security`, `Services`, or `Accounts`.
- `Programs` sits under operations in practice, but is actually a design/composition artifact. Wrong grouping, wrong mental expectation.

## 7. Data / Feature Problems

- The platform does not have one brutally enforced source of truth for feature semantics yet.
- Strategy config still references indicators/features through loose config shape.
- Feature planning exists, but it is still a sidecar rather than the unquestioned center of strategy evaluation.
- Runtime feature planning, backtest feature prep, and simulation prep are not obviously guaranteed to share the exact same computation pipeline.
- The feature catalog and canonical feature vocabulary are still partially aspirational.
- AI strategy generation compatibility is a stated goal, which makes inconsistency even more dangerous. If AI can name unsupported or differently computed features, the platform lies to the user.
- Feature validation surfaces exist, but they are still not strong enough as a dedicated user-facing subsystem.
- There is no obvious first-class "feature compatibility status" page that says:
- supported in builder
- supported in backtest
- supported in simulation
- supported in paper/live runtime
- That gap means false capability is always a risk.
- Market data source-of-truth is split:
- cached data inventory
- cached bars
- direct provider fetch during backtest
- direct provider fetch during simulation
- data manager manual fetch
- chart lab cache expectation
- No single invariant says when the system must reuse cached data versus live-fetch.
- Universe/source-of-truth is split:
- strategy symbols
- watchlist membership
- watchlist subscriptions on program
- symbol universe snapshot
- live universe resolved symbols
- This is a breeding ground for "why did the system trade that symbol?" disputes.
- Event source-of-truth is split:
- market event table
- earnings calendar service
- blackout fields on strategy controls
- event filter entity
- There is no one place to inspect the full effective event-gating state.
- Risk source-of-truth is split:
- account inline limits
- risk profile
- allocation override
- deployment risk link
- governor runtime state
- That means effective risk is reconstructed, not owned.
- Validation surfaces are fragmented:
- backtest metrics
- validation evidence
- logs panel
- test suite
- runtime monitor
- There is no single explicit operator-grade validation gate before paper or live promotion.
- The platform talks about canonical feature vocabulary and safe end-to-end support, but the current product surface does not make unsupported/partially supported features impossible.

## 8. Control Plane / Risk Problems

- The platform has multiple control authorities and they do not read as one coherent safety system.
- Global kill switch exists.
- Account-level kill/pause exists.
- Deployment pause exists.
- Governor halt exists.
- Manual close-position and close-all exist.
- Flatten semantics are separate.
- That is fine in theory. In practice the system exposes too many overlapping stop concepts.
- The user can reasonably ask:
- Is this halted or paused?
- Is it account-killed or governor-halted?
- Is this deployment paused or globally blocked?
- Are protective exits still live?
- Which page tells the truth?
- If the user has to ask those questions, the control plane is not clean.
- Enforcement paths are spread across:
- `kill_switch`
- `control.py`
- `governor.py`
- `deployment_service.py`
- `account_governor_loop.py`
- `alpaca_service.py`
- That is too many places to reason about safety unless authority is enforced with fanatical discipline.
- The platform has already needed a dedicated control-plane spec because the live implementation was not self-evident. That alone tells you the defaults were not structurally safe enough.
- Runtime control state is split across in-memory kill switch state, durable kill events, account flags, deployment status, and governor status.
- Startup hydration and runtime truth have historically been gaps. Any safety system that depends on correct rehydration is high-risk if the model is fragmented.
- Kill/pause/flatten semantics are easy to get wrong because the entity model is fragmented:
- `KillSwitchEvent`
- `Account.is_killed`
- `Deployment.status`
- `Deployment.governor_status`
- `GovernorEvent`
- Multiple persistence channels, overlapping meaning.
- There is still a danger of inconsistent enforcement between:
- open-new-position gating
- broker order cancellation
- manual close flows
- deployment pause flows
- governor loop checks
- Unsafe default risk remains wherever a path submits or allows orders without passing through one canonical gate.
- The platform still lacks a first-class persistent internal order model, which weakens post-incident reconstruction.
- Because the monitor/control surfaces overlap, the operator may take action from the wrong page and still not know whether the higher-precedence block is active.
- The system claims protective exits should survive kill/pause semantics, but without one clear operator-facing control-state panel, users can only trust that if the backend is perfect.
- For a trading platform, "trust us, the backend semantics are right" is not enough. The UI has to make the effective safety state obvious.

---

## FINAL VERDICT

Answer:

- The core reason the system feels disjointed is that it was built by layering new architecture on top of old flows without deleting the old mental models. The result is parallel abstractions, duplicate lifecycle artifacts, overlapping pages, and multiple competing sources of truth.

- What 3 things must be fixed first to stabilize the platform?
- First, collapse the runtime model into one canonical execution stack and one canonical runtime artifact. Pick the primary runtime unit: `TradingProgram + AccountAllocation` or `Deployment`. Stop keeping both as peers. Make `Portfolio Governor` a first-class entity instead of smuggling it through `Deployment`.
- Second, enforce one workflow shell: `Build -> Validate -> Promote -> Operate`. Reorganize pages and nav around that hierarchy, remove alias-route ambiguity, and stop sending users sideways between overlapping pages that claim the same job.
- Third, enforce one source of truth for effective behavior: one order gate, one risk source, one universe source, one feature pipeline, one promotion state machine. Right now too much is reconstructed from overlapping models and JSON payloads, and that is why the platform still feels unreliable even when parts of it work.
