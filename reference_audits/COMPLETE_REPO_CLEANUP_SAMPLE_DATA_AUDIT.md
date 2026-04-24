# COMPLETE REPO CLEANUP & SAMPLE DATA AUDIT

This is a repo-hygiene audit of the current codebase as it actually exists. It is not a style guide. It is not a cleanup wishlist. It is an inspection of runtime clutter, sample-data bleed, dead surfaces, duplicate logic, stale architecture residue, and folder-structure drift.

Primary repo areas inspected:

- `backend/app/`
- `backend/configs/`
- `backend/scripts/`
- `backend/research/`
- `backend/tests/`
- `frontend/src/`
- `frontend/e2e/`
- `scripts/`
- `docs/`
- root config and env examples

The core repo problem is not simply “too many files.” The real mess is boundary collapse:

- runtime bootstrap contains seed logic
- startup contains schema migration logic
- sample/demo content is mixed into production paths
- logs and docs preserve implementation status for features that are no longer clearly wired
- page names and route names do not line up with actual responsibilities
- historical architecture names still coexist with renamed canonical names

---

## 1. SAMPLE / DEMO DATA AUDIT

### Item 1

File path:
- `backend/app/main.py`

What it contains:
- `seed_default_data()`
- automatic creation of a default paper account
- automatic seeding of strategy YAMLs
- automatic seeding of watchlist YAMLs
- automatic seeding of “golden” watchlists
- automatic seeding of “golden” risk profiles

Where it is used:
- called on backend startup from app lifecycle

Risk:
- production runtime boot is mixed with sample/default content injection
- startup behavior changes database content even when the operator only intended to boot the app
- impossible to separate “empty system” from “system with curated starter content”
- creates silent dependence on seeded defaults for pages, tests, and operator expectations

Recommendation:
- Move default-content seeding out of startup
- Split into:
- bootstrap-required records
- optional starter packs
- optional demo content
- Keep only truly required bootstrap logic in startup

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Move to seed scripts

### Item 2

File path:
- `scripts/seed_strategies.py`

What it contains:
- explicit seeding of sample YAML strategies from `backend/configs/strategies`

Where it is used:
- README instructions
- manual seeding flow

Risk:
- duplicates logic already embedded in `backend/app/main.py`
- creates two competing seed paths for the same content
- one says “seed via script”
- one says “seed on startup”
- that is repo-hygiene failure

Recommendation:
- choose one canonical strategy-seeding mechanism
- if starter strategies are optional, keep this script and remove startup seeding
- if they are required defaults, remove the script and stop calling them “sample”

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Keep only if startup seeding is removed; otherwise delete

### Item 3

File path:
- `backend/scripts/seed_golden_templates.py`

What it contains:
- seeding of golden watchlists and golden risk profiles

Where it is used:
- standalone backend script
- same content is also embedded inside `seed_default_data()`

Risk:
- direct duplication of seeding responsibilities
- same golden data exists in both startup and script paths
- guarantees drift if one copy changes and the other does not

Recommendation:
- remove one owner
- golden templates should be seeded from one canonical script or one canonical data source, not both

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Keep as canonical seed script and delete duplicate startup copy

### Item 4

File path:
- `backend/scripts/seed_inventory.py`

What it contains:
- backfills DB inventory from existing parquet cache files

Where it is used:
- manual backend maintenance script

Risk:
- not fake data, but still a bootstrap/repair utility living beside runtime code
- depends on naming conventions in cache files
- can silently encode stale cached data as inventory truth

Recommendation:
- keep, but move under a clearly named maintenance/bootstrap folder
- document that it is a repair/import utility, not runtime bootstrap

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Keep

### Item 5

File path:
- `backend/configs/strategies/*.yaml`

What it contains:
- starter/sample strategy definitions such as `momentum.yaml`, `mean_reversion.yaml`, `intraday_momentum.yaml`, `breakout_trend.yaml`

Where it is used:
- startup seeding
- `scripts/seed_strategies.py`
- tests asserting presence of sample strategy YAML

Risk:
- runtime depends on “sample” content
- tests are coupled to bundled sample files instead of explicit fixtures
- unclear whether these are production starter packs, test fixtures, or demo artifacts

Recommendation:
- classify these as `starter_templates` or `seed_templates`, not “sample strategies”
- stop using them as implied production defaults unless explicitly bootstrapped by operator

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Move to seed scripts / starter-template directory

### Item 6

File path:
- `backend/configs/watchlists/*.yaml`

What it contains:
- seeded watchlist definitions

Where it is used:
- startup seeding in `seed_default_data()`

Risk:
- same category of problem as strategy YAMLs
- runtime boot mutates DB using starter watchlists

Recommendation:
- move to explicit watchlist starter pack seeding flow

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Move to seed scripts

### Item 7

File path:
- `backend/app/api/routes/events.py`

What it contains:
- `POST /events/seed-sample`
- hardcoded sample macro events for demo/testing

Where it is used:
- `frontend/src/pages/EventCalendar.tsx`
- visible UI button: `+ Load Sample Events`

Risk:
- production-facing page exposes sample-data injection
- demo events are mixed into runtime data model
- source is `"seed"`
- no clean dev-only boundary

Recommendation:
- remove from production UI path
- if retained, guard behind dev/admin feature flag
- move hardcoded event list into test fixtures or demo seed pack

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Move to seed scripts and admin/dev-only tools

### Item 8

