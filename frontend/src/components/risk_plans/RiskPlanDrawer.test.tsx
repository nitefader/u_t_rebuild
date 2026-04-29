import { afterEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { RiskPlanDrawer } from "./RiskPlanDrawer";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

/**
 * Frontend acceptance tests per §11.2 (Risk Plan slice):
 *   - Create RiskPlan drawer validates fields.
 *   - AI-generated RiskPlan requires user save/approval.
 */

describe("<RiskPlanDrawer />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("blocks save when name is empty", async () => {
    restore = installFetchMock([]);
    renderRoute(<RiskPlanDrawer mode="create" open={true} onOpenChange={() => undefined} />);
    const save = await screen.findByRole("button", { name: /Save Risk Plan/i });
    expect(save).toBeDisabled();
  });

  it("loads an AI draft into the form but requires the operator to save explicitly", async () => {
    let createCalls = 0;
    const now = new Date().toISOString();
    restore = installFetchMock([
      {
        url: "/api/v1/risk-plans/ai-draft",
        method: "POST",
        body: {
          risk_plan: {
            risk_plan_id: "plan-ai",
            name: "AI Suggested",
            description: "Drafted from prompt",
            status: "draft",
            risk_score: 4,
            risk_tier: "balanced",
            version: 1,
            created_at: now,
            updated_at: now,
            ai_generated: true,
            ai_summary: "Balanced day trading plan with 1% risk per trade.",
            source: "ai_generated",
          },
          risk_plan_version: {
            risk_plan_version_id: "ver-ai",
            risk_plan_id: "plan-ai",
            version: 1,
            status: "draft",
            config_fingerprint: "ai-fingerprint",
            config: {
              sizing_method: "risk_percent",
              risk_per_trade_pct: 1.0,
              max_open_positions: 5,
              max_daily_loss_pct: 3.0,
              max_drawdown_pct: 10.0,
              stop_required: true,
            },
            created_at: now,
          },
          warnings: [],
          ai_provider_id: "prov-1",
          ai_provider_name: "GROQ",
          boundary_guardrails: [],
        },
      },
      {
        url: "/api/v1/risk-plans",
        method: "POST",
        body: {
          risk_plan: {
            risk_plan_id: "plan-new",
            name: "AI Suggested",
            description: "Drafted from prompt",
            status: "draft",
            risk_score: 4,
            risk_tier: "balanced",
            version: 1,
            created_at: now,
            updated_at: now,
            ai_generated: true,
            ai_summary: "Balanced day trading plan with 1% risk per trade.",
            source: "ai_generated",
          },
          versions: [],
        },
      },
    ]);

    // Track POSTs
    const origFetch = globalThis.fetch;
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : (input as Request).url;
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.includes("/api/v1/risk-plans") && !url.includes("ai-draft") && method === "POST") {
        createCalls += 1;
      }
      return origFetch(input as Parameters<typeof fetch>[0], init);
    }) as typeof fetch;

    renderRoute(<RiskPlanDrawer mode="create" open={true} onOpenChange={() => undefined} />);

    const promptInput = (await screen.findByLabelText(/Prompt/)) as HTMLInputElement;
    fireEvent.change(promptInput, { target: { value: "balanced day-trading plan, 1% risk" } });

    fireEvent.click(screen.getByRole("button", { name: /Generate draft/i }));
    await waitFor(() => {
      expect((screen.getByLabelText(/Name \*/) as HTMLInputElement).value).toBe("AI Suggested");
    });

    // The AI summary is rendered.
    expect(screen.getByText(/Balanced day trading plan/i)).toBeInTheDocument();

    // Doctrine: AI must NOT have created a Risk Plan automatically.
    expect(createCalls).toBe(0);

    // Operator clicks save explicitly.
    fireEvent.click(screen.getByRole("button", { name: /Save Risk Plan/i }));
    await waitFor(() => {
      expect(createCalls).toBe(1);
    });

    globalThis.fetch = origFetch;
  });
});
