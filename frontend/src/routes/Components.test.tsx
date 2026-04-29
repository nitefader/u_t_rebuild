import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { Components } from "./Components";
import { renderRoute } from "@/test/renderRoute";

describe("<Components />", () => {
  it("renders the static catalog", () => {
    renderRoute(<Components />);
    expect(screen.getByText(/Components$/)).toBeInTheDocument();
    expect(screen.getByText(/Condition operators/i)).toBeInTheDocument();
    expect(screen.getByText(/SignalPlan intents/i)).toBeInTheDocument();
    expect(screen.getByText(/Account participation decisions/i)).toBeInTheDocument();
  });
});