File path:
- `frontend/src/pages/EventCalendar.tsx`

What it contains:
- calls `/events/seed-sample`
- renders “Load Sample Events”

Where it is used:
- routed page in `App.tsx`

Risk:
- sample data entry point is in normal user flow
- this is not a harmless dev button; it pollutes live app behavior

Recommendation:
- remove button from production surface
- if needed for dev, hide behind environment gate

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Convert to real config or dev-only feature flag

### Item 9

File path:
- `backend/research/slippage_model_example.py`
- `backend/research/signal_quality_metrics_example.py`
- `backend/research/performance_analytics_example.py`
- `backend/research/paper_mode_and_drift_monitoring_stub.md`
- `backend/research/position_sizing_examples.md`
- `backend/research/stop_loss_examples.md`
- `backend/research/quant_research_template.md`

What it contains:
- examples
- stubs
- research notes
- templates

Where it is used:
- no runtime references found
- one stub doc cross-references another research example

Risk:
- these are not bad files, but they are living directly under backend and feel closer to product than they are
- they increase search noise
- “example” and “stub” files inside backend invite wrong imports later

Recommendation:
- keep, but move under `docs/research/` or `research/archive/`
- do not leave them adjacent to runtime code without stronger isolation

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Move

### Item 10

File path:
- `backend/.env.example`

What it contains:
- partial/legacy environment example
- duplicate settings already present in root `.env.example`
- old `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL`
- duplicated app/db settings

Where it is used:
- unclear

Risk:
- configuration drift
- conflicting environment instructions
- likely stale naming relative to current per-account credential storage model

Recommendation:
- remove or replace with a single canonical env example

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Delete or merge into root `.env.example`

### Item 11

File path:
- `frontend/src/pages/LogsPanel.tsx`

What it contains:
- large arrays of implementation-history content
- references to seeded weights, golden watchlists, completed work items, files changed, roadmap-like status

Where it is used:
- routed page in app

Risk:
- product UI has turned into a project diary
- implementation notes, status ledger, and sample/status content are mixed into runtime page code
- creates false confidence that features are “complete” even when actual wiring is partial or dead

Recommendation:
- strip implementation-history payload out of product runtime
- move these logs into docs or admin-only diagnostics loaded from actual data

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Move

### Item 12

File path:
- `frontend/e2e/live_stream.spec.ts`

What it contains:
- fake websocket implementation injected into the browser for testing

Where it is used:
- Playwright test only

Risk:
- low if kept inside tests
- fine as test scaffolding

Recommendation:
- keep

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Keep

### Item 13

File path:
- `backend/tests/conftest.py`
- various tests using `seed_fake_credentials`

What it contains:
- fake credential helpers
- seeded fake broker setups for tests

Where it is used:
- backend tests

Risk:
- low inside tests
- appropriate if clearly isolated

Recommendation:
- keep, but ensure no runtime module imports test helpers

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Keep

### Item 14

File path:
- `backend/app/services/alpaca_account_stream.py`

What it contains:
- hardcoded preferred account name: `Paper1_OtijiTrader_UseTest`

Where it is used:
- startup/runtime account event stream

Risk:
- sample/test account naming leaked into runtime logic
- this is exactly the kind of leftover that should never survive cleanup

Recommendation:
- remove hardcoded account name
- choose accounts by explicit config / active deployment scope

Delete | Keep | Move to test fixtures | Move to seed scripts | Convert to real config
- Convert to real config

---

## 2. DEAD CODE AUDIT

### Item 1

File path:
- `frontend/src/pages/DeploymentManager.tsx`

Why it appears unused:
- exists as a full page
- not routed in `frontend/src/App.tsx`
- `/deployments` route points to `AccountGovernorPage`, not `DeploymentManager`

References found:
- self-definition only

Risk of deleting:
- medium
- page contains real UI logic for deployment controls
- but current app routing bypasses it

Recommendation:
- do not delete immediately
- first decide whether `DeploymentManager` or `AccountGovernor` is the canonical deployment/operator page
- then delete the loser

### Item 2

File path:
- `frontend/src/components/PDTGauge.tsx`

Why it appears unused:
- no runtime imports found
- only referenced in `LogsPanel.tsx` prose

References found:
- component file
- `LogsPanel.tsx` descriptive text

Risk of deleting:
- low to medium
- may represent unfinished intended UI, but not active wiring

Recommendation:
- safe candidate for removal after one final grep confirmation

### Item 3

File path:
- `frontend/src/components/ProgramSwimlane.tsx`

Why it appears unused:
- no runtime imports found
- only referenced in `LogsPanel.tsx` prose

References found:
- component file
- `LogsPanel.tsx`

Risk of deleting:
- low to medium

Recommendation:
- likely safe delete after final review

### Item 4

File path:
- `backend/app/services/position_ledger.py`

Why it appears unused:
- no active runtime references found in backend outside the file itself
- referenced only in docs and `LogsPanel.tsx` narrative

References found:
- no live code imports found
- docs/logs references only

Risk of deleting:
- medium to high
- the file represents intended attribution logic, but it is not integrated
- deleting it would remove future-work scaffolding
- keeping it in place misleads reviewers into thinking live fill routing exists

Recommendation:
- do not delete blindly
- either wire it into runtime properly or archive it as abandoned design work

### Item 5

File path:
- `backend/app/services/technical_analysis.py`

Why it appears unused:
- no obvious runtime imports found in backend search output
- comments mention placeholder RSI support

