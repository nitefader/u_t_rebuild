import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { spawn } from "node:child_process";

const UI_BASE = process.env.UTOS_UI_BASE ?? "http://127.0.0.1:5173";
const API_BASE = process.env.UTOS_API_BASE ?? "http://127.0.0.1:8000";
const CHROME =
  process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const logDir = resolve(process.cwd(), "..", ".runtime_logs");
const userDataDir = join(logDir, `headless-screener-${stamp}`);
const screenshotPath = join(logDir, `headless-screener-${stamp}.png`);
const remotePort = 9300 + Math.floor(Math.random() * 500);

mkdirSync(logDir, { recursive: true });

const passed = [];
const journeyCoverage = new Map([
  ["operator", new Set()],
  ["day_trader", new Set()],
  ["swing_quant", new Set()],
]);
const journeyRequirements = {
  operator: [
    "screeners_loaded",
    "ai_advisory",
    "save_watchlist",
    "deployment_doctrine",
    "unsafe_delete_guard",
    "audit_source",
    "readable_labels",
  ],
  day_trader: [
    "market_lists_visible",
    "movers_variants",
    "aapl_capability",
    "typed_criteria",
    "open_hour_schedule",
    "schedule_lifecycle",
  ],
  swing_quant: [
    "versioned_filter",
    "rerun_compare",
    "static_dynamic_watchlists",
    "dynamic_refresh",
    "version_pinned_schedule",
    "schedule_audit",
  ],
};

function pass(label, detail = "") {
  const line = detail ? `${label} — ${detail}` : label;
  passed.push(line);
  console.log(`PASS ${line}`);
}

function journeyPass(persona, key, label, detail = "") {
  const bucket = journeyCoverage.get(persona);
  if (!bucket) throw new Error(`Unknown journey persona: ${persona}`);
  bucket.add(key);
  pass(`Journey ${persona}: ${label}`, detail);
}

function assertJourneyCoverage() {
  const missing = [];
  for (const [persona, required] of Object.entries(journeyRequirements)) {
    const covered = journeyCoverage.get(persona) ?? new Set();
    for (const key of required) {
      if (!covered.has(key)) missing.push(`${persona}.${key}`);
    }
  }
  assert(missing.length === 0, `Missing journey coverage: ${missing.join(", ")}`);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function httpJson(url, options = {}) {
  const res = await fetch(url, options);
  const text = await res.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  return { status: res.status, body };
}

async function dumpDom(path) {
  const url = `${UI_BASE}${path}`;
  const child = spawn(CHROME, [
    "--headless=new",
    "--disable-gpu",
    "--virtual-time-budget=20000",
    "--dump-dom",
    url,
  ]);
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => {
    stdout += chunk.toString();
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });
  const code = await new Promise((resolveExit) => child.on("close", resolveExit));
  if (code !== 0) throw new Error(`Chrome dump-dom failed: ${stderr}`);
  return stdout.replace(/\s+/g, " ").trim();
}

async function waitFor(name, fn, timeoutMs = 60000, intervalMs = 300) {
  const start = Date.now();
  let lastError;
  while (Date.now() - start < timeoutMs) {
    try {
      const value = await fn();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, intervalMs));
  }
  throw new Error(`Timed out waiting for ${name}${lastError ? `: ${lastError.message}` : ""}`);
}

class CdpSession {
  constructor(url) {
    this.nextId = 1;
    this.pending = new Map();
    this.ws = new WebSocket(url);
  }

  static async connect(url) {
    const session = new CdpSession(url);
    await new Promise((resolveOpen, rejectOpen) => {
      session.ws.addEventListener("open", resolveOpen, { once: true });
      session.ws.addEventListener("error", rejectOpen, { once: true });
    });
    session.ws.addEventListener("message", (event) => {
      const payload = JSON.parse(event.data);
      if (!payload.id) return;
      const pending = session.pending.get(payload.id);
      if (!pending) return;
      session.pending.delete(payload.id);
      if (payload.error) pending.reject(new Error(payload.error.message));
      else pending.resolve(payload.result);
    });
    return session;
  }

  send(method, params = {}) {
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolveSend, rejectSend) => {
      this.pending.set(id, { resolve: resolveSend, reject: rejectSend });
    });
  }

  close() {
    this.ws.close();
  }
}

function asExpression(fn, arg) {
  return `(${fn.toString()})(${JSON.stringify(arg)})`;
}

async function evalPage(session, fn, arg, description) {
  const result = await session.send("Runtime.evaluate", {
    expression: asExpression(fn, arg),
    awaitPromise: true,
    returnByValue: true,
    userGesture: true,
  });
  if (result.exceptionDetails) {
    const exception = result.exceptionDetails.exception;
    const detail = exception?.description ?? exception?.value ?? result.exceptionDetails.text;
    throw new Error(`${description}: ${detail}`);
  }
  return result.result?.value;
}

