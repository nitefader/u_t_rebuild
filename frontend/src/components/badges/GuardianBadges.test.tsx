import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { BrokerPositionSnapshot } from "@/api/schemas/operations";
import { GuardianBadges } from "./GuardianBadges";

const BASE: BrokerPositionSnapshot = {
  account_id: "acct-1",
  symbol: "SPY",
  qty: 100,
  side: "long",
};

describe("<GuardianBadges />", () => {
  it("renders nothing when no Guardian / lineage state is set", () => {
    const { container } = render(<GuardianBadges snapshot={BASE} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows 'Adopted by …' + 'Orphan adopted' for owner_unknown adoption", () => {
    render(
      <GuardianBadges
        snapshot={{
          ...BASE,
          adoption_status: "adopted_by_guardian",
          adoption_reason: "owner_unknown",
          deployment_name: "Mean Reversion Protector",
        }}
      />,
    );
    expect(screen.getByText(/Adopted by Mean Reversion Protector/)).toBeInTheDocument();
    expect(screen.getByText(/Orphan adopted/)).toBeInTheDocument();
  });

  it("shows 'Adopted by …' + 'Owner Down: <orig>' for owner-down adoption", () => {
    render(
      <GuardianBadges
        snapshot={{
          ...BASE,
          adoption_status: "adopted_by_guardian",
          adoption_reason: "owner_deployment_down_unprotected",
          deployment_name: "Guardian C",
          original_owner_deployment_name: "Deployment A",
        }}
      />,
    );
    expect(screen.getByText(/Adopted by Guardian C/)).toBeInTheDocument();
    expect(screen.getByText(/Owner Down: Deployment A/)).toBeInTheDocument();
  });

  it("shows 'Owner Down (Self-Protected)' when owner unhealthy but stops attached", () => {
    render(
      <GuardianBadges
        snapshot={{
          ...BASE,
          owner_deployment_healthy: false,
          owner_self_protected: true,
          deployment_name: "Deployment A",
        }}
      />,
    );
    expect(screen.getByText(/Owner Down \(Self-Protected\): Deployment A/)).toBeInTheDocument();
  });

  it("shows 'Unmanaged' badge for orphan position with no Guardian set", () => {
    render(<GuardianBadges snapshot={{ ...BASE, unmanaged_broker_position: true }} />);
    expect(screen.getByText(/Unmanaged/)).toBeInTheDocument();
  });

  it("shows Account-level 'Guardian: <Name>' chip when Guardian is set but this position is not adopted", () => {
    render(
      <GuardianBadges
        snapshot={{ ...BASE, deployment_name: "Deployment A" }}
        accountGuardianName="Deployment C"
      />,
    );
    expect(screen.getByText(/Guardian: Deployment C/)).toBeInTheDocument();
  });

  it("does not duplicate the 'Guardian:' chip when this position is the adopted one", () => {
    render(
      <GuardianBadges
        snapshot={{
          ...BASE,
          adoption_status: "adopted_by_guardian",
          adoption_reason: "owner_unknown",
          deployment_name: "Guardian C",
        }}
        accountGuardianName="Guardian C"
      />,
    );
    // "Adopted by Guardian C" surfaces; the redundant "Guardian: Guardian C" chip is suppressed.
    expect(screen.getByText(/Adopted by Guardian C/)).toBeInTheDocument();
    expect(screen.queryByText(/Guardian: Guardian C/)).not.toBeInTheDocument();
  });
});