References found:
- file itself only in the current scan

Risk of deleting:
- medium

Recommendation:
- inspect one more time before deleting
- if not used, remove or move to archived experiments

### Item 6

File path:
- `backend/app/services/promotion_service.py`

Why it appears suspicious:
- appears used by `programs.py`
- but overlaps with deployment promotion lifecycle in `deployment_service.py`

References found:
- imported in `backend/app/api/routes/programs.py`
- referenced in `LogsPanel.tsx`

Risk of deleting:
- high

Recommendation:
- not dead
- but likely part of duplicate lifecycle logic and should be consolidated

### Item 7

File path:
- `backend/app/services/governor_service.py`

Why it appears suspicious:
- used by routes and deployment service
- but implements governor as a deployment sentinel rather than clean first-class entity

References found:
- `backend/app/api/routes/governor.py`
- `backend/app/services/deployment_service.py`

Risk of deleting:
- high

Recommendation:
- not dead
- structurally compromised, but still active

### Item 8

File path:
- `backend/app/cerebro/*`

Why it appears suspicious:
- active references exist from features and paper broker
- but the folder naming is domain-inconsistent and sidecar-like

References found:
- `features/cache.py`
- `features/frame.py`
- `features/preview.py`
- `paper_broker.py`

Risk of deleting:
- high

Recommendation:
- not dead
- rename/rehome later under a canonical feature-runtime namespace

### Item 9

File path:
- `backend/research/*example*`
- `backend/research/*stub*`

Why it appears unused:
- no runtime references

References found:
- only doc cross-references

Risk of deleting:
- low

Recommendation:
- move out of runtime-adjacent backend tree

### Item 10

File path:
- `frontend/src/pages/BackupRestore.tsx`

Why it appears suspicious:
- routed
- but only weak evidence of backend coverage
- admin/restore surface often exists without end-to-end operational hardening

References found:
- route in `App.tsx`
- referenced in `LogsPanel.tsx`

Risk of deleting:
- medium

Recommendation:
- not dead, but verify backend parity and tests before treating as supported

### Item 11

File path:
- `frontend/src/pages/CredentialManager.tsx`
- `frontend/src/pages/Services.tsx`
- `frontend/src/pages/AccountMonitor.tsx`

Why they appear partially overlapping:
- credentials/service configuration/account broker management are split across multiple pages
- overlap creates dead-ish subflows where one surface supersedes another

References found:
- all routed

Risk of deleting:
- medium to high

Recommendation:
- no immediate delete
- redesign ownership first, then remove redundant surface

### Item 12

File path:
- `scripts/start_backend.ps1`
- `scripts/setup.sh`
- root `scripts/*` plus near-duplicate backend/start entrypoints

Why they appear suspicious:
- mixed root-level scripts and backend-local launch scripts
- unclear canonical operator path

References found:
- README references some scripts

Risk of deleting:
- medium

Recommendation:
- keep only one canonical launch path per environment

---

## 3. DUPLICATE LOGIC AUDIT

### Duplication 1

Files involved:
- `backend/app/main.py`
- `scripts/seed_strategies.py`
- `backend/scripts/seed_golden_templates.py`

Duplicated responsibility:
- seeding starter/default data

Canonical owner should be:
- dedicated bootstrap/seed layer outside app startup

Recommendation:
- remove all duplicate seed definitions from startup
- keep seed packs explicit and operator-invoked

### Duplication 2

Files involved:
- `backend/app/services/deployment_service.py`
- `backend/app/services/promotion_service.py`
- `backend/app/api/routes/programs.py`
- `backend/app/api/routes/deployments.py`

Duplicated responsibility:
- paper-to-live / deployment promotion lifecycle logic

Canonical owner should be:
- one deployment lifecycle service

Recommendation:
- merge promotion logic into one canonical runtime/deployment service

### Duplication 3

Files involved:
- `backend/app/services/alpaca_service.py`
- `backend/app/brokers/alpaca_broker.py`
- `backend/app/api/routes/accounts.py`
- `backend/app/api/routes/deployments.py`
- `backend/app/api/routes/monitor.py`

Duplicated responsibility:
- broker operations exposed through service, broker wrapper, and route-level orchestration

Canonical owner should be:
- one broker-control service below routes

Recommendation:
- routes should stop owning broker mutation behavior

### Duplication 4

Files involved:
- `backend/app/core/backtest.py`
- `backend/app/services/simulation_service.py`
- `frontend/src/pages/BacktestLauncher.tsx`
- `frontend/src/pages/SimulationLab.tsx`
- `frontend/src/pages/ChartLab.tsx`

Duplicated responsibility:
- multiple “run the strategy over time-series data” experiences with overlapping config and validation concepts

Canonical owner should be:
- shared execution/run-configuration model with separate shells

Recommendation:
- consolidate shared configuration/validation and stop duplicating run-launch semantics in separate labs

### Duplication 5

Files involved:
- `frontend/src/pages/AccountGovernor.tsx`
- `frontend/src/pages/DeploymentManager.tsx`
- `frontend/src/pages/AccountMonitor.tsx`
- `frontend/src/pages/LiveMonitor.tsx`

Duplicated responsibility:
- deployment operations, account operations, monitor controls, pause/stop/flatten actions

Canonical owner should be:
- one operator control surface with clear account/deployment tabs

Recommendation:
- merge or kill overlapping pages

### Duplication 6

