import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { BrokerAccount } from "@/api/schemas/accounts";
import { installFetchMock, renderRoute } from "@/test/renderRoute";
import { AccountGuardianRow } from "./AccountGuardianRow";

const ACCOUNT_NO_GUARDIAN: BrokerAccount = {
  id: "acct-aaa",
  display_name: "Paper 2",
  provider: "alpaca",
  mode: "BROKER_PAPER",
  external_account_id: "ext-1",
  credentials_ref: "creds:paper2",
  needs_credentials: false,
  validation_status: "valid",
  last_account_snapshot: null,
  broker_sync_freshness: null,
  guardian_deployment_id: null,
  guardian_deployment_name: null,
  created_at: "2026-04-01T10:00:00Z",
  is_archived: false,
  archived_at: null,
};

const ACCOUNT_WITH_GUARDIAN: BrokerAccount = {
  ...ACCOUNT_NO_GUARDIAN,
  id: "acct-bbb",
  display_name: "Paper 3",
  guardian_deployment_id: "dep-c",
  guardian_deployment_name: "Mean Reversion Protector",
};

describe("<AccountGuardianRow />", () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
    vi.clearAllMocks();
  });

  it("renders 'Guardian: None' + 'Select Guardian Deployment' when no Guardian is set", () => {
    restore = installFetchMock([]);
    renderRoute(<AccountGuardianRow account={ACCOUNT_NO_GUARDIAN} />, {
      path: "/accounts",
    });
    expect(screen.getByText("Guardian:")).toBeInTheDocument();
    expect(screen.getByText("None")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Select Guardian Deployment for Paper 2/i }),
    ).toBeInTheDocument();
  });

  it("renders 'Guardian: <Name>' + Change + Remove when Guardian is set", () => {
    restore = installFetchMock([]);
    renderRoute(<AccountGuardianRow account={ACCOUNT_WITH_GUARDIAN} />, {
      path: "/accounts",
    });
    expect(screen.getByText("Mean Reversion Protector")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Change Guardian for Paper 3/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Remove Guardian from Paper 3/i }),
    ).toBeInTheDocument();
  });

  it("clicking Remove fires PUT /guardian with null", async () => {
    restore = installFetchMock([
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_WITH_GUARDIAN.id}/guardian`,
        method: "PUT",
        body: { account: { ...ACCOUNT_WITH_GUARDIAN, guardian_deployment_id: null, guardian_deployment_name: null }, already_exists: false },
      },
    ]);
    renderRoute(<AccountGuardianRow account={ACCOUNT_WITH_GUARDIAN} />, {
      path: "/accounts",
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Remove Guardian from Paper 3/i }),
    );
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls as unknown[][];
      const putCall = calls.find((call) => {
        const url = call[0];
        const method = ((call[1] as { method?: string })?.method ?? "GET").toUpperCase();
        return typeof url === "string" && url.endsWith("/guardian") && method === "PUT";
      });
      expect(putCall).toBeDefined();
      const body = JSON.parse((putCall![1] as { body: string }).body);
      expect(body).toEqual({ guardian_deployment_id: null });
    });
  });
});
