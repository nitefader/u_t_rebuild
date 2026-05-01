/**
 * headless-strategy-compose-v4.mjs
 *
 * Headless smoke test for the Strategy IDE v4 Compose page.
 * Modeled on headless-screener-watchlist.mjs — uses Chrome DevTools Protocol (CDP).
 *
 * Steps verified:
 *   1. Load /strategies/compose-v4
 *   2. Wait for Monaco editor (.monaco-editor)
 *   3. Apply "RSI Mean Reversion" starter from right rail
 *   4. Type a short addition in the entry editor via Monaco model API
 *   5. Click Save and assert URL flips to ?id=…
 *   6. Assert the save banner/pill appears (Saved v…)
 *   7. Screenshot
 *
 * Usage:
 *   node frontend/scripts/headless-strategy-compose-v4.mjs
 *
 * Env vars:
 *   UTOS_UI_BASE   — default http://127.0.0.1:5173
 *   UTOS_API_BASE  — default http://127.0.0.1:8000
 *   CHROME_PATH    — path to Chrome executable
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { spawn } from "node:child_process";

const UI_BASE = process.env.UTOS_UI_BASE ?? "http://127.0.0.1:5173";
const API_BASE = process.env.UTOS_API_BASE ?? "http://127.0.0.1:8000";
const CHROME =
  process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const stamp = new Date().toISOString().replace(/[:.]/g, "-");
const logDir = resolve(process.cwd(), ".runtime_logs");
const userDataDir = join(logDir, `headless-compose-v4-${stamp}`);
const screenshotPath = join(logDir, `headless-compose-v4-${stamp}.png`);
const remotePort = 9700 + Math.floor(Math.random() * 200);

mkdirSync(logDir, { recursive: true });

const passed = [];
const failed = [];

function pass(label, detail = "") {
  const msg = detail ? `PASS ${label} — ${detail}` : `PASS ${label}`;
  console.log(msg);
  passed.push(label);
}

function fail(label, detail = "") {
  const msg = detail ? `FAIL ${label} — ${detail}` : `FAIL ${label}`;
  console.error(msg);
  failed.push(label);
}

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// CDP helpers (modeled on headless-screener-watchlist.mjs)
// ---------------------------------------------------------------------------

async function waitFor(name, fn, timeoutMs = 60000, intervalMs = 400) {
  const start = Date.now();
  let lastError;
  while (Date.now() - start < timeoutMs) {
    try {
      const value = await fn();
      if (value) return value;
    } catch (err) {
      lastError = err;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(`Timed out waiting for ${name}${lastError ? `: ${lastError.message}` : ""}`);
}

class CdpSession {
  static async connect(wsUrl) {
    const session = Object.create(CdpSession.prototype);
    session.nextId = 1;
    session.pending = new Map();
    // Node 24 ships WebSocket globally
    session.ws = new WebSocket(wsUrl);
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
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
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

async function bodyText(session) {
  return evalPage(session, () => document.body.innerText, null, "bodyText");
}

async function waitForText(session, text, timeoutMs = 30000) {
  return waitFor(
    `text "${text}"`,
    async () => {
      const body = await bodyText(session);
      return body.includes(text);
    },
    timeoutMs,
  );
}

async function waitForSelector(session, selector, timeoutMs = 30000) {
  return waitFor(
    `selector ${selector}`,
    () =>
      evalPage(
        session,
        (sel) => !!document.querySelector(sel),
        selector,
        `waitForSelector(${selector})`,
      ),
    timeoutMs,
  );
}

async function navigate(session, path) {
  await session.send("Page.navigate", { url: `${UI_BASE}${path}` });
  await waitFor(
    `navigate ${path}`,
    () =>
      evalPage(
        session,
        (expectedPath) =>
          location.pathname.startsWith(expectedPath) &&
          ["interactive", "complete"].includes(document.readyState),
        path,
        `wait for ${path}`,
      ),
    30000,
  );
  await new Promise((r) => setTimeout(r, 800));
}

async function clickByAriaLabel(session, label) {
  return evalPage(
    session,
    (lbl) => {
      const el = document.querySelector(`[aria-label="${lbl}"]`);
      if (!el) throw new Error(`aria-label not found: ${lbl}`);
      el.click();
    },
    label,
    `clickByAriaLabel(${label})`,
  );
}

async function screenshot(session, path) {
  const result = await session.send("Page.captureScreenshot", { format: "png" });
  writeFileSync(path, Buffer.from(result.data, "base64"));
  console.log(`Screenshot saved: ${path}`);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

let chrome;
let session;

try {
  // Pre-flight: confirm the UI is up
  const ui = await httpJson(`${UI_BASE}/strategies/compose-v4`);
  if (ui.status !== 200) {
    fail("UI reachable", `GET /strategies/compose-v4 returned ${ui.status}`);
    process.exit(1);
  }

  // Spawn Chrome headless
  chrome = spawn(
    CHROME,
    [
      "--headless=new",
      `--remote-debugging-port=${remotePort}`,
      `--user-data-dir=${userDataDir}`,
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "--window-size=1440,900",
      "about:blank",
    ],
    { stdio: ["ignore", "ignore", "ignore"] },
  );

  // Wait for DevTools endpoint
  await waitFor(
    "Chrome DevTools",
    async () => {
      try {
        const result = await httpJson(`http://127.0.0.1:${remotePort}/json/new?about:blank`, {
          method: "PUT",
        });
        return result.status === 200 ? result.body : false;
      } catch {
        return false;
      }
    },
    30000,
  );

  const target = await httpJson(`http://127.0.0.1:${remotePort}/json/new?about:blank`, {
    method: "PUT",
  });
  session = await CdpSession.connect(target.body.webSocketDebuggerUrl);
  await session.send("Page.enable");
  await session.send("Runtime.enable");

  // -----------------------------------------------------------------------
  // Step 1: Navigate to /strategies/compose-v4
  // -----------------------------------------------------------------------
  await navigate(session, "/strategies/compose-v4");

  // Wait for the SPA to render the compose page (Monaco is lazy loaded)
  try {
    await waitForText(session, "Strategy name", 20000);
    pass("compose-v4 page loaded", "Strategy name field visible");
  } catch (e) {
    fail("compose-v4 page loaded", e.message);
  }

  // -----------------------------------------------------------------------
  // Step 2: Wait for Monaco editor
  // -----------------------------------------------------------------------
  try {
    await waitForSelector(session, ".monaco-editor", 30000);
    pass("Monaco editor loaded", ".monaco-editor selector present");
  } catch (e) {
    fail("Monaco editor loaded", e.message);
    // Continue even if Monaco fails - screenshot will show what happened
  }

  // Set strategy name (required for save)
  try {
    await evalPage(
      session,
      (name) => {
        const el = document.querySelector('[aria-label="Strategy name"]');
        if (!el) throw new Error("Strategy name field not found");
        el.focus();
        const nativeInput = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
        if (nativeInput && nativeInput.set) {
          nativeInput.set.call(el, name);
        } else {
          el.value = name;
        }
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      },
      "headless-verify-v4-strategy-2026-05-01",
      "set strategy name",
    );
  } catch (e) {
    fail("Strategy name set", e.message);
  }

  await new Promise((r) => setTimeout(r, 400));

  // -----------------------------------------------------------------------
  // Step 3: Apply RSI Mean Reversion starter
  // Panel is open by default on new page (no ?id= param).
  // Cards in the panel may be collapsed — click the card to expand, then Apply.
  // -----------------------------------------------------------------------
  try {
    await waitForSelector(session, '[data-testid="starter-card"]', 15000);
    // First try clicking Apply directly (in case card is already expanded)
    // If not, click the card header to expand it first
    const applied = await evalPage(
      session,
      () => {
        // Find the RSI Mean Reversion card by text content and click Apply
        const applyBtn = document.querySelector('[aria-label="Apply RSI Mean Reversion template"]');
        if (applyBtn) {
          applyBtn.click();
          return "applied_direct";
        }
        // Try to click the card to expand it first
        const cards = document.querySelectorAll('[data-testid="starter-card"]');
        for (const card of cards) {
          if (card.textContent.includes("RSI Mean Reversion")) {
            // Click the expand button or the card header
            const btn = card.querySelector("button");
            if (btn) {
              btn.click();
              return "expanded_card";
            }
          }
        }
        return "not_found";
      },
      null,
      "click RSI starter",
    );
    await new Promise((r) => setTimeout(r, 800));
    if (applied === "expanded_card") {
      // Now try Apply button after expansion
      await clickByAriaLabel(session, "Apply RSI Mean Reversion template");
      await new Promise((r) => setTimeout(r, 1200));
      pass("RSI Mean Reversion starter applied", "card expanded then applied");
    } else if (applied === "applied_direct") {
      await new Promise((r) => setTimeout(r, 1200));
      pass("RSI Mean Reversion starter applied", "direct apply click");
    } else {
      fail("RSI Mean Reversion starter applied", `card state: ${applied}`);
    }
  } catch (e) {
    fail("RSI Mean Reversion starter applied", e.message);
  }

  // -----------------------------------------------------------------------
  // Step 4: Append text to Monaco entry editor
  // Dispatch via the Monaco editor model API (accessed through window.monaco).
  // -----------------------------------------------------------------------
  try {
    const appended = await evalPage(
      session,
      () => {
        if (!window.monaco) return "no_monaco";
        const editors = window.monaco.editor.getEditors();
        if (!editors.length) return "no_editors";
        // Target the first editor (long entry)
        const editor = editors[0];
        const model = editor.getModel();
        if (!model) return "no_model";
        const current = model.getValue();
        model.setValue(current ? current + "\nAND 1d.volume > 0" : "1d.rsi(14) < 30 AND 1d.volume > 0");
        return "ok";
      },
      null,
      "append Monaco text",
    );
    if (appended === "ok") {
      pass("Entry editor text appended", "Monaco model updated with AND 1d.volume > 0");
    } else {
      fail("Entry editor text appended", `Monaco state: ${appended}`);
    }
  } catch (e) {
    fail("Entry editor text appended", e.message);
  }

  await new Promise((r) => setTimeout(r, 600));

  // -----------------------------------------------------------------------
  // Step 5: Click Save
  // -----------------------------------------------------------------------
  try {
    await clickByAriaLabel(session, "Save strategy");
    pass("Save button clicked");
  } catch (e) {
    fail("Save button clicked", e.message);
  }

  // -----------------------------------------------------------------------
  // Step 6: Wait for URL ?id= and save pill
  // -----------------------------------------------------------------------
  try {
    await waitFor(
      "URL ?id= after save",
      () =>
        evalPage(
          session,
          () => window.location.search.includes("id="),
          null,
          "url id check",
        ),
      20000,
    );
    const savedId = await evalPage(
      session,
      () => new URLSearchParams(window.location.search).get("id"),
      null,
      "read saved id",
    );
    pass("URL flipped to ?id=", `id=${savedId}`);
  } catch (e) {
    fail("URL flipped to ?id=", e.message);
  }

  try {
    await waitFor(
      "Saved pill/banner",
      async () => {
        const text = await bodyText(session);
        return text.toLowerCase().includes("saved v") || text.toLowerCase().includes("saved as");
      },
      15000,
    );
    pass("Save pill/banner visible", "Saved v text confirmed");
  } catch (e) {
    fail("Save pill/banner visible", e.message);
  }

  // -----------------------------------------------------------------------
  // Step 7: Screenshot
  // -----------------------------------------------------------------------
  await screenshot(session, screenshotPath);
  pass("Screenshot captured", screenshotPath);

} catch (err) {
  console.error("FATAL:", err.message);
  failed.push("fatal_error");
} finally {
  if (session) session.close();
  if (chrome) chrome.kill();
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------
console.log("\n--- headless-strategy-compose-v4 summary ---");
console.log(`PASSED: ${passed.length}, FAILED: ${failed.length}`);
for (const f of failed) console.error(`  FAIL: ${f}`);
if (failed.length > 0) process.exit(1);
process.exit(0);