Files involved:
- `backend/app/services/watchlist_service.py`
- `backend/app/services/universe_service.py`
- `backend/app/api/routes/watchlists.py`
- `backend/app/api/routes/universes.py`
- `backend/app/api/routes/data.py`

Duplicated responsibility:
- symbol universe / watchlist / membership / overlay resolution

Canonical owner should be:
- explicit universe domain layer

Recommendation:
- decide whether watchlists are the canonical universe primitive or just one source feeding universes

### Duplication 7

Files involved:
- `backend/app/services/reporting.py`
- `backend/app/services/risk_profile_generator.py`
- `backend/app/services/backtest_service.py`
- `backend/app/services/param_optimizer.py`

Duplicated responsibility:
- backtest metrics and downstream recommendations built on same results

Canonical owner should be:
- reporting/metrics service

Recommendation:
- centralize metrics production and consume it everywhere else

### Duplication 8

Files involved:
- `frontend/src/api/accounts.ts`
- `frontend/src/api/monitor.ts`
- `frontend/src/api/governor.ts`
- `frontend/src/api/services.ts`

Duplicated responsibility:
- operator control-plane fetching spread across several API client files

Canonical owner should be:
- one control-plane API module organized by domain

Recommendation:
- regroup frontend API clients by bounded context, not by historical screen

### Duplication 9

Files involved:
- `backend/app/main.py` incremental migration block
- env examples
- startup seed logic

Duplicated responsibility:
- startup tries to be migration engine, bootstrap engine, and app entrypoint

Canonical owner should be:
- separate migration tool plus separate bootstrap/seed tool

Recommendation:
- remove non-app responsibilities from `main.py`

### Duplication 10

Files involved:
- `frontend/src/pages/StrategyCreator.tsx`
- `frontend/src/pages/StrategyEditor.tsx`
- `frontend/src/pages/Strategies.tsx`
- `frontend/src/pages/StrategyDetails.tsx`

Duplicated responsibility:
- strategy authoring/edit/versioning flows

Canonical owner should be:
- one strategy workspace with modes

Recommendation:
- collapse “create” and “edit/new version” into a unified strategy workstation

---

## 4. BACKEND ROUTE CLEANUP

### Route group

Route prefix:
- `/api/v1/strategies`

Purpose:
- strategy CRUD, validation, version operations

Still needed? yes/no/unclear
- yes

Overlaps with:
- programs
- backtests
- strategy-controls

Missing tests:
- unclear if full diff/version/prompt-assisted generation paths are covered

Recommended action:
- keep
- narrow to pure strategy domain

### Route group

Route prefix:
- `/api/v1/backtests`

Purpose:
- launch and inspect backtests

Still needed? yes/no/unclear
- yes

Overlaps with:
- simulations
- optimizations
- monitor replay surfaces

Missing tests:
- likely missing full replay/reporting edge coverage

Recommended action:
- keep
- extract shared run-config schema used by simulations and optimizations

### Route group

Route prefix:
- `/api/v1/accounts`

Purpose:
- broker account CRUD, credentials, account activity, flatten/halt

Still needed? yes/no/unclear
- yes

Overlaps with:
- services
- control
- monitor

Missing tests:
- account emergency/flatten/credential edge paths need broader coverage

Recommended action:
- keep
- strip non-account-owned broker mutation paths if they belong under control-plane service

### Route group

Route prefix:
- `/api/v1/deployments`

Purpose:
- deployment lifecycle and live deployment controls

Still needed? yes/no/unclear
- yes

Overlaps with:
- monitor
- governor
- programs

Missing tests:
- manual live control actions need stronger tests

Recommended action:
- keep
- reduce overlap with monitor and governor

### Route group

Route prefix:
- `/api/v1/data`

Purpose:
- data ingestion, inventory, metadata, watchlist-like helpers

Still needed? yes/no/unclear
- yes

Overlaps with:
- services
- universes
- watchlists

Missing tests:
- route family appears partially covered, but too much mixed responsibility remains

Recommended action:
- split data ingestion, metadata, and universe/watchlist helpers into cleaner route groups

### Route group

Route prefix:
- `/api/v1/control`

Purpose:
- global/account/deployment kill and control status

Still needed? yes/no/unclear
- yes

Overlaps with:
- accounts
- monitor
- governor

Missing tests:
- legacy strategy-scope controls still exist and are only lightly covered

Recommended action:
- keep
- delete deprecated strategy-scope endpoints once replacement path is complete

### Route group

Route prefix:
- `/api/v1/events`

Purpose:
- event calendar and event filters

Still needed? yes/no/unclear
- yes

Overlaps with:
- strategy-controls
- watchlist exclusions

Missing tests:
- no obvious dedicated event route tests found

Recommended action:
- keep
- remove sample-seed endpoint from standard runtime surface

### Route group

Route prefix:
- `/api/v1/ml`

Purpose:
- ML analysis and promotion advice

Still needed? yes/no/unclear
- unclear

Overlaps with:
- optimizations
- backtests
- deployment promotion review

Missing tests:
- only partial decision-support coverage observed

Recommended action:
- keep only if product owner still wants ML advisory workflow
- otherwise isolate from core runtime

### Route group

Route prefix:
- `/api/v1/monitor`

Purpose:
- live/deployment monitoring and close actions

Still needed? yes/no/unclear
- yes

Overlaps with:
- deployments
- accounts
- control

Missing tests:
- only partial workflow coverage