async function browserApi(session, path, options = {}) {
  const response = await evalPage(
    session,
    async ({ path: apiPath, options: requestOptions }) => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), requestOptions.timeoutMs ?? 120000);
      try {
        const res = await fetch(apiPath, {
          method: requestOptions.method ?? "GET",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body:
            requestOptions.body === undefined
              ? undefined
              : JSON.stringify(requestOptions.body),
          signal: controller.signal,
        });
        const text = await res.text();
        let body = null;
        if (text) {
          try {
            body = JSON.parse(text);
          } catch {
            body = text;
          }
        }
        return { status: res.status, body };
      } finally {
        clearTimeout(timeout);
      }
    },
    { path, options },
    `browser fetch ${path}`,
  );
  const expected = options.expected ?? [200];
  assert(
    expected.includes(response.status),
    `${path} returned ${response.status}: ${JSON.stringify(response.body)}`,
  );
  return response.body;
}

async function navigate(session, path) {
  await session.send("Page.navigate", { url: `${UI_BASE}${path}` });
  await waitFor(`navigate ${path}`, () =>
    evalPage(
      session,
      (expectedPath) =>
        location.pathname === expectedPath &&
        ["interactive", "complete"].includes(document.readyState),
      path,
      `wait for ${path}`,
    ),
  );
}

async function bodyText(session) {
  return evalPage(
    session,
    () => document.body.innerText.replace(/\s+/g, " ").trim(),
    null,
    "read body",
  );
}

async function waitForText(session, text, timeoutMs = 60000) {
  return waitFor(`text ${text}`, async () => (await bodyText(session)).includes(text), timeoutMs);
}

async function clickMarketListRun(session, label) {
  return waitFor(
    `market list Run ${label}`,
    () =>
      evalPage(
        session,
        (targetLabel) => {
          const nodes = Array.from(document.querySelectorAll("div"));
          const card = nodes
            .filter(
              (node) =>
                node.innerText?.includes(targetLabel) &&
                Array.from(node.querySelectorAll("button")).some(
                  (candidate) => candidate.innerText.trim() === "Run" && !candidate.disabled,
                ),
            )
            .sort((a, b) => a.innerText.length - b.innerText.length)[0];
          if (!card) throw new Error(`Market list card not found: ${targetLabel}`);
          const button = Array.from(card.querySelectorAll("button")).find(
            (candidate) => candidate.innerText.trim() === "Run" && !candidate.disabled,
          );
          if (!button) throw new Error(`Run button not found for ${targetLabel}`);
          button.scrollIntoView({ block: "center" });
          button.click();
          return true;
        },
        label,
        `click Run for ${label}`,
      ),
    60000,
  );
}

async function clickButtonByText(session, label, options = {}) {
  const point = await waitFor(
    `button ${label}`,
    () =>
      evalPage(
        session,
        ({ label: targetLabel, scopeText = null, exact = false }) => {
          const isVisible = (node) => {
            const rect = node.getBoundingClientRect();
            const style = window.getComputedStyle(node);
            return (
              rect.width > 0 &&
              rect.height > 0 &&
              rect.right > 0 &&
              rect.bottom > 0 &&
              rect.left < window.innerWidth &&
              rect.top < window.innerHeight &&
              style.display !== "none" &&
              style.visibility !== "hidden" &&
              style.pointerEvents !== "none" &&
              !node.closest('[data-state="closed"], [aria-hidden="true"], [inert]')
            );
          };
          const matchesText = (value) => {
            const text = value?.replace(/\s+/g, " ").trim() ?? "";
            return exact ? text === targetLabel : text.includes(targetLabel);
          };
          const candidates = Array.from(document.querySelectorAll("button")).filter((button) => {
            if (button.disabled || !isVisible(button) || !matchesText(button.innerText)) return false;
            if (!scopeText) return true;
            return Boolean(
              Array.from(document.querySelectorAll("div, section, article, form"))
                .filter((node) => isVisible(node) && node.innerText?.includes(scopeText) && node.contains(button))
                .sort((a, b) => a.innerText.length - b.innerText.length)[0],
            );
          });
          const button = candidates[0];
          if (!button) {
            const available = Array.from(document.querySelectorAll("button"))
              .map((node) => `[${node.disabled ? "disabled" : "enabled"}] ${node.innerText?.replace(/\s+/g, " ").trim()}`)
              .join(" | ");
            throw new Error(`Button not found: ${targetLabel}; available: ${available}`);
          }
          button.scrollIntoView({ block: "center" });
          const rect = button.getBoundingClientRect();
          return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        },
        { label, ...options },
        `click button ${label}`,
      ),
    60000,
  );
  await session.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: point.x, y: point.y });
  await session.send("Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: point.x,
    y: point.y,
    button: "left",
    clickCount: 1,
  });
  await session.send("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: point.x,
    y: point.y,
    button: "left",
    clickCount: 1,
  });
  return true;
}

