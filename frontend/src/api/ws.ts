/**
 * Typed WebSocket hook with reconnect, last-event timestamp, and
 * Zod-decoded payload.
 *
 * Doctrine: closing a tab does NOT drop the broker connection.
 * The backend (`runtime_context.py`) owns the lifetime of broker
 * streams; this hook only owns the per-tab subscription.
 */

import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { wsAbsoluteUrl } from "@/config/env";

export type WSStatus = "idle" | "connecting" | "open" | "closed" | "error";

export interface UseWSResult<T> {
  status: WSStatus;
  lastEventAt: Date | null;
  lastError: string | null;
  lastPayload: T | null;
  send: (data: unknown) => void;
  close: () => void;
}

export interface UseWSOptions<T> {
  schema: z.ZodType<T>;
  path: string;
  enabled?: boolean;
  reconnectMs?: number;
  onMessage?: (payload: T) => void;
}

/**
 * Subscribe to a backend WebSocket. Reconnects with exponential
 * back-off (capped) when the connection drops while `enabled` is
 * true. Surfaces parse errors via `lastError` so the UI can show
 * them — never silently swallowed.
 */
export function useWS<T>(opts: UseWSOptions<T>): UseWSResult<T> {
  const { schema, path, enabled = true, reconnectMs = 2000, onMessage } = opts;
  const [status, setStatus] = useState<WSStatus>("idle");
  const [lastEventAt, setLastEventAt] = useState<Date | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const [lastPayload, setLastPayload] = useState<T | null>(null);

  const sockRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!enabled) {
      sockRef.current?.close(1000, "disabled");
      return;
    }
    let stopped = false;
    let backoff = reconnectMs;

    const connect = () => {
      if (stopped) return;
      setStatus("connecting");
      const url = wsAbsoluteUrl(path);
      const sock = new WebSocket(url);
      sockRef.current = sock;

      sock.addEventListener("open", () => {
        backoff = reconnectMs;
        setStatus("open");
        setLastError(null);
      });

      sock.addEventListener("message", (event) => {
        let raw: unknown;
        try {
          raw = JSON.parse(typeof event.data === "string" ? event.data : "");
        } catch {
          setLastError("invalid_json_frame");
          return;
        }
        const parsed = schema.safeParse(raw);
        if (!parsed.success) {
          setLastError(parsed.error.issues.map((i) => i.message).join("; "));
          return;
        }
        setLastPayload(parsed.data);
        setLastEventAt(new Date());
        onMessageRef.current?.(parsed.data);
      });

      sock.addEventListener("error", () => {
        setStatus("error");
        setLastError("websocket_error");
      });

      sock.addEventListener("close", () => {
        setStatus("closed");
        if (stopped) return;
        reconnectTimerRef.current = setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, 30_000);
      });
    };

    connect();

    return () => {
      stopped = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      sockRef.current?.close(1000, "unmount");
    };
  }, [enabled, path, reconnectMs, schema]);

  function send(data: unknown): void {
    const sock = sockRef.current;
    if (!sock || sock.readyState !== WebSocket.OPEN) return;
    sock.send(typeof data === "string" ? data : JSON.stringify(data));
  }

  function close(): void {
    sockRef.current?.close(1000, "client_close");
  }

  return { status, lastEventAt, lastError, lastPayload, send, close };
}