Recommended action:
- keep
- remove account-scoped actions disguised as deployment-scoped

### Route group

Route prefix:
- `/api/v1/optimizations`

Purpose:
- optimization profiles and weight generation

Still needed? yes/no/unclear
- yes

Overlaps with:
- backtests
- programs

Missing tests:
- broader lifecycle and failure-path testing likely thin

Recommended action:
- keep

### Route group

Route prefix:
- `/api/v1/universes`

Purpose:
- universe resolution and persisted universe snapshots

Still needed? yes/no/unclear
- yes

Overlaps with:
- watchlists
- programs
- data

Missing tests:
- some coverage exists

Recommended action:
- keep, but define relation to watchlists explicitly

### Route group

Route prefix:
- `/api/v1/bi`

Purpose:
- BI overview

Still needed? yes/no/unclear
- unclear

Overlaps with:
- dashboard
- reporting

Missing tests:
- minimal

Recommended action:
- decide whether BI is real product surface or leftover experiment

### Route group

Route prefix:
- `/api/v1/backlog`

Purpose:
- program backlog item management

Still needed? yes/no/unclear
- yes

Overlaps with:
- logs/admin planning surfaces

Missing tests:
- some coverage exists

Recommended action:
- keep if backlog is a genuine product entity; otherwise move to admin/internal tooling

### Route group

Route prefix:
- `/api/v1/services`

Purpose:
- data service / AI service registry

Still needed? yes/no/unclear
- yes

Overlaps with:
- accounts
- credentials
- data

Missing tests:
- has route coverage, but conceptual overlap remains

Recommended action:
- keep, but separate provider registry from account credential UX

### Route group

Route prefix:
- `/api/v1/programs`

Purpose:
- trading programs and allocations

Still needed? yes/no/unclear
- yes

Overlaps with:
- deployments
- strategies
- risk profiles
- strategy-controls
- execution styles

Missing tests:
- component-boundary validation remains likely incomplete

Recommended action:
- keep

### Route group

Route prefix:
- `/api/v1/watchlists`

Purpose:
- watchlist CRUD and membership operations

Still needed? yes/no/unclear
- yes

Overlaps with:
- universes
- data watchlist helpers

Missing tests:
- core coverage exists

Recommended action:
- keep
- stop duplicating watchlist-ish flows under data routes

### Route group

Route prefix:
- `/api/v1/simulations`

Purpose:
- simulation sessions and stepping

Still needed? yes/no/unclear
- yes

Overlaps with:
- backtests
- chart lab
- monitor

Missing tests:
- only partial contract coverage

Recommended action:
- keep, but align config and nomenclature with backtests

### Route group

Route prefix:
- `/api/v1/risk-profiles`

Purpose:
- risk profile CRUD and generation

Still needed? yes/no/unclear
- yes

Overlaps with:
- programs
- accounts
- AI-assisted generation

Missing tests:
- no obvious dedicated risk-profile route test file found

Recommended action:
- keep
- add real route coverage

### Route group

Route prefix:
- `/api/v1/strategy-controls`

Purpose:
- strategy controls / formerly strategy governors

Still needed? yes/no/unclear
- yes

Overlaps with:
- old naming “governors”
- events
- risk profiles

Missing tests:
- no obvious dedicated route tests found

Recommended action:
- keep
- finish rename and remove old terminology everywhere else

### Route group

Route prefix:
- `/api/v1/execution-styles`

Purpose:
- execution style CRUD

Still needed? yes/no/unclear
- yes

Overlaps with:
- strategies
- deployments

Missing tests:
- no obvious dedicated execution-style route tests found

Recommended action:
- keep
- add route tests

### Route group

Route prefix:
- `/api/v1/governor`

Purpose:
- portfolio/account governor bootstrap and operations

Still needed? yes/no/unclear
- unclear

Overlaps with:
- control
- deployments
- monitor
- account governor page

Missing tests:
- some bootstrap coverage exists, but broader surface looks under-tested

Recommended action:
- decide whether this is a first-class domain route group or transitional scaffold

### Route group

Route prefix:
- `/api/v1/admin`

Purpose:
- admin tooling and user-journey validations

Still needed? yes/no/unclear
- yes, but internal only

Overlaps with:
- logs
- docs

Missing tests:
- backup/restore and admin tooling breadth likely under-covered

Recommended action:
- keep
- make admin boundary explicit

---

## 5. FRONTEND PAGE CLEANUP

### Page

Page path:
- `frontend/src/pages/Dashboard.tsx`

Purpose:
- top-level overview

Still needed? yes/no/unclear
- yes

Overlaps with:
- BI
- Monitor

Should be grouped under:
- Monitor

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/Strategies.tsx`

Purpose:
- strategy list and discovery

Still needed? yes/no/unclear
- yes

Overlaps with:
- StrategyDetails
- StrategyCreator
- StrategyEditor

Should be grouped under:
- Build

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/StrategyCreator.tsx`

Purpose:
- new strategy creation

Still needed? yes/no/unclear
- unclear

Overlaps with:
- StrategyEditor

Should be grouped under:
- Build

Recommended action:
- likely merge into `StrategyEditor`

### Page

Page path:
- `frontend/src/pages/StrategyEditor.tsx`

Purpose:
- edit/new-version strategy workflow

Still needed? yes/no/unclear
- yes

Overlaps with:
- StrategyCreator

Should be grouped under:
- Build

