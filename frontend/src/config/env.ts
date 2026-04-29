/**
 * Build-time and runtime environment helpers.
 *
 * Mirrors the seam used by the legacy frontend (`__UTOS_API_BASE__`,
 * `__UTOS_API_KEY__` globals + `VITE_API_BASE` / `VITE_UTOS_API_KEY`
 * env vars) so a packaged Ultimate Trader bundle can be hosted
 * separately from the backend.
 */

declare global {
  // eslint-disable-next-line no-var
  var __UTOS_API_BASE__: string | undefined;
  // eslint-disable-next-line no-var
  var __UTOS_API_KEY__: string | undefined;
}

function readGlobal(name: "__UTOS_API_BASE__" | "__UTOS_API_KEY__"): string | undefined {
  if (typeof globalThis === "undefined") return undefined;
  const v = (globalThis as unknown as Record<string, unknown>)[name];
  if (v == null) return undefined;
  const s = String(v).trim();
  return s.length > 0 ? s : undefined;
}

function readImportMeta(name: "VITE_API_BASE" | "VITE_UTOS_API_KEY"): string | undefined {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env;
  if (!env) return undefined;
  const v = env[name];
  if (v == null) return undefined;
  const s = String(v).trim();
  return s.length > 0 ? s : undefined;
}

export function getApiBase(): string {
  const fromGlobal = readGlobal("__UTOS_API_BASE__");
  if (fromGlobal) return fromGlobal.replace(/\/+$/, "");
  const fromEnv = readImportMeta("VITE_API_BASE");
  if (fromEnv) return fromEnv.replace(/\/+$/, "");
  return "";
}

export function getApiKey(): string | undefined {
  return readGlobal("__UTOS_API_KEY__") ?? readImportMeta("VITE_UTOS_API_KEY");
}

export function apiAbsoluteUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  const base = getApiBase();
  return base ? `${base}${p}` : p;
}

export function wsAbsoluteUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  const base = getApiBase();
  if (!base) {
    if (typeof globalThis.location === "undefined") return `ws://127.0.0.1${p}`;
    const proto = globalThis.location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${globalThis.location.host}${p}`;
  }
  try {
    const u = new URL(base, "http://127.0.0.1");
    const wsProto = u.protocol === "https:" ? "wss:" : "ws:";
    return `${wsProto}//${u.host}${p}`;
  } catch {
    return p;
  }
}
