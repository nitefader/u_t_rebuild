import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { AccountDetailDrawer } from "./AccountDetailDrawer";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const ACCOUNT_ID = "11111111-2222-3333-4444-555555555555";
const LINEAGE_PROTECTED = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const LINEAGE_NAKED = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
const LINEAGE_PENDING = "cccccccc-cccc-cccc-cccc-cccccccccccc";

const ACCOUNT = {
  id: ACCOUNT_ID,
  account_id: ACCOUNT_ID,
  label: "Paper Account 1",
  provider: "alpaca",
  mode: "paper",
};

const ACCOUNT_OPS = {
  account_id: ACCOUNT_ID,
  broker_account_snapshot: null,
  broker_sync_freshness: null,
  open_broker_orders: [],
  internal_order_ledger_summary: {
    total_count: 0,
    open_count: 0,
    terminal_count: 0,
    by_status: {},
    by_intent: {},
  },
  positions: [
    {
      account_id: ACCOUNT_ID,
      symbol: "SPY",
      qty: 10,
      side: "long",
      avg_entry_price: 100,
      market_value: 1000,
      unrealized_pl: 5,
      position_lineage_id: LINEAGE_PROTECTED,
    },
    {
      account_id: ACCOUNT_ID,
      symbol: "TSLA",
      qty: 5,
      side: "long",
      avg_entry_price: 200,
      market_value: 1000,
      unrealized_pl: -10,
      position_lineage_id: LINEAGE_NAKED,
    },
    {
      account_id: ACCOUNT_ID,
      symbol: "AAPL",
      qty: 7,
      side: "long",
      avg_entry_price: 150,
      market_value: 1050,
      unrealized_pl: 0,
      position_lineage_id: LINEAGE_PENDING,
    },
  ],
  position_views: [
    {
      snapshot: { account_id: ACCOUNT_ID, symbol: "SPY", position_lineage_id: LINEAGE_PROTECTED },
      protection_status: "protected",
      protective_order_count: 2,
    },
    {
      snapshot: { account_id: ACCOUNT_ID, symbol: "TSLA", position_lineage_id: LINEAGE_NAKED },
      protection_status: "naked",
      protective_order_count: 0,
    },
    {
      snapshot: { account_id: ACCOUNT_ID, symbol: "AAPL", position_lineage_id: LINEAGE_PENDING },
      protection_status: "pending_protection",
      protective_order_count: 0,
    },
  ],
  deployments: [],
  is_paused: false,
  is_killed: false,
};

describe("<AccountDetailDrawer /> — protection_status column", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders Protected, NAKED, and Pending tones from position_views", async () => {
    restore = installFetchMock([
      {
        url: `/api/v1/operations/accounts/${ACCOUNT_ID}`,
        body: ACCOUNT_OPS,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-config`,
        body: { detail: "not found" },
        status: 404,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/restrictions`,
        body: { detail: "not found" },
        status: 404,
      },
      {
        url: `/api/v1/broker-accounts/${ACCOUNT_ID}/risk-plan-map`,
        body: { account_id: ACCOUNT_ID, entries: [] },
      },
      {
        url: "/api/v1/risk-plans",
        body: { plans: [] },
      },
    ]);
    renderRoute(
      <AccountDetailDrawer open={true} onOpenChange={() => {}} account={ACCOUNT as never} />,
    );
    await waitFor(() => {
      expect(screen.getByText(/Protected \(2\)/)).toBeInTheDocument();
      expect(screen.getByText("NAKED")).toBeInTheDocument();
      expect(screen.getByText("Stop Pending")).toBeInTheDocument();
    });
  });
});
