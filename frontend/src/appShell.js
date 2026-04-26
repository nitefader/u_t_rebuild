/**
 * Cross-page shell helpers — system status badge in the nav, consistent
 * empty/loading shells, and a single place to adjust the operator chrome.
 */

export async function mountSystemStatusBadge(navElement, api) {
  if (!navElement) return;
  const placeholder = document.createElement("span");
  placeholder.className = "nav-status nav-status--loading";
  placeholder.textContent = "Checking config…";
  placeholder.title = "Loading backend status";
  navElement.appendChild(placeholder);

  try {
    const status = await api.status();
    placeholder.className = `nav-status ${badgeClass(status)}`;
    placeholder.textContent = badgeLabel(status);
    placeholder.title = badgeTooltip(status);
  } catch (err) {
    placeholder.className = "nav-status nav-status--error";
    placeholder.textContent = "Backend unreachable";
    placeholder.title = err.message || "Backend not responding";
  }
}

function badgeClass(status) {
  if (!status.alpaca_credentials_present) return "nav-status nav-status--warn";
  if (status.alpaca_test_stream) return "nav-status nav-status--test";
  return "nav-status nav-status--ok";
}

function badgeLabel(status) {
  if (!status.alpaca_credentials_present) return "Alpaca not configured";
  if (status.alpaca_test_stream) return `Alpaca · ${status.operator_environment} · TEST stream`;
  const feed = (status.alpaca_data_feed || "iex").toUpperCase();
  return `Alpaca · ${status.operator_environment} · ${feed}`;
}

function badgeTooltip(status) {
  const parts = [
    `Endpoint: ${status.alpaca_endpoint}`,
    `Credentials: ${status.alpaca_credentials_present ? "configured" : "missing — set ALPACA_API_KEY and ALPACA_SECRET_KEY"}`,
    `Market data: ${status.alpaca_test_stream ? "FAKEPACA test stream (24/7)" : `${(status.alpaca_data_feed || "iex").toUpperCase()} feed`}`
  ];
  return parts.join("\n");
}

export function renderLoadingShell(title, message) {
  return `<section class="loading-shell">
    <div class="loading-shell__spinner" aria-hidden="true"></div>
    <div>
      <h1>${escapeHtml(title)}</h1>
      <p>${escapeHtml(message)}</p>
    </div>
  </section>`;
}

export function renderErrorShell(title, message, hint) {
  const hintHtml = hint ? `<p class="loading-shell__hint">${escapeHtml(hint)}</p>` : "";
  return `<section class="loading-shell loading-shell--error" role="alert">
    <div>
      <h1>${escapeHtml(title)}</h1>
      <p>${escapeHtml(message)}</p>
      ${hintHtml}
    </div>
  </section>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
