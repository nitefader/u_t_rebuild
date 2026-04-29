import { z } from "zod";
import { api } from "./client";
import {
  WatchlistListResponseSchema,
  WatchlistResponseSchema,
  WatchlistSnapshotSchema,
  type WatchlistListResponse,
  type WatchlistResponse,
  type WatchlistSnapshot,
  type WatchlistWriteRequest,
} from "./schemas/watchlists";

export const WatchlistsApi = {
  list: (): Promise<WatchlistListResponse> =>
    api.get(WatchlistListResponseSchema, "/api/v1/watchlists"),

  create: (req: WatchlistWriteRequest): Promise<WatchlistResponse> =>
    api.post(WatchlistResponseSchema, "/api/v1/watchlists", req),

  get: (id: string): Promise<WatchlistResponse> =>
    api.get(WatchlistResponseSchema, `/api/v1/watchlists/${id}`),

  update: (id: string, req: WatchlistWriteRequest): Promise<WatchlistResponse> =>
    api.patch(WatchlistResponseSchema, `/api/v1/watchlists/${id}`, req),

  delete: (id: string) => api.post(z.unknown(), `/api/v1/watchlists/${id}/delete`),

  archive: (id: string): Promise<WatchlistResponse> =>
    api.post(WatchlistResponseSchema, `/api/v1/watchlists/${id}/archive`),

  takeSnapshot: (id: string, note?: string | null): Promise<WatchlistSnapshot> =>
    api.post(WatchlistSnapshotSchema, `/api/v1/watchlists/${id}/snapshot`, {
      note: note ?? null,
    }),

  refresh: (id: string, note?: string | null): Promise<WatchlistSnapshot> =>
    api.post(WatchlistSnapshotSchema, `/api/v1/watchlists/${id}/refresh`, {
      note: note ?? null,
    }),
};