async function clickScheduleButton(session, scheduleName, buttonLabel) {
  return waitFor(
    `schedule button ${buttonLabel} for ${scheduleName}`,
    () =>
      evalPage(
        session,
        ({ scheduleName: targetName, buttonLabel: targetLabel }) => {
          const isVisible = (node) => {
            const rect = node.getBoundingClientRect();
            const style = window.getComputedStyle(node);
            return (
              rect.width > 0 &&
              rect.height > 0 &&
              style.display !== "none" &&
              style.visibility !== "hidden" &&
              !node.closest('[data-state="closed"], [aria-hidden="true"], [inert]')
            );
          };
          const card = Array.from(document.querySelectorAll("div"))
            .filter(
              (node) =>
                isVisible(node) &&
                node.innerText?.includes(targetName) &&
                Array.from(node.querySelectorAll("button")).some(
                  (button) => button.innerText.trim() === targetLabel && !button.disabled,
                ),
            )
            .sort((a, b) => a.innerText.length - b.innerText.length)[0];
          if (!card) throw new Error(`Schedule card not found: ${targetName}`);
          const button = Array.from(card.querySelectorAll("button")).find(
            (candidate) => candidate.innerText.trim() === targetLabel && !candidate.disabled,
          );
          if (!button) throw new Error(`Schedule button not found: ${targetLabel}`);
          button.scrollIntoView({ block: "center" });
          button.click();
          return true;
        },
        { scheduleName, buttonLabel },
        `click schedule ${buttonLabel}`,
      ),
    60000,
  );
}

async function setControlByLabel(session, label, value) {
  return waitFor(
    `control ${label}`,
    () =>
      evalPage(
        session,
        ({ label: targetLabel, value: nextValue }) => {
          const isVisible = (node) => {
            const rect = node.getBoundingClientRect();
            const style = window.getComputedStyle(node);
            return (
              rect.width > 0 &&
              rect.height > 0 &&
              rect.right > 0 &&
              rect.bottom > 0 &&
              rect.left < window.innerWidth &&
              rect.top < window.innerHeight &&
              style.display !== "none" &&
              style.visibility !== "hidden" &&
              style.pointerEvents !== "none" &&
              !node.closest('[data-state="closed"], [aria-hidden="true"], [inert]')
            );
          };
          const labels = Array.from(document.querySelectorAll("label"));
          const labelNode = labels.find((node) =>
            isVisible(node) && node.innerText?.replace(/\s+/g, " ").trim().startsWith(targetLabel),
          );
          if (!labelNode) throw new Error(`Label not found: ${targetLabel}`);
          const control = labelNode.querySelector("input, textarea, select");
          if (!control) throw new Error(`Control not found for label: ${targetLabel}`);
          const proto =
            control instanceof HTMLTextAreaElement
              ? HTMLTextAreaElement.prototype
              : control instanceof HTMLSelectElement
                ? HTMLSelectElement.prototype
                : HTMLInputElement.prototype;
          Object.getOwnPropertyDescriptor(proto, "value").set.call(control, String(nextValue));
          control.dispatchEvent(new Event("input", { bubbles: true }));
          control.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        },
        { label, value },
        `set ${label}`,
      ),
    60000,
  );
}

async function clickCheckboxByLabel(session, label) {
  return evalPage(
    session,
    (targetLabel) => {
      const isVisible = (node) => {
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        return (
          rect.width > 0 &&
          rect.height > 0 &&
          rect.right > 0 &&
          rect.bottom > 0 &&
          rect.left < window.innerWidth &&
          rect.top < window.innerHeight &&
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          style.pointerEvents !== "none" &&
          !node.closest('[data-state="closed"], [aria-hidden="true"], [inert]')
        );
      };
      const labelNode = Array.from(document.querySelectorAll("label")).find((node) =>
        isVisible(node) && node.innerText?.replace(/\s+/g, " ").trim().includes(targetLabel),
      );
      if (!labelNode) throw new Error(`Checkbox label not found: ${targetLabel}`);
      const checkbox = labelNode.querySelector('input[type="checkbox"]');
      if (!checkbox) throw new Error(`Checkbox not found for label: ${targetLabel}`);
      if (!checkbox.checked) {
        checkbox.scrollIntoView({ block: "center" });
        checkbox.click();
      }
      return true;
    },
    label,
    `check ${label}`,
  );
}

async function setLastCriterionRow(session, metric, operator, value) {
  return evalPage(
    session,
    ({ metric: requestedMetric, operator, value }) => {
      const isVisible = (node) => {
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        return (
          rect.width > 0 &&
          rect.height > 0 &&
          rect.right > 0 &&
          rect.bottom > 0 &&
          rect.left < window.innerWidth &&
          rect.top < window.innerHeight &&
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          style.pointerEvents !== "none" &&
          !node.closest('[data-state="closed"], [aria-hidden="true"], [inert]')
        );
      };
      const rows = Array.from(document.querySelectorAll("div"))
        .filter((node) => isVisible(node) && node.querySelectorAll("select").length >= 2 && node.querySelector("input"));
      const row = rows.at(-1);
      if (!row) throw new Error("Criterion row not found");
      const [metricSelect, operatorSelect] = Array.from(row.querySelectorAll("select"));
      const input = row.querySelector("input");
      const setSelect = (select, nextValue) => {
        if (!Array.from(select.options).some((option) => option.value === nextValue)) {
          const available = Array.from(select.options).map((o) => o.value).join(", ");
          throw new Error(`Select option not found: ${nextValue}; available: ${available}`);
        }
        Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(select, nextValue);
        select.dispatchEvent(new Event("input", { bubbles: true }));
        select.dispatchEvent(new Event("change", { bubbles: true }));
      };
      // Resolve metric: use first available option when caller passes null.
      // This avoids hardcoding option values that may change when the backend
      // adds or renames metrics.
      const resolvedMetric =
        requestedMetric !== null
          ? requestedMetric
          : (Array.from(metricSelect.options)[0]?.value ?? null);
      if (resolvedMetric === null) throw new Error("Metric select has no options");
      setSelect(metricSelect, resolvedMetric);
      setSelect(operatorSelect, operator);
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, String(value));
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return resolvedMetric;
    },
    { metric, operator, value },
    "set criterion row",
  );
}

