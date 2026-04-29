import { api } from "./client";
import {
  ResearchEvidenceListSchema,
  ResearchEvidenceSchema,
  type EvidenceTypeValue,
  type ResearchEvidence,
  type ResearchEvidenceList,
} from "./schemas/research";

export const ResearchApi = {
  list: (filters?: {
    strategy_id?: string;
    strategy_version_id?: string;
    evidence_type?: EvidenceTypeValue;
  }): Promise<ResearchEvidenceList> => {
    const params = new URLSearchParams();
    if (filters?.strategy_id) params.set("strategy_id", filters.strategy_id);
    if (filters?.strategy_version_id) params.set("strategy_version_id", filters.strategy_version_id);
    if (filters?.evidence_type) params.set("evidence_type", filters.evidence_type);
    const qs = params.toString();
    const path = `/api/v1/operations/research-evidence${qs ? `?${qs}` : ""}`;
    return api.get(ResearchEvidenceListSchema, path);
  },
  get: (evidenceId: string): Promise<ResearchEvidence> =>
    api.get(ResearchEvidenceSchema, `/api/v1/operations/research-evidence/${evidenceId}`),
};