Recommended action:
- make this the canonical authoring surface

### Page

Page path:
- `frontend/src/pages/StrategyDetails.tsx`

Purpose:
- inspect versions and strategy details

Still needed? yes/no/unclear
- yes

Overlaps with:
- Strategies
- StrategyEditor

Should be grouped under:
- Build

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/BacktestLauncher.tsx`

Purpose:
- launch backtests

Still needed? yes/no/unclear
- yes

Overlaps with:
- SimulationLab
- OptimizationLab

Should be grouped under:
- Validate

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/RunHistory.tsx`

Purpose:
- browse run history

Still needed? yes/no/unclear
- yes

Overlaps with:
- RunDetails

Should be grouped under:
- Validate

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/RunDetails.tsx`

Purpose:
- inspect individual runs

Still needed? yes/no/unclear
- yes

Overlaps with:
- ChartLab
- SimulationLab

Should be grouped under:
- Validate

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/AccountMonitor.tsx`

Purpose:
- account inventory and account actions

Still needed? yes/no/unclear
- yes

Overlaps with:
- CredentialManager
- Services
- AccountGovernor

Should be grouped under:
- Operate

Recommended action:
- keep, but narrow ownership

### Page

Page path:
- `frontend/src/pages/CredentialManager.tsx`

Purpose:
- manage credentials

Still needed? yes/no/unclear
- unclear

Overlaps with:
- AccountMonitor
- Services

Should be grouped under:
- Admin

Recommended action:
- probably collapse into Services or AccountMonitor credential drawer

### Page

Page path:
- `frontend/src/pages/AccountGovernor.tsx`

Purpose:
- portfolio/deployment governor operations

Still needed? yes/no/unclear
- yes

Overlaps with:
- DeploymentManager
- LiveMonitor
- AccountMonitor

Should be grouped under:
- Operate

Recommended action:
- keep as canonical deployment/operator page if `DeploymentManager` is retired

### Page

Page path:
- `frontend/src/pages/RiskProfiles.tsx`

Purpose:
- risk profile management

Still needed? yes/no/unclear
- yes

Overlaps with:
- Programs
- Accounts

Should be grouped under:
- Build

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/DataManager.tsx`

Purpose:
- manage market data services and cache

Still needed? yes/no/unclear
- yes

Overlaps with:
- Services
- ChartLab

Should be grouped under:
- Admin

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/EventCalendar.tsx`

Purpose:
- event calendar management

Still needed? yes/no/unclear
- yes

Overlaps with:
- StrategyControls

Should be grouped under:
- Build

Recommended action:
- keep, but remove sample-seed affordance

### Page

Page path:
- `frontend/src/pages/LogsPanel.tsx`

Purpose:
- mixed logs, issues, status ledger, docs links, internal planning

Still needed? yes/no/unclear
- unclear

Overlaps with:
- Admin
- docs
- issue tracking

Should be grouped under:
- Admin

Recommended action:
- split into actual runtime logs vs docs/internal status

### Page

Page path:
- `frontend/src/pages/LiveMonitor.tsx`

Purpose:
- live monitoring

Still needed? yes/no/unclear
- yes

Overlaps with:
- AccountGovernor
- AccountMonitor
- RunDetails

Should be grouped under:
- Monitor

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/Services.tsx`

Purpose:
- provider service registry

Still needed? yes/no/unclear
- yes

Overlaps with:
- CredentialManager
- DataManager

Should be grouped under:
- Admin

Recommended action:
- keep, but stop sharing ownership with account credential flows

### Page

Page path:
- `frontend/src/pages/TradingPrograms.tsx`

Purpose:
- program composition

Still needed? yes/no/unclear
- yes

Overlaps with:
- Strategies
- RiskProfiles
- StrategyControls
- ExecutionStyles

Should be grouped under:
- Build

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/WatchlistLibrary.tsx`

Purpose:
- watchlist management

Still needed? yes/no/unclear
- yes

Overlaps with:
- universes
- programs

Should be grouped under:
- Build

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/OptimizationLab.tsx`

Purpose:
- optimization and robustness validation

Still needed? yes/no/unclear
- yes

Overlaps with:
- BacktestLauncher
- SimulationLab

Should be grouped under:
- Validate

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/ChartLab.tsx`

Purpose:
- visual chart exploration

Still needed? yes/no/unclear
- yes

Overlaps with:
- SimulationLab
- RunDetails
- DataManager

Should be grouped under:
- Validate

Recommended action:
- keep, but define narrower mission

### Page

Page path:
- `frontend/src/pages/SimulationLab.tsx`

Purpose:
- stepped simulation / replay-like lab

Still needed? yes/no/unclear
- yes

Overlaps with:
- BacktestLauncher
- ChartLab

Should be grouped under:
- Validate

Recommended action:
- keep, but align with backtest terminology

### Page

Page path:
- `frontend/src/pages/BackupRestore.tsx`

Purpose:
- backup/restore admin utility

Still needed? yes/no/unclear
- unclear

Overlaps with:
- Admin tooling

Should be grouped under:
- Admin

Recommended action:
- keep only if backend/admin flow is hardened

### Page

Page path:
- `frontend/src/pages/StrategyGovernors.tsx`

Purpose:
- strategy controls management

Still needed? yes/no/unclear
- yes

Overlaps with:
- EventCalendar
- RiskProfiles
- Programs

Should be grouped under:
- Build

Recommended action:
- keep, but rename file to match actual domain