async function firstUsableStrategy(session) {
  const strategies = await browserApi(session, "/api/v1/strategies/v4/");
  const strategy = strategies.find((item) => item.head_version_id);
  assert(strategy, "No strategy version available for Deployment UI attachment walkthrough");
  return strategy;
}

async function firstUsableAccount(session) {
  const accounts = await browserApi(session, "/api/v1/broker-accounts");
  const account = accounts.accounts[0];
  assert(account, "No broker account available for Deployment UI attachment walkthrough");
  return account;
}

async function runUiOperatorPass(session) {
  await navigate(session, "/screeners");
  await clickButtonByText(session, "AI Composer");
  await waitForText(session, "AI is advisory only");
  const aiName = `Headless UI AI ${stamp}`;
  await setControlByLabel(session, "Screener name", aiName);
  await setControlByLabel(
    session,
    "Prompt",
    "Find fractionable stocks under $30 with RVOL over 3 and avoid earnings",
  );
  const aiDraft = await browserApi(session, "/api/v1/screeners/ai/interpret", {
    method: "POST",
    body: {
      prompt: "Find fractionable stocks under $30 with RVOL over 3 and avoid earnings",
      operator_session_id: `headless-ui-${stamp}`,
    },
  });
  assert(aiDraft.advisory_only === true, "AI composer API did not stay advisory-only");
  assert(aiDraft.audit_preview?.mutation === "none", "AI composer API claimed a mutation");
  assert(aiDraft.unsupported_clauses.length > 0, "AI composer API did not surface unsupported clauses");
  pass("UI AI Composer drawer exposes advisory controls", "typed compiler verified through browser API");
  journeyPass("operator", "ai_advisory", "AI Composer is advisory-only", "mutation=none");
  await clickButtonByText(session, "Cancel");

  for (const label of ["Day Losers", "Most Active"]) {
    await navigate(session, "/screeners");
    await waitForText(session, label, 60000);
    await clickMarketListRun(session, label);
    await waitFor(
      `${label} detail navigation`,
      () =>
        evalPage(
          session,
          (expectedLabel) => location.pathname.startsWith("/screeners/") && document.body.innerText.includes(expectedLabel),
          label,
          `wait for ${label} navigation`,
        ),
      180000,
    );
    const variantId = await evalPage(session, () => location.pathname.split("/").filter(Boolean).at(-1), null, "read variant id");
    const variantRuns = await browserApi(session, `/api/v1/screeners/${variantId}/runs`);
    assert(variantRuns.runs[0]?.status === "completed", `${label} market-list UI run did not complete`);
    assert(
      JSON.stringify(variantRuns.runs[0]?.source_evidence ?? {}).toLowerCase().includes("alpaca"),
      `${label} market-list run did not retain Alpaca source evidence`,
    );
    await browserApi(session, `/api/v1/screeners/${variantId}/archive`, { method: "POST" });
  }
  pass("UI runs additional Alpaca market-list variants", "Day Losers and Most Active");
  journeyPass("day_trader", "movers_variants", "Day Losers and Most Active market-list variants");

  await navigate(session, "/screeners");
  await clickButtonByText(session, "New Screener");
  await waitForText(session, "Pick a universe source and visible typed criteria");
  const screenerName = `Headless UI Criteria ${stamp}`;
  await setControlByLabel(session, "Display name", screenerName);
  await setControlByLabel(session, "Description (optional)", "UI-driven typed criteria walkthrough");
  await clickButtonByText(session, "Add criterion");
  await setLastCriterionRow(session, null, "lte", 50);
  pass("UI typed criteria drawer exposes editable metric/operator/value controls", screenerName);
  journeyPass("day_trader", "typed_criteria", "Typed metric/operator/value controls work");
  await clickButtonByText(session, "Cancel");

  const strategy = await firstUsableStrategy(session);
  await navigate(session, "/deployments");
  await clickButtonByText(session, "New Deployment");
  await waitForText(session, "The Deployment publishes SignalPlans");
  await setControlByLabel(session, "Display name", `Headless UI Entry Deployment ${stamp}`);
  await setControlByLabel(session, "Strategy", strategy.strategy_v4_id);
  await waitFor("strategy versions load", async () => {
    const text = await bodyText(session);
    return text.includes("Strategy version") && !text.includes("No Strategy versions");
  });
  await setControlByLabel(session, "Strategy version", strategy.head_version_id);
  pass("UI Deployment drawer accepts current Strategy version", strategy.name);
  await clickButtonByText(session, "Cancel");
}

