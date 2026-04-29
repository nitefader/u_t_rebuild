/**
 * Centralised HTTP client.
 *
 * Doctrine: every API call goes through this client so:
 *   - the optional X-UTOS-API-Key header is uniform,
 *   - operator-readable errors are surfaced (no silent failures),
 *   - response Zod schemas validate the payload (catches API drift).
 *
 * The frontend never calls a provider directly. AI, market-data,
 * and broker traffic always flows through `/api/v1/...`.
 */

import { z } from "zod";
import { apiAbsoluteUrl, getApiKey } from "@/config/env";

export class ApiError extends Error {
  status: number;
  detail: string;
  url: string;
  body: unknown;

  constructor(args: { message: string; status: number; detail: string; url: string; body: unknown }) {
    super(args.message);
    this.name = "ApiError";
    this.status = args.status;
    this.detail = args.detail;
    this.url = args.url;
    this.body = args.body;
  }
}

export type RequestInitJson = Omit<RequestInit, "body" | "headers"> & {
  body?: unknown;
  headers?: Record<string, string>;
};

function mergeHeaders(extra?: Record<string, string>): HeadersInit {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(extra ?? {}),
  };
  const apiKey = getApiKey();
  if (apiKey) headers["X-UTOS-API-Key"] = apiKey;
  return headers;
}

async function readBodySafe(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function detailFrom(body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((e) => JSON.stringify(e)).join("; ");
  }
  if (typeof body === "string") return body;
  return "";
}

export async function apiFetch(path: string, init: RequestInitJson = {}): Promise<Response> {
  const url = apiAbsoluteUrl(path);
  const { body, headers: _ignored, ...rest } = init;
  void _ignored;
  const headers = mergeHeaders(init.headers) as Record<string, string>;

  const requestInit: RequestInit = { ...rest, headers };

  if (body !== undefined) {
    if (typeof body === "string" || body instanceof FormData || body instanceof Blob) {
      requestInit.body = body;
    } else {
      requestInit.body = JSON.stringify(body);
      headers["Content-Type"] = "application/json";
    }
  }

  let res: Response;
  try {
    res = await fetch(url, requestInit);
  } catch (cause) {
    throw new ApiError({
      message: `Network error reaching ${path}`,
      status: 0,
      detail: cause instanceof Error ? cause.message : "network_error",
      url,
      body: null,
    });
  }

  if (!res.ok) {
    const body = await readBodySafe(res);
    throw new ApiError({
      message: `${init.method ?? "GET"} ${path} failed (${res.status})`,
      status: res.status,
      detail: detailFrom(body) || res.statusText,
      url,
      body,
    });
  }

  return res;
}

export async function apiJson<T extends z.ZodTypeAny>(
  schema: T,
  path: string,
  init: RequestInitJson = {},
): Promise<z.infer<T>> {
  const res = await apiFetch(path, init);
  const body = await readBodySafe(res);
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError({
      message: `Response from ${path} did not match expected schema`,
      status: res.status,
      detail: parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; "),
      url: apiAbsoluteUrl(path),
      body,
    });
  }
  return parsed.data;
}

export type ApiClient = {
  get<T extends z.ZodTypeAny>(schema: T, path: string): Promise<z.infer<T>>;
  post<T extends z.ZodTypeAny>(schema: T, path: string, body?: unknown): Promise<z.infer<T>>;
  put<T extends z.ZodTypeAny>(schema: T, path: string, body?: unknown): Promise<z.infer<T>>;
  patch<T extends z.ZodTypeAny>(schema: T, path: string, body?: unknown): Promise<z.infer<T>>;
  del<T extends z.ZodTypeAny>(schema: T, path: string, body?: unknown): Promise<z.infer<T>>;
};

export const api: ApiClient = {
  get: (schema, path) => apiJson(schema, path),
  post: (schema, path, body) => apiJson(schema, path, { method: "POST", body }),
  put: (schema, path, body) => apiJson(schema, path, { method: "PUT", body }),
  patch: (schema, path, body) => apiJson(schema, path, { method: "PATCH", body }),
  del: (schema, path, body) => apiJson(schema, path, { method: "DELETE", body }),
};
