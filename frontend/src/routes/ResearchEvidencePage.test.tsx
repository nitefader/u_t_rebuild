import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { ResearchEvidencePage } from "./ResearchEvidencePage";
import { EVIDENCE_TYPES } from "@/api/schemas/research";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const STATUS_OK = {
  alpaca_endpoint: "https://paper-api.alpaca.markets",
  alpaca_data_feed: "sip",
  alpaca_credentials_present: true,
  alpaca_test_stream: false,
  operator_environment: "paper",
  operator_environment_source: "explicit",
  operator_environment_conflict: null,
};

describe("<ResearchEvidencePage />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the empty state when no evidence has been recorded", async () => {
    restore = installFetchMock([
      { url: "/api/v1/operations/research-evidence", body: { evidence: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(
      <ResearchEvidencePage
        title="Backtests"
        subtitle="Test"
        evidenceType={EVIDENCE_TYPES.BACKTEST}
        awaitingMessage="awaiting"
        explainSlug="backtests"
      />,
    );
    await waitFor(() => {
      expect(screen.getByText(/No runs yet/i)).toBeInTheDocument();
    });
  });

  it("renders one evidence row on happy path", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/operations/research-evidence",
        body: {
          evidence: [
            {
              evidence_id: "ev-1",
              evidence_type: EVIDENCE_TYPES.BACKTEST,
              strategy_id: "11111111-1111-1111-1111-111111111111",
              strategy_version_id: "22222222-2222-2222-2222-222222222222",
              created_at: new Date().toISOString(),
              succeeded: true,
              summary: { trades: 12 },
              metrics: { sharpe: 1.42 },
            },
          ],
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(
      <ResearchEvidencePage
        title="Backtests"
        subtitle="Test"
        evidenceType={EVIDENCE_TYPES.BACKTEST}
        awaitingMessage="awaiting"
      />,
    );
    await waitFor(() => {
      expect(screen.getByText(/succeeded/i)).toBeInTheDocument();
    });
  });

  it("surfaces a degraded read state when evidence list fails", async () => {
    restore = installFetchMock([
      { url: "/api/v1/operations/research-evidence", body: { detail: "kaboom" }, status: 500 },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(
      <ResearchEvidencePage
        title="Backtests"
        subtitle="Test"
        evidenceType={EVIDENCE_TYPES.BACKTEST}
        awaitingMessage="awaiting"
      />,
    );
    await waitFor(() => {
      expect(screen.getByText(/Could not load evidence/i)).toBeInTheDocument();
    });
  });
});