### Page

Page path:
- `frontend/src/pages/ExecutionStyles.tsx`

Purpose:
- execution style management

Still needed? yes/no/unclear
- yes

Overlaps with:
- Strategies
- Programs

Should be grouped under:
- Build

Recommended action:
- keep

### Page

Page path:
- `frontend/src/pages/DeploymentManager.tsx`

Purpose:
- deployment manager with live controls

Still needed? yes/no/unclear
- unclear

Overlaps with:
- AccountGovernor
- LiveMonitor

Should be grouped under:
- Operate

Recommended action:
- orphaned; choose canonical page and delete or merge this one

---

## 6. DATABASE / MIGRATION / SEED CLEANUP

### Item 1

File path:
- `backend/app/main.py`

Purpose:
- ad hoc schema migrations via startup-time `ALTER TABLE` block

Production-safe? yes/no
- no

Risk:
- no versioned migration system
- migrations run at app startup
- failure modes are opaque
- impossible to reason about schema history cleanly
- rename plus additive migrations are jammed into entrypoint

Recommendation:
- move to Alembic or equivalent versioned migration system

### Item 2

File path:
- no dedicated migrations directory present

Purpose:
- absence of proper migration system

Production-safe? yes/no
- no

Risk:
- schema drift
- startup magic
- poor reproducibility

Recommendation:
- create versioned migration framework

### Item 3

File path:
- `backend/app/main.py`

Purpose:
- default paper account creation

Production-safe? yes/no
- no

Risk:
- forces starter account into any fresh runtime

Recommendation:
- move to explicit bootstrap seed

### Item 4

File path:
- `backend/configs/strategies/*.yaml`

Purpose:
- starter strategies

Production-safe? yes/no
- yes as templates, no as implicit startup content

Risk:
- ambiguous role

Recommendation:
- move to starter template pack

### Item 5

File path:
- `backend/configs/watchlists/*.yaml`

Purpose:
- starter watchlists

Production-safe? yes/no
- yes as templates, no as automatic runtime seed

Risk:
- same ambiguity

Recommendation:
- move to explicit bootstrap path

### Item 6

File path:
- `backend/scripts/seed_golden_templates.py`

Purpose:
- golden template seed

Production-safe? yes/no
- yes if explicit, no if duplicated with startup seeding

Risk:
- dual source of truth

Recommendation:
- keep as only seed owner

### Item 7

File path:
- `scripts/seed_strategies.py`

Purpose:
- sample strategy seed

Production-safe? yes/no
- yes if explicit

Risk:
- duplicates startup seeding

Recommendation:
- keep only if startup seeding is removed

### Item 8

File path:
- `backend/.env.example`

Purpose:
- secondary env template

Production-safe? yes/no
- no

Risk:
- stale config naming

Recommendation:
- delete or merge

### Item 9

File path:
- root `.env.example`

Purpose:
- canonical environment example

Production-safe? yes/no
- mostly yes

Risk:
- still mixes historical Alpaca env comments with UI-stored credential model

Recommendation:
- rewrite to match current config truth exactly

---

## 7. CONFIGURATION CLEANUP

Unsafe defaults:

- `backend/app/config.py` ships placeholder `SECRET_KEY`
- `backend/app/config.py` ships placeholder `ENCRYPTION_KEY`
- `backend/.env.example` duplicates and conflicts with root env model
- root `.env.example` still comments about hard-coded default Alpaca accounts even though credentials are also stored per account in UI

Duplicated config:

- root `.env.example`
- `backend/.env.example`
- startup-time defaults in `Settings`
- startup-time seeded default account in `main.py`

Unclear settings:

- `PLATFORM_MODE` meaning is only partial and does not cleanly constrain operational paths
- CORS configured in code while env examples also suggest config-driven operation
- database URL semantics differ between root example and backend-config-resolved path behavior

Hardcoded paths:

- `backend/app/config.py` resolves `.env` relative to backend
- root README suggests copying root `.env.example` to root `.env`
- backend config actually expects `backend/.env`
- that is a configuration paper cut waiting to waste time

Provider defaults:

- default paper balance and other defaults are legitimate
- default paper account creation in startup is not

Feature flags:

- no clean feature-flag system found for demo/dev-only endpoints like sample event seeding

Hardcoded secrets or sample credentials:

- no committed real secrets observed in inspected files
- but placeholder secret models are duplicated
- runtime stream selection still contains hardcoded test account name `Paper1_OtijiTrader_UseTest`

Configuration cleanup actions:

- one env example only
- one env file location only
- no runtime hardcoded test account names
- dev/demo-only functionality behind explicit flags
- startup should not create business entities silently

---

## 8. TEST CLEANUP

Outdated assumptions:

- tests assert presence of sample strategy YAML files
- that couples core test health to starter/demo content packaging

Fake happy paths:

- many tests use fake credentials and monkeypatched data providers, which is normal
- the problem is not mocks themselves
- the problem is that some critical operator flows still seem more lightly covered than the amount of surface area implies

Missing edge cases:

- event routes appear under-tested
- execution styles routes appear under-tested
- risk profiles routes appear under-tested
- strategy-controls routes appear under-tested
- admin backup/restore breadth appears under-tested
- live operator overlap paths between accounts/deployments/monitor deserve more integration tests

Brittle snapshots:

- no obvious snapshot-test mess found in the inspected set

Tests covering dead code:

