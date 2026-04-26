import assert from "node:assert/strict";
import test from "node:test";

import { createChartLabApi } from "../src/api/chartLab.js";
import { mountChartLab } from "../src/chartLab.js";

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
    this.sent = [];
    this.closed = false;
  }

  send(data) {
    this.sent.push(data);
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
  return document.createElement("main");
}

function makeDocument() {
  // Minimal DOM stand-in sufficient for chartLab.js
  const elements = [];
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
      classList: {
        contains() {
          return false;
        }
      },
      style: {},
      dataset: {},
      get textContent() {
        return this._text || "";
      },
      set textContent(value) {
        this._text = String(value);
      },
      get innerHTML() {
        return this._html || "";
      },
      set innerHTML(value) {
        this._html = String(value);
        if (value === "") this.children = [];
      },
      appendChild(child) {
        this.children.push(child);
        return child;
      },
      addEventListener(type, fn) {
        this.eventListeners[type] = this.eventListeners[type] || [];
        this.eventListeners[type].push(fn);
      },
      setAttribute(name, value) {
        this.attributes[name] = String(value);
        if (name === "class") this.className = String(value);
      },
      getAttribute(name) {
        return this.attributes[name];
      }
    };
    elements.push(el);
    return el;
  }
  return document;
}

test("createChartLabApi.streamUrl includes the symbol query and ws scheme", () => {
  setupGlobals();
  const api = createChartLabApi({
    fetchImpl: makeFetch({}),
    websocketImpl: FakeWebSocket
  });
  assert.equal(api.streamUrl("SPY"), "ws://127.0.0.1:5173/api/v1/chart-lab/stream?symbol=SPY");
});

test("createChartLabApi.health returns the JSON payload", async () => {
  setupGlobals();
  const api = createChartLabApi({
    fetchImpl: makeFetch({ streaming_enabled: true, default_symbol: "SPY", test_stream: false }),
    websocketImpl: FakeWebSocket
  });
  const health = await api.health();
  assert.deepEqual(health, { streaming_enabled: true, default_symbol: "SPY", test_stream: false });
});

test("mountChartLab connects on form submit and appends bars from stream messages", async () => {
  setupGlobals();
  const root = makeRoot();
  const api = {
    async health() {
      return { streaming_enabled: true, default_symbol: "FAKEPACA", test_stream: true };
    },
    openStream(symbol) {
      return new FakeWebSocket(`ws://test/${symbol}`);
    }
  };

  const chart = mountChartLab(root, api);
  // Wait one microtask for init() to resolve.
  await Promise.resolve();
  await Promise.resolve();

  chart.connect("FAKEPACA");
  const socket = FakeWebSocket.last;
  assert.ok(socket, "socket created");
  socket.emitOpen();
  socket.emitMessage({ type: "ready", symbol: "FAKEPACA", test_stream: true });
  socket.emitMessage({
    type: "bar",
    data: {
      symbol: "FAKEPACA",
      timeframe: "1m",
      timestamp: "2026-04-25T17:00:00Z",
      open: 100,
      high: 101,
      low: 99,
      close: 100.5,
      volume: 1234
    }
  });

  assert.equal(chart.state.status, "connected");
  assert.equal(chart.state.bars.length, 1);
  assert.equal(chart.state.bars[0].close, 100.5);

  chart.disconnect();
  assert.equal(socket.closed, true);
});

test("mountChartLab marks status as error when health check fails", async () => {
  setupGlobals();
  const root = makeRoot();
  const api = {
    async health() {
      throw new Error("boom");
    },
    openStream() {
      return new FakeWebSocket("ws://test");
    }
  };
  const chart = mountChartLab(root, api);
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(chart.state.status, "error");
  assert.match(chart.state.statusMessage, /boom/);
});