async function createScheduleFromVisibleControls(session, { name, cadence = "daily", timeOfDay = "09:15", approvalPolicy = null }) {
  await clickButtonByText(session, "New schedule");
  await waitForText(session, "Save schedule");
  await setControlByLabel(session, "Schedule name", name);
  await setControlByLabel(session, "Cadence", cadence);
  if (cadence === "every_n_minutes") {
    await setControlByLabel(session, "Interval minutes", "15");
    await setControlByLabel(session, "Session start", "09:30");
    await setControlByLabel(session, "Session end", "10:30");
  } else {
    await setControlByLabel(session, "Time of day", timeOfDay);
  }
  await setControlByLabel(session, "Timezone", "America/New_York");
  if (approvalPolicy) {
    await setControlByLabel(session, "Approval policy", approvalPolicy);
  }
  await clickButtonByText(session, "Save schedule");
  await waitFor(
    `schedule persisted ${name}`,
    async () => {
      const schedules = await browserApi(session, "/api/v1/discovery-schedules");
      return schedules.schedules.some((item) => item.name === name);
    },
    60000,
  );
  await waitForText(session, name, 60000);
}

async function exerciseVisibleSchedule(session, name) {
  const visible = await bodyText(session);
  assert(visible.includes("Run schedule now") && visible.includes("Edit") && visible.includes("Pause"), `Schedule controls not visible for ${name}`);
  const schedules = await browserApi(session, "/api/v1/discovery-schedules");
  const schedule = schedules.schedules.find((item) => item.name === name);
  assert(schedule, `Schedule not found: ${name}`);
  await clickScheduleButton(session, name, "Run schedule now");
  const execution = await waitFor(
    `schedule run-now completed ${name}`,
    async () => {
      const executions = await browserApi(session, `/api/v1/discovery-schedules/${schedule.schedule_id}/executions`);
      return executions.executions.find((item) => item.status === "completed");
    },
    180000,
  );
  assert(execution.status === "completed", `Schedule run-now did not complete: ${execution.error}`);
  await waitForText(session, "Execution history", 60000);

  await clickScheduleButton(session, name, "Pause");
  await waitFor(
    `schedule paused ${name}`,
    async () => {
      const updated = await browserApi(session, `/api/v1/discovery-schedules/${schedule.schedule_id}`);
      return updated.status === "paused";
    },
    60000,
  );
  await clickScheduleButton(session, name, "Resume");
  await waitFor(
    `schedule resumed ${name}`,
    async () => {
      const updated = await browserApi(session, `/api/v1/discovery-schedules/${schedule.schedule_id}`);
      return updated.status === "active";
    },
    60000,
  );
  await clickScheduleButton(session, name, "Archive");
  await waitFor(
    `schedule archived ${name}`,
    async () => {
      const updated = await browserApi(session, `/api/v1/discovery-schedules/${schedule.schedule_id}`);
      return updated.status === "archived";
    },
    60000,
  );
}

function appendFractionableCriterion(expression) {
  const fractionable = {
    kind: "criterion",
    criterion: {
      metric: "broker.fractionable",
      operator: "eq",
      value: true,
      value_max: null,
      label: "Fractionable at Alpaca",
    },
    children: [],
  };
  const base =
    expression && expression.kind === "all"
      ? expression.children ?? []
      : expression
        ? [expression]
        : [];
  return { kind: "all", criterion: null, children: [...base, fractionable] };
}

async function verifyAaplCapabilityEvidence(session) {
  const capabilityScreener = await browserApi(session, "/api/v1/screeners", {
    method: "POST",
    expected: [201],
    body: {
      name: `Headless AAPL Capability ${stamp}`,
      description: "Regression guard for Alpaca tradability evidence",
      tags: ["headless_walkthrough", "capability_regression"],
      universe_source: { kind: "explicit", symbols: ["AAPL"] },
      criteria: [],
      expression: {
        kind: "criterion",
        criterion: {
          metric: "broker.tradable",
          operator: "eq",
          value: true,
          value_max: null,
          label: "Tradable at Alpaca",
        },
        children: [],
      },
      timeframe: "1d",
      source_preference: "alpaca",
      sort_metric: null,
      sort_descending: true,
      max_results: 10,
    },
  });
  const run = await browserApi(session, `/api/v1/screeners/${capabilityScreener.screener.id}/run`, {
    method: "POST",
    body: { operator_session_id: `headless-aapl-${stamp}` },
    timeoutMs: 180000,
  });
  const aapl = run.results.find((row) => row.symbol === "AAPL");
  assert(aapl, "AAPL capability run did not return an AAPL row");
  assert(aapl.metrics["broker.tradable"] === true, "AAPL did not return broker.tradable=true");
  assert(
    !aapl.blocked_reasons.some((reason) => reason.includes("asset is not tradable at Alpaca")),
    `AAPL returned a false not-tradable reason: ${aapl.blocked_reasons.join("; ")}`,
  );
  await browserApi(session, `/api/v1/screeners/${capabilityScreener.screener.id}/archive`, {
    method: "POST",
  });
  journeyPass("day_trader", "aapl_capability", "AAPL capability evidence stays true", "Alpaca tradable=true");
}