- route tests still cover deprecated strategy-scope control endpoints
- that is useful as long as those routes exist, but it also cements legacy clutter

Tests not covering critical flows:

- sample/demo content exposure in EventCalendar UI and backend route
- startup seeding side effects
- migration-startup idempotency in a versioned, inspectable way
- page reachability/orphan pages

Tests to delete:

- tests that only preserve deprecated strategy-scope control routes once those routes are removed
- tests that enforce presence of sample YAML as a runtime invariant rather than fixture availability

Tests to rewrite:

- tests coupled to startup-seeded default content
- tests that rely on broad “system boot contains starter data” assumptions

Tests to add:

- route reachability and unused page detection via frontend route manifest checks
- explicit startup bootstrap test proving no business entities are auto-created unless bootstrap enabled
- admin/dev gating test for sample-event seeding
- config consistency tests for env file location and naming
- integration tests for account/deployment/control surface boundaries

---

## 9. CLEANUP PLAN

### Phase 1: Safe deletes

Items that can be removed immediately.

- `backend/.env.example` after merging any still-needed content into root `.env.example`
- `frontend/src/components/PDTGauge.tsx` if one final grep confirms no runtime imports
- `frontend/src/components/ProgramSwimlane.tsx` if one final grep confirms no runtime imports
- research/example files can be moved out immediately if docs links are updated
- remove `Paper1_OtijiTrader_UseTest` hardcoded preference from `alpaca_account_stream.py`

### Phase 2: Move / isolate

Sample data, fixtures, seed data, and demo content that should be moved out of runtime paths.

- move startup seeding out of `backend/app/main.py`
- move strategy YAML starter content into explicit starter-template/bootstrap path
- move watchlist YAML starter content into explicit bootstrap path
- move sample event seeding into admin/dev-only seed pack
- move `LogsPanel` implementation-history payload into docs/admin diagnostics
- move `backend/research/*` into a clearer research/docs area

### Phase 3: Consolidate

Duplicate logic that should be merged into canonical services.

- unify seeding ownership
- unify deployment/promotion lifecycle ownership
- unify control-plane broker mutation ownership
- unify account/service/credential ownership
- unify watchlist/universe boundaries
- unify strategy authoring pages

### Phase 4: Refactor

Larger structural cleanup that requires tests first.

- replace startup migration block with versioned migrations
- redesign page IA into Build / Validate / Operate / Monitor / Admin
- reduce monitor/accounts/deployments/control route overlap
- define one canonical operator surface for live actions
- rename legacy “governor/governors/strategy_governors/strategy_controls” residue consistently

### Phase 5: Guardrails

Lint rules, folder conventions, import rules, CI checks, and documentation to prevent the mess from returning.

- forbid sample/demo endpoints in production bundles without explicit flag
- add CI check for orphan frontend pages not routed from app manifest
- add CI check for backend routes with no tests
- add import-boundary rules: runtime code cannot import from research/docs/test helpers
- add folder convention:
- `app/` runtime only
- `bootstrap/` seed/bootstrap only
- `migrations/` schema only
- `research/` non-runtime only
- `docs/` docs only
- add CI check for duplicate env examples and stale config keys
- require page-to-route and route-to-test inventory docs to stay current

---

## FINAL VERDICT

What is the worst source of clutter?

- `backend/app/main.py`

It is carrying far too much repo debt:

- app entrypoint
- ad hoc migration engine
- seed/bootstrap engine
- default record creator
- historical schema salvage logic

That one file is where runtime cleanliness goes to die.

What backend cleanup must happen first?

- remove startup-owned schema migration and startup-owned business-data seeding from `backend/app/main.py`

What frontend cleanup must happen first?

- choose the canonical deployment/operator page and delete or merge the redundant one
- right now `AccountGovernor.tsx`, `DeploymentManager.tsx`, `AccountMonitor.tsx`, and `LiveMonitor.tsx` overlap badly enough to keep the whole operator UX muddy

What should absolutely NOT be deleted yet?

- `backend/app/services/position_ledger.py` should not be blindly deleted until the team explicitly decides whether to integrate or archive it
- `backend/app/services/governor_service.py` should not be deleted before governance ownership is redesigned
- `backend/app/services/promotion_service.py` should not be deleted before deployment/promotion lifecycle consolidation
- `frontend/src/pages/BackupRestore.tsx` should not be deleted until backend admin flow is verified
- strategy/watchlist YAML starter content should not be deleted until tests and onboarding flows stop depending on them

Top 10 cleanup actions in order

1. Extract migrations out of `backend/app/main.py` into a real versioned migration system.
2. Remove all startup seeding of business entities from `backend/app/main.py`.
3. Pick one canonical seed/bootstrap mechanism and delete duplicate seeding logic.
4. Delete or merge `backend/.env.example` into one canonical env example.
5. Remove `Paper1_OtijiTrader_UseTest` and any runtime test-account assumptions.
6. Kill the production-facing sample event seed path from `events.py` and `EventCalendar.tsx`.
7. Choose between `AccountGovernor.tsx` and `DeploymentManager.tsx`; delete or merge the redundant page.
8. Remove orphan frontend components like `PDTGauge.tsx` and `ProgramSwimlane.tsx` after final verification.
9. Move `backend/research/*` and implementation-history payloads out of runtime-adjacent product paths.
10. Reorganize frontend information architecture into Build / Validate / Operate / Monitor / Admin and align route names, page names, and backend route groups to match.
