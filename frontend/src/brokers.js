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

export function mountBrokers(root, api) {
  if (!root) return;

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
    activeReplaceNotice: null
  };

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
    const payload = {
      display_name: String(data.get("display_name") || "").trim(),
      api_key: String(data.get("api_key") || "").trim(),
      api_secret: String(data.get("api_secret") || "").trim()
    };
    if (!payload.display_name || !payload.api_key || !payload.api_secret) {
      setState({ formError: "Display name, API key, and API secret are required." });
      return;
    }
    try {
      setState({ submitting: true, formError: null, formNotice: null });
      const result = await api.createAlpacaPaper(payload);
      const verb = result.already_exists ? "Already registered" : "Registered";
      setState({
        submitting: false,
        formNotice: `${verb}: ${result.account.display_name}`,
        showAddForm: false
      });
      await refresh();
    } catch (err) {
      setState({ submitting: false, formError: err.message || String(err) });
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
      await api.replaceAlpacaPaperCredentials(accountId, payload);
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
    addButton.textContent = state.showAddForm ? "Cancel" : "+ Add Alpaca paper account";
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
      empty.textContent = "No broker accounts registered. Click \"+ Add Alpaca paper account\" above to create one.";
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
    heading.textContent = "New Alpaca paper account";
    card.appendChild(heading);

    const help = document.createElement("p");
    help.className = "broker-card__help";
    help.textContent =
      "Validates the credentials against Alpaca's paper endpoint and registers a new BrokerAccount. The system starts a Trade Update Stream for this account immediately — no restart required.";
    card.appendChild(help);

    const form = document.createElement("form");
    form.className = "broker-form";
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      createAccount(form);
    });

    form.innerHTML = `
      <label><span>Display name</span><input name="display_name" autocomplete="off" required placeholder="e.g. Algo Trading - Paper"></label>
      <label><span>API key</span><input name="api_key" autocomplete="off" required placeholder="PK..."></label>
      <label><span>API secret</span><input name="api_secret" autocomplete="off" required type="password" placeholder="••••••••"></label>
    `;
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

    const actions = document.createElement("div");
    actions.className = "broker-card__actions";
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

    return card;
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
