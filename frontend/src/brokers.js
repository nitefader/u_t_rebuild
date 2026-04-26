/**
 * Broker Accounts page — registry, creation, credential rotation.
 *
 * Per the user: "Accounts should have their own page. All account creation
 * moved to the proper page." This module owns the broker-account surface
 * that previously lived inside the Operations Center.
 *
 * Loosely styled after ui_mockup_v2.html's brokers section: account cards
 * with status badges + an inline create form.
 */

const MODE_LABELS = {
  BROKER_PAPER: "Broker Runtime · Paper",
  BROKER_LIVE: "Broker Runtime · Live"
};

const MODE_CLASSES = {
  BROKER_PAPER: "mode-paper",
  BROKER_LIVE: "mode-live"
};

export function mountBrokers(root, api, options = {}) {
  if (!root) return;

  const manualTradeApi = options.manualTradeApi || null;

  const state = {
    accounts: [],
    loading: true,
    error: null,
    formError: null,
    formNotice: null,
    submitting: false,
    showAddForm: false,
    activeReplaceCredentialsFor: null,
    activeReplaceError: null,
    activeReplaceNotice: null,
    activeQuickOrderFor: null,
    // Per-account cross-screen state. The user-journey review found that
    // a single quickOrderError / quickOrderNotice bled across accounts.
    quickOrderErrorByAccount: {},
    quickOrderNoticeByAccount: {},
    quickOrderSubmittingByAccount: {},
    quickOrderIdempotencyKeyByAccount: {},
    ordersByAccount: {},
    cancellingOrderIds: {}
  };

  let openOrdersPollTimer = null;
  const NOTICE_TTL_MS = 6000;
  const POLL_MS = 4000;

  function clearNoticeAfter(accountId) {
    setTimeout(() => {
      if (state.quickOrderNoticeByAccount[accountId] === undefined) return;
      const next = { ...state.quickOrderNoticeByAccount };
      delete next[accountId];
      state.quickOrderNoticeByAccount = next;
      render();
    }, NOTICE_TTL_MS);
  }

  function startOpenOrdersPolling(accountId) {
    stopOpenOrdersPolling();
    if (!manualTradeApi) return;
    openOrdersPollTimer = setInterval(() => {
      if (state.activeQuickOrderFor !== accountId) {
        stopOpenOrdersPolling();
        return;
      }
      refreshOrdersForAccount(accountId);
    }, POLL_MS);
  }

  function stopOpenOrdersPolling() {
    if (openOrdersPollTimer) {
      clearInterval(openOrdersPollTimer);
      openOrdersPollTimer = null;
    }
  }

  function setState(partial) {
    Object.assign(state, partial);
    render();
  }

  async function refresh() {
    try {
      const payload = await api.list();
      setState({ accounts: payload.accounts || [], loading: false, error: null });
    } catch (err) {
      setState({ loading: false, error: err.message || String(err) });
    }
  }

  async function createAccount(form) {
    const data = new FormData(form);
    const provider = String(data.get("provider") || "alpaca").trim().toLowerCase();
    const mode = String(data.get("mode") || "").trim();
    const display_name = String(data.get("display_name") || "").trim();
    const api_key = String(data.get("api_key") || "").trim();
    const api_secret = String(data.get("api_secret") || "").trim();
    if (!display_name || !api_key || !api_secret || !mode) {
      setState({ formError: "Display name, mode, API key, and API secret are required." });
      return;
    }
    if (mode !== "BROKER_PAPER" && mode !== "BROKER_LIVE") {
      setState({ formError: `Mode must be paper or live (got "${mode}").` });
      return;
    }
    if (mode === "BROKER_LIVE") {
      const typed = window.prompt(
        `LIVE account\n\nYou are about to register real-money credentials for "${display_name}" (${provider}).\n\n` +
        `Type the display name to confirm:`
      );
      if (!typed || typed.trim() !== display_name) {
        setState({ formError: typed === null ? "Live registration canceled." : "Display name did not match — registration canceled." });
        return;
      }
    }
    const payload = { provider, mode, display_name, api_key, api_secret };
    try {
      setState({ submitting: true, formError: null, formNotice: null });
      const result = await api.create(payload);
      const verb = result.already_exists ? "Already registered" : "Registered";
      setState({
        submitting: false,
        formNotice: `${verb}: ${result.account.display_name} (${result.account.mode})`,
        showAddForm: false
      });
      await refresh();
    } catch (err) {
      setState({ submitting: false, formError: err.detail || err.message || String(err) });
    }
  }

  async function replaceCredentials(form) {
    const accountId = form.dataset.accountId;
    const data = new FormData(form);
    const payload = {
      api_key: String(data.get("api_key") || "").trim(),
      api_secret: String(data.get("api_secret") || "").trim()
    };
    if (!payload.api_key || !payload.api_secret) {
      setState({ activeReplaceError: "API key and secret are required." });
      return;
    }
    try {
      setState({ submitting: true, activeReplaceError: null, activeReplaceNotice: null });
      await api.replaceCredentials(accountId, payload);
      setState({
        submitting: false,
        activeReplaceNotice: "Credentials replaced. Broker sync will be marked stale until next refresh.",
        activeReplaceCredentialsFor: null
      });
      await refresh();
    } catch (err) {
      setState({ submitting: false, activeReplaceError: err.message || String(err) });
    }
  }

  async function deleteAccount(account) {
    const confirmName = window.prompt(
      `Delete or archive "${account.display_name}"?\n\n` +
      `Type the display name to confirm: ${account.display_name}`
    );
    if (!confirmName) return;
    try {
      const result = await api.deleteAccount(account.id, {
        confirm_display_name: confirmName.trim(),
        confirm_mode: account.mode
      });
      if (result.status === "BLOCKED") {
        alert(`Delete blocked: ${result.message}\n\n${(result.blockers || []).join(", ")}`);
      }
      await refresh();
    } catch (err) {
      alert(`Delete failed: ${err.message || err}`);
    }
  }

  async function pauseAccount(account) {
    try {
      await api.pauseAccount(account.id, "operator_request");
      await refresh();
    } catch (err) {
      alert(`Pause failed: ${err.message || err}`);
    }
  }

  async function resumeAccount(account) {
    try {
      await api.resumeAccount(account.id, "operator_request");
      await refresh();
    } catch (err) {
      alert(`Resume failed: ${err.message || err}`);
    }
  }

  async function refreshOrdersForAccount(accountId) {
    if (!manualTradeApi) return;
    try {
      const payload = await manualTradeApi.list(accountId);
      state.ordersByAccount = { ...state.ordersByAccount, [accountId]: payload.orders || [] };
      render();
    } catch (err) {
      state.ordersByAccount = { ...state.ordersByAccount, [accountId]: [] };
      state.quickOrderErrorByAccount = {
        ...state.quickOrderErrorByAccount,
        [accountId]: err.message || String(err)
      };
      render();
    }
  }

  function setAccountField(map, accountId, value) {
    const next = { ...state[map] };
    if (value === null || value === undefined) {
      delete next[accountId];
    } else {
      next[accountId] = value;
    }
    return next;
  }

  function ensureIdempotencyKey(accountId) {
    if (!state.quickOrderIdempotencyKeyByAccount[accountId] && manualTradeApi) {
      state.quickOrderIdempotencyKeyByAccount = setAccountField(
        "quickOrderIdempotencyKeyByAccount",
        accountId,
        manualTradeApi.makeIdempotencyKey()
      );
    }
  }

  function rotateIdempotencyKey(accountId) {
    state.quickOrderIdempotencyKeyByAccount = setAccountField(
      "quickOrderIdempotencyKeyByAccount",
      accountId,
      manualTradeApi ? manualTradeApi.makeIdempotencyKey() : null
    );
  }

  function describeOrderForConfirm(symbol, side, qty) {
    const verb = side === "long" ? "BUY" : "SELL";
    return `${verb} ${qty} ${symbol}`;
  }

  async function submitQuickOrder(form, account) {
    if (!manualTradeApi) {
      state.quickOrderErrorByAccount = setAccountField(
        "quickOrderErrorByAccount",
        account.id,
        "Manual trade API is not configured."
      );
      render();
      return;
    }
    if (state.quickOrderSubmittingByAccount[account.id]) return; // prevent double-click
    const data = new FormData(form);
    const symbol = String(data.get("symbol") || "").trim().toUpperCase();
    const sideRaw = String(data.get("side") || "").trim().toLowerCase();
    const qtyRaw = String(data.get("qty") || "").trim();
    const intent = String(data.get("intent") || "open").trim();
    const reason = String(data.get("reason") || "").trim();
    const qty = Number(qtyRaw);

    const errors = [];
    if (!symbol) errors.push("Symbol is required.");
    if (sideRaw !== "long" && sideRaw !== "short") errors.push("Side must be Buy or Sell.");
    if (!Number.isFinite(qty) || qty <= 0) errors.push("Quantity must be a positive number.");
    if (!reason || reason.length < 3) errors.push("Reason is required (audit trail).");
    if (errors.length) {
      state.quickOrderErrorByAccount = setAccountField(
        "quickOrderErrorByAccount",
        account.id,
        errors.join(" ")
      );
      render();
      return;
    }

    ensureIdempotencyKey(account.id);
    const payload = {
      symbol,
      side: sideRaw,
      qty,
      order_type: "market",
      time_in_force: "day",
      intent,
      reason,
      idempotency_key: state.quickOrderIdempotencyKeyByAccount[account.id]
    };

    if (account.mode === "BROKER_LIVE") {
      // Mirror the type-confirm flow used for Delete (Journey-review P0):
      // a single click is too easy to dismiss for a real-money order.
      const orderHuman = describeOrderForConfirm(symbol, sideRaw, qty);
      const typed = window.prompt(
        `LIVE account: "${account.display_name}"\n\n` +
        `You are about to place a real-money order:\n  ${orderHuman} @ market\n\n` +
        `Type the account display name to confirm:`
      );
      if (!typed || typed.trim() !== account.display_name) {
        state.quickOrderErrorByAccount = setAccountField(
          "quickOrderErrorByAccount",
          account.id,
          typed === null
            ? "Live order canceled."
            : "Live order canceled — display name did not match."
        );
        render();
        return;
      }
      payload.confirm_live = true;
      payload.confirm_account_display_name = account.display_name;
    }

    state.quickOrderSubmittingByAccount = setAccountField("quickOrderSubmittingByAccount", account.id, true);
    state.quickOrderErrorByAccount = setAccountField("quickOrderErrorByAccount", account.id, null);
    state.quickOrderNoticeByAccount = setAccountField("quickOrderNoticeByAccount", account.id, null);
    render();

    try {
      const result = await manualTradeApi.submit(account.id, payload);
      const noun = result.duplicate ? "Duplicate (existing order returned)" : "Submitted";
      const verb = describeOrderForConfirm(symbol, sideRaw, qty);
      state.quickOrderSubmittingByAccount = setAccountField("quickOrderSubmittingByAccount", account.id, false);
      state.quickOrderNoticeByAccount = setAccountField(
        "quickOrderNoticeByAccount",
        account.id,
        `${noun}: ${verb} (${result.client_order_id}) · ${result.status}`
      );
      // Successful submit consumes the idempotency key — generate a fresh
      // one so the next click is a brand-new order, not a replay.
      rotateIdempotencyKey(account.id);
      clearNoticeAfter(account.id);
      // Also refresh the account snapshot so equity/cash reflect the order.
      refresh();
      await refreshOrdersForAccount(account.id);
    } catch (err) {
      state.quickOrderSubmittingByAccount = setAccountField("quickOrderSubmittingByAccount", account.id, false);
      state.quickOrderErrorByAccount = setAccountField(
        "quickOrderErrorByAccount",
        account.id,
        friendlyError(err, "submit")
      );
      render();
    }
  }

  async function cancelOrder(account, order) {
    if (!manualTradeApi) return;
    const sideRaw = String(order.side || "").toLowerCase();
    const orderHuman = describeOrderForConfirm(order.symbol, sideRaw, order.quantity);
    const confirmed = window.confirm(
      `Cancel ${orderHuman}?\n\n(client_order_id: ${order.client_order_id})`
    );
    if (!confirmed) return;
    try {
      setState({ cancellingOrderIds: { ...state.cancellingOrderIds, [order.order_id]: true } });
      const result = await manualTradeApi.cancel(account.id, order.order_id);
      const remaining = { ...state.cancellingOrderIds };
      delete remaining[order.order_id];
      state.cancellingOrderIds = remaining;
      state.quickOrderNoticeByAccount = setAccountField(
        "quickOrderNoticeByAccount",
        account.id,
        result.no_op
          ? `No change: ${result.message || "order already in terminal state"}`
          : `Canceled: ${orderHuman} (${order.client_order_id})`
      );
      clearNoticeAfter(account.id);
      await refreshOrdersForAccount(account.id);
    } catch (err) {
      const remaining = { ...state.cancellingOrderIds };
      delete remaining[order.order_id];
      state.cancellingOrderIds = remaining;
      state.quickOrderErrorByAccount = setAccountField(
        "quickOrderErrorByAccount",
        account.id,
        friendlyError(err, "cancel")
      );
      // Re-fetch open orders so the operator sees the truth (e.g. FILLED).
      await refreshOrdersForAccount(account.id);
    }
  }

  function friendlyError(err, kind) {
    const code = err && err.code;
    const fields = (err && err.fields) || {};
    if (kind === "cancel" && code === "order_already_filled") {
      const filled = fields.filled_quantity ? ` (filled ${fields.filled_quantity})` : "";
      return `Already filled before cancel reached the broker${filled}. The list has been refreshed.`;
    }
    if (kind === "submit" && code === "broker_sync_stale") {
      return "Broker sync is stale — the system blocked this order to avoid trading on stale truth. Wait a moment and retry.";
    }
    if (code === "idempotency_key_in_flight") {
      return "An identical request is in flight. Wait a moment and check the open-orders list before retrying.";
    }
    if (code === "idempotency_key_conflict") {
      return "This idempotency key was already used for a different order. Review the order and submit again.";
    }
    if (code === "manual_trade_disabled") {
      return "Manual trade is disabled by configuration (UTOS_MANUAL_TRADE_ENABLED=false).";
    }
    if (code === "manual_trade_composition_root_not_initialized") {
      return "Manual trade composition root is not ready for this account. Restart the API or check server logs.";
    }
    if (err && err.recoveryHint) {
      return `${err.message || `Could not ${kind}.`} ${err.recoveryHint}`;
    }
    return (err && (err.message || String(err))) || `Could not ${kind}.`;
  }

  async function flattenAccount(account) {
    const confirmed = window.confirm(
      `Flatten all positions on "${account.display_name}"?\n\n` +
      `This is a destructive operational action. Confirm to proceed.`
    );
    if (!confirmed) return;
    try {
      const result = await api.flattenAccount(account.id, "operator_request");
      if (result && result.accepted === false) {
        alert(`Flatten ${result.status}: ${result.reason}`);
      }
      await refresh();
    } catch (err) {
      alert(`Flatten failed: ${err.message || err}`);
    }
  }

  function render() {
    root.innerHTML = "";

    const wrap = document.createElement("section");
    wrap.className = "brokers-shell";

    const header = document.createElement("header");
    header.className = "brokers-shell__header";
    header.innerHTML = `
      <div>
        <h1>Broker Accounts</h1>
        <p class="brokers-shell__subtitle">Broker identity, credentials, balances. Each Account owns its broker truth and runs its own Trade Update Stream.</p>
      </div>
    `;
    const headerActions = document.createElement("div");
    headerActions.className = "brokers-shell__actions";
    const addButton = document.createElement("button");
    addButton.type = "button";
    addButton.className = "brokers-add-btn";
    addButton.textContent = state.showAddForm ? "Cancel" : "+ Add Account";
    addButton.addEventListener("click", () => setState({ showAddForm: !state.showAddForm, formError: null, formNotice: null }));
    headerActions.appendChild(addButton);
    header.appendChild(headerActions);
    wrap.appendChild(header);

    if (state.formNotice) {
      const notice = document.createElement("p");
      notice.className = "brokers-notice";
      notice.textContent = state.formNotice;
      wrap.appendChild(notice);
    }

    if (state.showAddForm) {
      wrap.appendChild(buildCreateForm());
    }

    if (state.loading) {
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "Loading accounts…";
      wrap.appendChild(p);
      root.appendChild(wrap);
      return;
    }
    if (state.error) {
      const p = document.createElement("p");
      p.className = "warning";
      p.setAttribute("role", "alert");
      p.textContent = `Could not load accounts: ${state.error}`;
      wrap.appendChild(p);
      root.appendChild(wrap);
      return;
    }
    if (state.accounts.length === 0) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "No broker accounts registered. Click \"+ Add Account\" above to register your first one.";
      wrap.appendChild(empty);
      root.appendChild(wrap);
      return;
    }

    const grid = document.createElement("div");
    grid.className = "brokers-grid";
    for (const account of state.accounts) {
      grid.appendChild(buildAccountCard(account));
    }
    wrap.appendChild(grid);
    root.appendChild(wrap);
  }

  function buildCreateForm() {
    const card = document.createElement("section");
    card.className = "broker-card broker-card--form";

    const heading = document.createElement("h3");
    heading.textContent = "New Account";
    card.appendChild(heading);

    const help = document.createElement("p");
    help.className = "broker-card__help";
    help.textContent =
      "Pick the provider and mode (paper or live). The backend derives the right broker endpoint and trade-update stream from your selection — there are no separate paper or live forms.";
    card.appendChild(help);

    const form = document.createElement("form");
    form.className = "broker-form";
    form.dataset.create = "true";
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      createAccount(form);
    });

    form.innerHTML = `
      <label><span>Display name</span><input name="display_name" autocomplete="off" required placeholder="e.g. Algo Trading"></label>
      <label><span>Provider</span>
        <select name="provider" required>
          <option value="alpaca" selected>Alpaca</option>
        </select>
      </label>
      <label><span>Mode</span>
        <select name="mode" required data-broker-mode>
          <option value="" disabled selected>— pick paper or live —</option>
          <option value="BROKER_PAPER">Paper (sandbox)</option>
          <option value="BROKER_LIVE">Live (real money)</option>
        </select>
      </label>
      <label><span>API key</span><input name="api_key" autocomplete="off" required placeholder="PK..."></label>
      <label><span>API secret</span><input name="api_secret" autocomplete="off" required type="password" placeholder="••••••••"></label>
      <p class="broker-card__live-warning warning" data-live-banner role="alert" hidden>
        LIVE mode places real-money orders. You will be asked to type the display name to confirm.
      </p>
    `;

    // Show the live-mode warning the moment the operator picks LIVE.
    const modeSelect = form.querySelector("[data-broker-mode]");
    const liveBanner = form.querySelector("[data-live-banner]");
    if (modeSelect && liveBanner) {
      modeSelect.addEventListener("change", () => {
        if (modeSelect.value === "BROKER_LIVE") {
          liveBanner.removeAttribute("hidden");
        } else {
          liveBanner.setAttribute("hidden", "");
        }
      });
    }

    const actions = document.createElement("div");
    actions.className = "broker-form__actions";
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.disabled = state.submitting;
    submit.textContent = state.submitting ? "Validating…" : "Validate & register";
    actions.appendChild(submit);
    if (state.formError) {
      const err = document.createElement("p");
      err.className = "warning";
      err.setAttribute("role", "alert");
      err.textContent = state.formError;
      actions.appendChild(err);
    }
    form.appendChild(actions);
    card.appendChild(form);
    return card;
  }

  function buildAccountCard(account) {
    const sync = account.broker_sync_freshness;
    const isStale = !!(sync && sync.is_stale);
    const card = document.createElement("article");
    card.className = `broker-card ${isStale ? "broker-card--stale" : ""}`;

    const top = document.createElement("header");
    top.className = "broker-card__top";
    const name = document.createElement("div");
    name.className = "broker-card__name";
    name.innerHTML = `
      <h3>${escapeHtml(account.display_name)}</h3>
      <p class="broker-card__id">${escapeHtml(account.provider)} · ${escapeHtml(account.external_account_id || account.id)}</p>
    `;
    top.appendChild(name);
    const modeBadge = document.createElement("span");
    modeBadge.className = `mode-badge ${MODE_CLASSES[account.mode] || ""}`;
    modeBadge.textContent = MODE_LABELS[account.mode] || account.mode;
    top.appendChild(modeBadge);
    card.appendChild(top);

    if (account.last_account_snapshot) {
      const stats = document.createElement("dl");
      stats.className = "broker-card__stats";
      const snap = account.last_account_snapshot;
      const fields = [
        ["Equity", formatMoney(snap.equity)],
        ["Cash", formatMoney(snap.cash)],
        ["Buying Power", formatMoney(snap.buying_power)],
        ["Day-Trade BP", formatMoney(snap.daytrading_buying_power)],
        ["PDT", snap.pattern_day_trader ? "Yes" : "No"],
        ["Status", snap.account_status || "—"]
      ];
      for (const [label, value] of fields) {
        const row = document.createElement("div");
        row.innerHTML = `<dt>${label}</dt><dd>${escapeHtml(value)}</dd>`;
        stats.appendChild(row);
      }
      card.appendChild(stats);
    }

    const syncRow = document.createElement("p");
    syncRow.className = "broker-card__sync";
    if (sync) {
      const label = isStale
        ? `Sync stale: ${escapeHtml(sync.stale_reason || "freshness check failed")}`
        : `Sync fresh · last sync ${formatRelative(sync.last_sync_at)}`;
      syncRow.innerHTML = label;
      if (isStale) syncRow.classList.add("warning");
    } else {
      syncRow.textContent = "No sync state yet — first refresh pending.";
    }
    card.appendChild(syncRow);

    if (account.needs_credentials) {
      const banner = document.createElement("p");
      banner.className = "warning broker-card__needs-credentials";
      banner.setAttribute("role", "alert");
      banner.innerHTML =
        "Stored credentials missing — trading is blocked until you re-enter API key & secret. Click <strong>Replace credentials</strong> below.";
      card.appendChild(banner);
    }

    const actions = document.createElement("div");
    actions.className = "broker-card__actions";
    const pauseBtn = document.createElement("button");
    pauseBtn.type = "button";
    pauseBtn.textContent = "Pause";
    pauseBtn.addEventListener("click", () => pauseAccount(account));
    actions.appendChild(pauseBtn);
    const resumeBtn = document.createElement("button");
    resumeBtn.type = "button";
    resumeBtn.textContent = "Resume";
    resumeBtn.addEventListener("click", () => resumeAccount(account));
    actions.appendChild(resumeBtn);
    const flattenBtn = document.createElement("button");
    flattenBtn.type = "button";
    flattenBtn.className = "danger";
    flattenBtn.textContent = "Flatten";
    flattenBtn.addEventListener("click", () => flattenAccount(account));
    actions.appendChild(flattenBtn);
    const replaceBtn = document.createElement("button");
    replaceBtn.type = "button";
    replaceBtn.textContent =
      state.activeReplaceCredentialsFor === account.id ? "Cancel" : "Replace credentials";
    replaceBtn.addEventListener("click", () =>
      setState({
        activeReplaceCredentialsFor: state.activeReplaceCredentialsFor === account.id ? null : account.id,
        activeReplaceError: null,
        activeReplaceNotice: null
      })
    );
    actions.appendChild(replaceBtn);
    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "danger";
    deleteBtn.textContent = "Delete or archive";
    deleteBtn.addEventListener("click", () => deleteAccount(account));
    actions.appendChild(deleteBtn);
    card.appendChild(actions);

    if (state.activeReplaceCredentialsFor === account.id) {
      card.appendChild(buildReplaceForm(account));
    }
    if (state.activeReplaceNotice && state.activeReplaceCredentialsFor === null) {
      // Show notice only on the card most recently edited — best-effort: top of grid.
      const note = document.createElement("p");
      note.className = "brokers-notice";
      note.textContent = state.activeReplaceNotice;
      card.appendChild(note);
    }

    if (manualTradeApi) {
      card.appendChild(buildQuickOrderToggle(account));
      if (state.activeQuickOrderFor === account.id) {
        card.appendChild(buildQuickOrderPanel(account));
        card.appendChild(buildOpenOrdersList(account));
      }
    }

    return card;
  }

  function buildQuickOrderToggle(account) {
    const wrapper = document.createElement("div");
    wrapper.className = "broker-card__quick-order-toggle";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "broker-quick-order-btn";
    if (account.needs_credentials) {
      button.disabled = true;
      button.title = "Re-enter credentials before placing orders.";
      button.textContent = "Quick Order (credentials needed)";
      wrapper.appendChild(button);
      return wrapper;
    }
    button.textContent = state.activeQuickOrderFor === account.id ? "Hide Quick Order" : "Quick Order…";
    button.addEventListener("click", () => {
      if (state.activeQuickOrderFor === account.id) {
        stopOpenOrdersPolling();
        setState({ activeQuickOrderFor: null });
      } else {
        // Clear stale inputs from any other account before switching focus.
        state.quickOrderErrorByAccount = setAccountField("quickOrderErrorByAccount", account.id, null);
        state.quickOrderNoticeByAccount = setAccountField("quickOrderNoticeByAccount", account.id, null);
        ensureIdempotencyKey(account.id);
        setState({ activeQuickOrderFor: account.id });
        refreshOrdersForAccount(account.id);
        startOpenOrdersPolling(account.id);
      }
    });
    wrapper.appendChild(button);
    return wrapper;
  }

  function buildQuickOrderPanel(account) {
    const panel = document.createElement("section");
    panel.className = `broker-card__quick-order ${account.mode === "BROKER_LIVE" ? "broker-card__quick-order--live" : ""}`;

    const heading = document.createElement("h4");
    heading.textContent = `Quick Order · ${account.display_name}`;
    panel.appendChild(heading);

    if (account.mode === "BROKER_LIVE") {
      const warn = document.createElement("p");
      warn.className = "warning";
      warn.setAttribute("role", "alert");
      warn.textContent = "LIVE account — every order is real money. You will be asked to confirm before sending.";
      panel.appendChild(warn);
    } else {
      const help = document.createElement("p");
      help.className = "broker-card__help";
      help.textContent =
        "Paper account — orders go to Alpaca paper. Market orders only in this slice; staleness gate enforced server-side.";
      panel.appendChild(help);
    }

    const form = document.createElement("form");
    form.className = "broker-form broker-form--quick-order";
    form.dataset.accountId = account.id;
    const submitting = !!state.quickOrderSubmittingByAccount[account.id];
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const submitButton = form.querySelector("button[type='submit']");
      if (submitButton) submitButton.disabled = true; // synchronous double-click guard
      submitQuickOrder(form, account);
    });
    form.innerHTML = `
      <label class="quick-order-grid">
        <span>Symbol</span><input name="symbol" autocomplete="off" required placeholder="SPY" maxlength="20">
      </label>
      <label class="quick-order-grid">
        <span>Side</span>
        <select name="side" required>
          <option value="long">Buy</option>
          <option value="short">Sell</option>
        </select>
      </label>
      <label class="quick-order-grid">
        <span>Quantity</span>
        <input name="qty" type="number" inputmode="decimal" step="0.01" min="0.01" required placeholder="10">
      </label>
      <label class="quick-order-grid">
        <span>Intent</span>
        <select name="intent">
          <option value="open">Open</option>
          <option value="close">Close</option>
          <option value="reduce">Reduce</option>
        </select>
      </label>
      <label class="quick-order-grid quick-order-grid--wide">
        <span>Reason</span>
        <input name="reason" autocomplete="off" required placeholder="why are you placing this order?" minlength="3" maxlength="200">
      </label>
    `;

    const actions = document.createElement("div");
    actions.className = "broker-form__actions";
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "broker-quick-order-submit";
    submit.disabled = submitting;
    submit.textContent = submitting
      ? "Sending…"
      : account.mode === "BROKER_LIVE"
        ? "Send LIVE order"
        : "Send paper order";
    actions.appendChild(submit);
    const accountError = state.quickOrderErrorByAccount[account.id];
    if (accountError) {
      const err = document.createElement("p");
      err.className = "warning";
      err.setAttribute("role", "alert");
      err.textContent = accountError;
      actions.appendChild(err);
    }
    const accountNotice = state.quickOrderNoticeByAccount[account.id];
    if (accountNotice) {
      const notice = document.createElement("p");
      notice.className = "brokers-notice";
      notice.textContent = accountNotice;
      actions.appendChild(notice);
    }
    form.appendChild(actions);
    panel.appendChild(form);
    return panel;
  }

  function buildOpenOrdersList(account) {
    const wrapper = document.createElement("section");
    wrapper.className = "broker-card__open-orders";

    const heading = document.createElement("h4");
    heading.innerHTML = `Recent orders <button type="button" class="link-btn">Refresh</button>`;
    heading.querySelector("button").addEventListener("click", () => refreshOrdersForAccount(account.id));
    wrapper.appendChild(heading);

    const orders = state.ordersByAccount[account.id];
    if (!orders) {
      const loading = document.createElement("p");
      loading.className = "empty";
      loading.textContent = "Loading orders…";
      wrapper.appendChild(loading);
      return wrapper;
    }
    const open = orders.filter((order) =>
      ["created", "pending_submission", "submitted", "accepted", "partially_filled"].includes(order.status)
    );
    if (!open.length) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "No open orders for this account.";
      wrapper.appendChild(empty);
    } else {
      const list = document.createElement("ul");
      list.className = "broker-open-orders-list";
      for (const order of open) {
        const item = document.createElement("li");
        const summary = document.createElement("div");
        summary.className = "broker-open-orders-list__row";
        const sideLabel = String(order.side || "").toLowerCase() === "long" ? "BUY" : "SELL";
        summary.innerHTML = `
          <code>${escapeHtml(order.client_order_id)}</code>
          <span>${escapeHtml(sideLabel)} ${escapeHtml(String(order.quantity))} ${escapeHtml(order.symbol)}</span>
          <span class="status status-${escapeHtml(order.status)}">${escapeHtml(order.status)}</span>
        `;
        item.appendChild(summary);
        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.className = "danger";
        const cancelling = !!state.cancellingOrderIds[order.order_id];
        cancelBtn.disabled = cancelling;
        cancelBtn.textContent = cancelling ? "Cancelling…" : "Cancel";
        cancelBtn.addEventListener("click", () => cancelOrder(account, order));
        item.appendChild(cancelBtn);
        list.appendChild(item);
      }
      wrapper.appendChild(list);
    }
    return wrapper;
  }

  function buildReplaceForm(account) {
    const form = document.createElement("form");
    form.className = "broker-form broker-form--replace";
    form.dataset.accountId = account.id;
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      replaceCredentials(form);
    });
    form.innerHTML = `
      <label><span>New API key</span><input name="api_key" autocomplete="off" required placeholder="PK..."></label>
      <label><span>New API secret</span><input name="api_secret" autocomplete="off" required type="password" placeholder="••••••••"></label>
    `;
    const actions = document.createElement("div");
    actions.className = "broker-form__actions";
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.disabled = state.submitting;
    submit.textContent = state.submitting ? "Validating…" : "Validate & replace";
    actions.appendChild(submit);
    if (state.activeReplaceError) {
      const err = document.createElement("p");
      err.className = "warning";
      err.setAttribute("role", "alert");
      err.textContent = state.activeReplaceError;
      actions.appendChild(err);
    }
    form.appendChild(actions);
    return form;
  }

  refresh();
  return { state, refresh };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatMoney(value) {
  if (value === null || value === undefined) return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return `$${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatRelative(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const seconds = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return d.toLocaleString();
}
