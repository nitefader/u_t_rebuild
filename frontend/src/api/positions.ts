import { api } from "./client";
import {
  AiExplainPositionResponseSchema,
  PositionExplanationContextSchema,
  type AiExplainPositionResponse,
  type PositionExplanationContext,
} from "./schemas/positions";

export const PositionsApi = {
  explain: (accountId: string, positionLineageId: string): Promise<PositionExplanationContext> =>
    api.get(
      PositionExplanationContextSchema,
      `/api/v1/broker-accounts/${accountId}/positions/${positionLineageId}/explain`,
    ),

  aiExplain: (context: PositionExplanationContext): Promise<AiExplainPositionResponse> =>
    api.post(AiExplainPositionResponseSchema, "/api/v1/ai/explain-position", context),
};
