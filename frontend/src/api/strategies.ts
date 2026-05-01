/**
 * Typed client for the legacy /api/v1/strategies backend.
 *
 * The legacy strategy backend stays alive through Slice 11 (runtime swap).
 * Research surfaces (Backtests, Walk-Forward, Optimization, Sim Lab) and
 * Deployments use list() and listVersions() for strategy/version pickers
 * and human-readable run labels. New authoring must use the v4 API
 * (frontend/src/api/strategiesV4.ts) and v4 IDE routes instead.
 */

import { z } from "zod";
import { api } from "./client";
import {
  StrategyListResponseSchema,
  StrategyVersionRecordSchema,
  type StrategyListResponse,
  type StrategyVersionRecord,
} from "./schemas/strategies";

const VersionListSchema = z.array(StrategyVersionRecordSchema);

export const StrategiesApi = {
  list: (): Promise<StrategyListResponse> =>
    api.get(StrategyListResponseSchema, "/api/v1/strategies"),

  listVersions: (id: string): Promise<StrategyVersionRecord[]> =>
    api.get(VersionListSchema, `/api/v1/strategies/${id}/versions`),
};
