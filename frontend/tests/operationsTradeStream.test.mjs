import assert from "node:assert/strict";
import test from "node:test";

import { createOperationsTradeStreamApi } from "../src/api/operationsTradeStream.js";
import { mountOperationsTradeStream } from "../src/operationsTradeStream.js";

class FakeWebSocket extends EventTarget {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  constructor(url) {
    super();
    FakeWebSocket.last = this;
    this.url = url;
    this.readyState = FakeWebSocket.CONNECTING;
    this.closed = false;
  }

  send(data) {
    /* no-op */
  }

  close(code, reason) {
    this.readyState = FakeWebSocket.CLOSED;
    this.closed = true;
    this.dispatchEvent(new CloseEvent("close", { code, reason }));
  }

  emitOpen() {
    this.readyState = FakeWebSocket.OPEN;
    this.dispatchEvent(new Event("open"));
  }

  emitMessage(payload) {
    this.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(payload) }));
  }
}

class CloseEvent extends Event {
  constructor(type, init = {}) {
    super(type);
    this.code = init.code;
    this.reason = init.reason;
  }
}

class MessageEvent extends Event {
  constructor(type, init = {}) {
    super(type);
    this.data = init.data;
  }
}

function makeFetch(payload) {
  return async () => ({
    ok: true,
    status: 200,
    statusText: "OK",
    async json() {
      return payload;
    }
  });
}

function setupGlobals() {
  globalThis.location = { protocol: "http:", host: "127.0.0.1:5173" };
  globalThis.WebSocket = FakeWebSocket;
}

function makeRoot() {
  const document = makeDocument();
  globalThis.document = document;
  return document.createElement("aside");
}

function makeDocument() {
  const document = {
    createElement(tag) {
      return makeElement(tag);
    },
    createElementNS(_ns, tag) {
      return makeElement(tag);
    }
  };
  function makeElement(tag) {
    const el = {
      tagName: tag.toUpperCase(),
      children: [],
      attributes: {},
      eventListeners: {},
      classList: { contains() { return false; } },
      style: {},
      dataset: {},
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

test("createOperationsTradeStreamApi.streamUrl uses ws scheme to the trade-stream path", () => {
  setupGlobals();
  const api = createOperationsTradeStreamApi({ fetchImpl: makeFetch({}), websocketImpl: FakeWebSocket });
  assert.equal(
    api.streamUrl("11111111-2222-3333-4444-555555555555"),
    "ws://127.0.0.1:5173/api/v1/operations/trade-stream?account_id=11111111-2222-3333-4444-555555555555"
  );
});

test("mountOperationsTradeStream collects order_event and fill_event entries", async () => {
  setupGlobals();
  const root = makeRoot();
  const api = {
    async health() { return { streaming_enabled: true, account_provider: "broker_account", account_ids: ["acct-1"] }; },
    openStream(accountId) { return new FakeWebSocket(`ws://test/trade?account_id=${accountId}`); }
  };
  const panel = mountOperationsTradeStream(root, api);
  await Promise.resolve();
  await Promise.resolve();

  panel.connect();
  const socket = FakeWebSocket.last;
  assert.ok(socket, "socket created");
  socket.emitOpen();
  assert.equal(socket.url, "ws://test/trade?account_id=acct-1");
  socket.emitMessage({ type: "ready", account_provider: "broker_account", account_id: "acct-1" });
  socket.emitMessage({
    type: "order_event",
    data: { client_order_id: "utos-1", status: "accepted", filled_quantity: 0, event_at: "2026-04-25T17:30:00+00:00" }
  });
  socket.emitMessage({
    type: "fill_event",
    data: { client_order_id: "utos-1", symbol: "SPY", side: "buy", qty: 5, price: 100.25, event_at: "2026-04-25T17:30:01+00:00" }
  });
  socket.emitMessage({
    type: "order_event",
    data: { client_order_id: "utos-1", status: "canceled", filled_quantity: 0, event_at: "2026-04-25T17:31:00+00:00" }
  });

  assert.equal(panel.state.status, "connected");
  assert.equal(panel.state.events.length, 3);
  assert.equal(panel.state.events[0].type, "order_event");
  assert.equal(panel.state.events[0].data.status, "canceled");
  assert.equal(panel.state.events[1].type, "fill_event");
  assert.equal(panel.state.events[2].type, "order_event");
  assert.equal(panel.state.events[2].data.status, "accepted");

  panel.disconnect();
  assert.equal(socket.closed, true);
});

test("mountOperationsTradeStream marks status as disabled when health says streaming_enabled=false", async () => {
  setupGlobals();
  const root = makeRoot();
  const api = {
    async health() { return { streaming_enabled: false, account_provider: "broker_account", account_ids: [] }; },
    openStream() { return new FakeWebSocket("ws://test/trade"); }
  };
  const panel = mountOperationsTradeStream(root, api);
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(panel.state.status, "disabled");
});
