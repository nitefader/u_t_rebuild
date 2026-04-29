import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ExpressionPreview } from "./ExpressionPreview";

describe("<ExpressionPreview />", () => {
  it("formats criterion fallbacks with readable labels and boolean values", () => {
    render(
      <ExpressionPreview
        expression={{
          kind: "criterion",
          criterion: {
            metric: "broker.fractionable",
            operator: "eq",
            value: true,
            value_max: null,
            label: null,
          },
          children: [],
        }}
      />,
    );

    expect(screen.getByText("Fractionable at Alpaca: Yes")).toBeInTheDocument();
    expect(screen.queryByText(/broker\.fractionable eq true/i)).not.toBeInTheDocument();
  });
});
