import assert from "node:assert/strict";
import test from "node:test";

import { mountBrokers } from "../src/brokers.js";


function setupGlobals() {
  globalThis.location = { protocol: "http:", host: "127.0.0.1:5173" };
}

function makeRoot() {
  const document = makeDocument();
  globalThis.document = document;
  return document.createElement("main");
}

function makeDocument() {
  const document = {
    createElement(tag) { return makeElement(tag); },
    createElementNS(_ns, tag) { return makeElement(tag); }
  };
  function makeElement(tag) {
    const el = {
      tagName: tag.toUpperCase(),
      children: [],
      attributes: {},
      classList: { contains() { return false; } },
      style: {},
      dataset: {},
      eventListeners: {},
      get textContent() { return this._text || ""; },
      set textContent(value) { this._text = String(value); },
      get innerHTML() { return this._html || ""; },
      set innerHTML(value) { this._html = String(value); if (value === "") this.children = []; },
      appendChild(child) { this.children.push(child); return child; },
      addEventListener(type, fn) { this.eventListeners[type] = this.eventListeners[type] || []; this.eventListeners[type].push(fn); },
      setAttribute(name, value) { this.attributes[name] = String(value); if (name === "class") this.className = String(value); },
      getAttribute(name) { return this.attributes[name]; }
    };
    return el;
  }
  return document;
}


function makeApi(accounts) {
  const calls = { list: 0, create: 0 };
  return {
    calls,
    async list() {
      calls.list++;
      return { accounts };
    },
    async createAlpacaPaper(payload) {
      calls.create++;
      return { account: { ...payload, id: "new-id", mode: "BROKER_PAPER" }, already_exists: false };
    },
    async replaceAlpacaPaperCredentials() { return {}; },
    async deleteAccount() { return { status: "ARCHIVED" }; }
  };
}


test("Brokers page lists accounts returned by the API", async () => {
  setupGlobals();
  const root = makeRoot();
  const account = {
    id: "11111111-2222-3333-4444-555555555555",
    display_name: "Algo Trading - Paper",
    provider: "alpaca",
    mode: "BROKER_PAPER",
    external_account_id: "PA12345",
    last_account_snapshot: {
      equity: 100000,
      cash: 99500,
      buying_power: 100000,
      daytrading_buying_power: 100000,
      pattern_day_trader: false,
      account_status: "ACTIVE"
    },
    broker_sync_freshness: {
      account_id: "11111111-2222-3333-4444-555555555555",
      last_sync_at: new Date().toISOString(),
      is_stale: false
    }
  };
  const api = makeApi([account]);
  const page = mountBrokers(root, api);
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(api.calls.list, 1);
  assert.equal(page.state.accounts.length, 1);
});


test("Brokers page surfaces stale-sync flag", async () => {
  setupGlobals();
  const root = makeRoot();
  const account = {
    id: "22222222-2222-2222-2222-222222222222",
    display_name: "Stale Account",
    provider: "alpaca",
    mode: "BROKER_PAPER",
    broker_sync_freshness: { is_stale: true, stale_reason: "broker_sync_stale" }
  };
  const api = makeApi([account]);
  const page = mountBrokers(root, api);
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(page.state.accounts[0].broker_sync_freshness.is_stale, true);
});


test("Brokers page records error state on API failure", async () => {
  setupGlobals();
  const root = makeRoot();
  const api = {
    async list() { throw new Error("boom"); },
    async createAlpacaPaper() {},
    async replaceAlpacaPaperCredentials() {},
    async deleteAccount() {}
  };
  const page = mountBrokers(root, api);
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(page.state.loading, false);
  assert.match(page.state.error, /boom/);
});