let chrome;
let session;

try {
  const backend = await httpJson(`${API_BASE}/api/v1/screeners`);
  assert(backend.status === 200, `Backend not ready: /screeners ${backend.status}`);
  const ui = await httpJson(`${UI_BASE}/screeners`);
  assert(ui.status === 200, `Frontend not ready: /screeners ${ui.status}`);

  chrome = spawn(CHROME, [
    "--headless=new",
    `--remote-debugging-port=${remotePort}`,
    `--user-data-dir=${userDataDir}`,
    "--disable-gpu",
    "--disable-web-security",
    "--no-first-run",
    "--no-default-browser-check",
    "--window-size=1440,1000",
    "about:blank",
  ]);

  chrome.stderr.on("data", (chunk) => process.stderr.write(chunk));
  chrome.stdout.on("data", (chunk) => process.stdout.write(chunk));

  await waitFor("Chrome DevTools", async () => {
    try {
      const result = await httpJson(`http://127.0.0.1:${remotePort}/json/new?about:blank`, {
        method: "PUT",
      });
      return result.status === 200 ? result.body : false;
    } catch {
      return false;
    }
  }, 30000);

  const target = await httpJson(`http://127.0.0.1:${remotePort}/json/new?about:blank`, {
    method: "PUT",
  });
  session = await CdpSession.connect(target.body.webSocketDebuggerUrl);
  await session.send("Page.enable");
  await session.send("Runtime.enable");
  await session.send("Network.enable");
  await session.send("Page.addScriptToEvaluateOnNewDocument", {
    source: `window.__UTOS_API_BASE__ = ${JSON.stringify(API_BASE)};`,
  });

  await navigate(session, "/screeners");
  await waitForText(session, "Alpaca Market Lists");
  await waitForText(session, "AI Composer");
  assert(!(await bodyText(session)).includes("Could not load screeners"), "Screeners page displayed load failure");
  pass("Screeners page loaded", "market lists, templates, and AI entry points visible");
  journeyPass("operator", "screeners_loaded", "Screeners discovery surface loads");
  journeyPass("day_trader", "market_lists_visible", "Alpaca market-list entry points visible");

  await runUiOperatorPass(session);
  await verifyAaplCapabilityEvidence(session);

  await navigate(session, "/screeners");
  await waitForText(session, "Day Gainers", 60000);
  await clickMarketListRun(session, "Day Gainers");
  await waitFor(
    "Day Gainers detail navigation",
    () =>
      evalPage(
        session,
        () => location.pathname.startsWith("/screeners/") && document.body.innerText.includes("Day Gainers"),
        null,
        "wait for market-list run navigation",
      ),
    180000,
  );
  const screenerId = await evalPage(
    session,
    () => location.pathname.split("/").filter(Boolean).at(-1),
    null,
    "read screener id",
  );
  let runs = await browserApi(session, `/api/v1/screeners/${screenerId}/runs`);
  const marketRun = runs.runs[0];
  assert(marketRun.status === "completed", `Market-list run did not complete: ${marketRun.error}`);
  assert(marketRun.universe_size > 0, "Market-list run produced an empty universe");
  pass("Run Alpaca Day Gainers", `${marketRun.universe_size} candidates / ${marketRun.matched_count} matches`);

  const detail = await browserApi(session, `/api/v1/screeners/${screenerId}`);
  const latest = detail.versions.at(-1);
  const editedVersion = await browserApi(session, `/api/v1/screeners/${screenerId}/versions`, {
    method: "POST",
    body: {
      name: `Headless fractionable ${stamp}`,
      description: "Headless walkthrough version with broker fractionable gate",
      tags: ["headless_walkthrough"],
      universe_source: latest.universe_source,
      criteria: latest.criteria ?? [],
      expression: appendFractionableCriterion(latest.expression),
      timeframe: latest.timeframe,
      source_preference: "alpaca",
      sort_metric: latest.sort_metric,
      sort_descending: latest.sort_descending,
      max_results: latest.max_results,
    },
  });
  assert(editedVersion.expression.children.some((child) => child.criterion?.metric === "broker.fractionable"));
  pass("Edit Screener and add broker fractionable filter", editedVersion.id);
  journeyPass("swing_quant", "versioned_filter", "Versioned broker-capability filter", editedVersion.id);

  const filteredRun = await browserApi(session, `/api/v1/screeners/${screenerId}/run`, {
    method: "POST",
    body: { version_id: editedVersion.id, operator_session_id: `headless-${stamp}` },
    timeoutMs: 180000,
  });
  assert(filteredRun.status === "completed", `Filtered run failed: ${filteredRun.error}`);
  assert(filteredRun.matched_count > 0, "Filtered run had no matched symbols to save");
  pass("Run edited Screener", `${filteredRun.matched_count} fractionable matches`);

  const rerun = await browserApi(session, `/api/v1/screeners/runs/${filteredRun.id}/rerun`, {
    method: "POST",
    body: { operator_session_id: `headless-${stamp}` },
    timeoutMs: 180000,
  });
  assert(rerun.status === "completed", `Rerun failed: ${rerun.error}`);
  assert(rerun.parent_run_id === filteredRun.id, "Rerun lineage did not point to parent run");
  assert(Object.keys(rerun.source_evidence ?? {}).length > 0, "Rerun did not retain source evidence");
  pass("Rerun pinned version", rerun.id);

  const diff = await browserApi(
    session,
    `/api/v1/screeners/runs/${rerun.id}/diff?against_run_id=${filteredRun.id}`,
  );
  assert(Array.isArray(diff.added) && Array.isArray(diff.removed) && Array.isArray(diff.stayed));
  pass("Compare runs", `added=${diff.added.length} removed=${diff.removed.length} stayed=${diff.stayed.length}`);
  journeyPass("swing_quant", "rerun_compare", "Rerun and compare pinned version", `stayed=${diff.stayed.length}`);

  await navigate(session, `/screeners/${screenerId}`);
  await waitForText(session, "Results:");
  await waitForText(session, "Save selected matches");
  pass("Run detail UI shows results and save action");

  await waitForText(session, "Schedules");
  const screenerScheduleName = `Headless Screener Schedule ${stamp}`;
  await createScheduleFromVisibleControls(session, {
    name: screenerScheduleName,
    cadence: "daily",
    timeOfDay: "09:15",
  });
  const scheduleListAfterScreenerCreate = await browserApi(session, "/api/v1/discovery-schedules");
  const screenerSchedule = scheduleListAfterScreenerCreate.schedules.find((item) => item.name === screenerScheduleName);
  assert(screenerSchedule?.target_kind === "screener_run", "Screener schedule was not persisted with screener_run target");
  assert(screenerSchedule.screener_version_id === editedVersion.id, "Screener schedule did not pin the edited version");
  await exerciseVisibleSchedule(session, screenerScheduleName);
  pass("Schedule Screener run from UI", screenerScheduleName);
  journeyPass("day_trader", "open_hour_schedule", "Premarket Screener schedule visible", "09:15 America/New_York");
  journeyPass("swing_quant", "version_pinned_schedule", "Schedule pins exact ScreenerVersion", editedVersion.id);

  const staticWatchlist = await browserApi(session, `/api/v1/screeners/runs/${rerun.id}/save-as-watchlist`, {
    method: "POST",
    body: {
      name: `Headless Static Entries ${stamp}`,
      description: "Headless static entry Watchlist",
      only_matched: true,
      kind: "static",
    },
  });
  assert(staticWatchlist.symbol_count > 0, "Static Watchlist saved zero symbols");
  pass("Save matched symbols as static Watchlist", `${staticWatchlist.symbol_count} symbols`);
  journeyPass("operator", "save_watchlist", "Save matched results as Watchlist", staticWatchlist.name);

  const dynamicWatchlist = await browserApi(session, `/api/v1/screeners/runs/${rerun.id}/save-as-watchlist`, {
    method: "POST",
    body: {
      name: `Headless Dynamic Entries ${stamp}`,
      description: "Headless dynamic entry Watchlist",
      only_matched: true,
      kind: "dynamic",
    },
  });
  pass("Create dynamic Watchlist from ScreenerVersion", dynamicWatchlist.name);
  journeyPass("swing_quant", "static_dynamic_watchlists", "Static and dynamic Watchlists created");

  const snapshot = await browserApi(session, `/api/v1/watchlists/${dynamicWatchlist.watchlist_id}/refresh`, {
    method: "POST",
    body: { note: "headless walkthrough refresh" },
    timeoutMs: 180000,
  });
  assert(snapshot.symbols.length > 0, "Dynamic Watchlist refresh produced no symbols");
  assert(snapshot.source_run_id, "Dynamic Watchlist refresh did not record source_run_id");
  pass("Refresh dynamic Watchlist snapshot", `${snapshot.symbols.length} symbols`);
  journeyPass("swing_quant", "dynamic_refresh", "Dynamic Watchlist refresh records snapshot", snapshot.source_run_id);

  await navigate(session, "/watchlists");
  await waitForText(session, dynamicWatchlist.name);
  await waitForText(session, "Dynamic");
  pass("Watchlist Manager shows dynamic Watchlist");

  await clickButtonByText(session, "Open", { scopeText: dynamicWatchlist.name, exact: true });
  await waitForText(session, "Entry Watchlist detail");
  await waitForText(session, "Schedules");
  const watchlistScheduleName = `Headless Watchlist Schedule ${stamp}`;
  const visibleWatchlistScheduleControls = await bodyText(session);
  assert(visibleWatchlistScheduleControls.includes("New schedule"), "Watchlist schedule controls are not visible");
  await createScheduleFromVisibleControls(session, {
    name: watchlistScheduleName,
    cadence: "every_n_minutes",
    approvalPolicy: "auto_snapshot",
  });
  await navigate(session, "/watchlists");
  await waitForText(session, dynamicWatchlist.name);
  await clickButtonByText(session, "Open", { scopeText: dynamicWatchlist.name, exact: true });
  await waitForText(session, watchlistScheduleName, 60000);
  const scheduleListAfterWatchlistCreate = await browserApi(session, "/api/v1/discovery-schedules");
  const watchlistSchedule = scheduleListAfterWatchlistCreate.schedules.find((item) => item.name === watchlistScheduleName);
  assert(watchlistSchedule?.target_kind === "watchlist_refresh", "Watchlist schedule target was not persisted");
  assert(watchlistSchedule.watchlist_id === dynamicWatchlist.watchlist_id, "Watchlist schedule did not pin the Watchlist");
  assert(watchlistSchedule.approval_policy === "auto_snapshot", "Watchlist schedule did not persist approval policy");
  await exerciseVisibleSchedule(session, watchlistScheduleName);
  pass("Schedule Watchlist refresh from UI", watchlistScheduleName);
  journeyPass("day_trader", "schedule_lifecycle", "Schedule run-now/pause/resume/archive lifecycle", watchlistScheduleName);
  journeyPass("swing_quant", "schedule_audit", "Watchlist refresh schedule audit lifecycle", watchlistScheduleName);

  const strategies = await browserApi(session, "/api/v1/strategies/v4/");
  const strategy = strategies.find((item) => item.head_version_id);
  const accounts = await browserApi(session, "/api/v1/broker-accounts");
  assert(strategy, "No strategy version available for Deployment attachment walkthrough");
  assert(accounts.accounts.length > 0, "No broker account available for Deployment attachment walkthrough");
  const deployment = await browserApi(session, "/api/v1/deployments", {
    method: "POST",
    body: {
      name: `Headless Entry Deployment ${stamp}`,
      description: "Headless walkthrough deployment; entries from Watchlist only",
      strategy_version_v4_id: strategy.head_version_id,
      watchlist_ids: [dynamicWatchlist.watchlist_id],
      subscribed_account_ids: [accounts.accounts[0].id],
      runtime_overrides: { source: "headless_screener_watchlist_walkthrough" },
    },
  });
  pass("Attach Watchlist to Deployment entry universe", deployment.deployment.name);

  await navigate(session, "/deployments");
  await waitForText(session, deployment.deployment.name, 180000);
  await waitForText(session, "exits from Account-owned Positions");
  const deploymentDom = await dumpDom("/deployments");
  assert(deploymentDom.includes(deployment.deployment.name), "Deployment DOM did not include created deployment");
  assert(deploymentDom.includes(dynamicWatchlist.name), "Deployment DOM did not include readable Watchlist name");
  assert(
    deploymentDom.includes("Entries come from Watchlists. Exits come from Account-owned Positions scoped to this Deployment."),
    "Deployment DOM did not include entry/exit doctrine copy",
  );
  pass("Deployment UI confirms entry/exit doctrine");
  journeyPass("operator", "deployment_doctrine", "Deployment explains entries and exits");
  journeyPass("operator", "readable_labels", "Deployment and Watchlist names are readable", dynamicWatchlist.name);

  const blockedDelete = await browserApi(session, `/api/v1/screeners/${screenerId}/delete`, {
    method: "POST",
    expected: [409],
  });
  assert(String(blockedDelete.detail ?? "").includes("run history"), "Unsafe Screener delete did not explain run history");
  pass("Unsafe delete blocked with readable reason", blockedDelete.detail);
  journeyPass("operator", "unsafe_delete_guard", "Unsafe delete blocked", blockedDelete.detail);

  const archived = await browserApi(session, `/api/v1/screeners/${screenerId}/archive`, {
    method: "POST",
  });
  assert(archived.screener.status === "archived", "Screener archive did not return archived status");
  pass("Archive Screener safely", archived.screener.status);

  const ai = await browserApi(session, "/api/v1/screeners/ai/interpret", {
    method: "POST",
    body: {
      prompt: "Find fractionable stocks under $30 with RVOL over 3 and avoid earnings",
      operator_session_id: `headless-${stamp}`,
    },
  });
  assert(ai.advisory_only === true, "AI composer response was not advisory-only");
  assert(ai.audit_preview?.mutation === "none", "AI composer audit preview claimed mutation");
  assert(ai.unsupported_clauses.length > 0, "AI composer did not surface unsupported earnings clause");
  pass("AI advisory composer reviewed", "typed rules visible, mutation=none, unsupported clause surfaced");

  await navigate(session, `/screeners/${screenerId}`);
  await waitForText(session, "Results:");
  const screenshot = await session.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: true,
  });
  writeFileSync(screenshotPath, Buffer.from(screenshot.data, "base64"));
  pass("Audit/source UI reviewed", screenshotPath);
  journeyPass("operator", "audit_source", "Audit and source evidence reviewed", screenshotPath);

  assertJourneyCoverage();
  pass("All persona journeys covered", Object.keys(journeyRequirements).join(", "));

  console.log(`\nHeadless walkthrough complete: ${passed.length} checks passed.`);
} finally {
  if (session) session.close();
  if (chrome && !chrome.killed) chrome.kill();
  try {
    rmSync(userDataDir, { recursive: true, force: true });
  } catch {
    // Best effort cleanup only.
  }
}
