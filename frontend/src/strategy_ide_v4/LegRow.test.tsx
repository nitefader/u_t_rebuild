import { describe, expect, it, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { render } from "@testing-library/react";
import { LegRow } from "./LegRow";
import type { StrategyLegV4Draft } from "@/api/schemas/strategiesV4";

function makeLeg(overrides: Partial<StrategyLegV4Draft> = {}): StrategyLegV4Draft {
  return {
    id: "leg-1",
    position: 1,
    kind: "target",
    size_pct: 0.5,
    target_type: "%",
    target_value: 2.0,
    on_fill_action: { kind: "be_exact" },
    ...overrides,
  };
}

describe("<LegRow />", () => {
  it("renders kind, size, target type fields", () => {
    render(
      <LegRow leg={makeLeg()} index={0} totalLegs={2} onChange={vi.fn()} onRemove={vi.fn()} />,
    );
    expect(screen.getByRole("combobox", { name: /leg 1 kind/i })).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: /leg 1 size percent/i })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /leg 1 target type/i })).toBeInTheDocument();
  });

  it("size_pct stored as decimal; displayed as percentage", () => {
    render(
      <LegRow leg={makeLeg({ size_pct: 0.25 })} index={0} totalLegs={2} onChange={vi.fn()} onRemove={vi.fn()} />,
    );
    const input = screen.getByRole("spinbutton", { name: /leg 1 size percent/i }) as HTMLInputElement;
    expect(parseFloat(input.value)).toBeCloseTo(25, 2);
  });

  it("changing size input fires onChange with size_pct as decimal", () => {
    const onChange = vi.fn();
    render(
      <LegRow leg={makeLeg({ size_pct: 0.5 })} index={0} totalLegs={2} onChange={onChange} onRemove={vi.fn()} />,
    );
    fireEvent.change(screen.getByRole("spinbutton", { name: /leg 1 size percent/i }), {
      target: { value: "75" },
    });
    const updated = onChange.mock.calls[0][0] as StrategyLegV4Draft;
    expect(updated.size_pct).toBeCloseTo(0.75, 4);
  });

  it("feature target_type hides target_value input", () => {
    render(
      <LegRow
        leg={makeLeg({ target_type: "feature", target_value: null })}
        index={0}
        totalLegs={1}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.queryByRole("spinbutton", { name: /leg 1 target value/i })).not.toBeInTheDocument();
    expect(screen.getByText(/feature target.*runtime/i)).toBeInTheDocument();
  });

  it("non-feature target_type shows target_value input", () => {
    render(
      <LegRow leg={makeLeg({ target_type: "%", target_value: 2.0 })} index={0} totalLegs={1} onChange={vi.fn()} onRemove={vi.fn()} />,
    );
    expect(screen.getByRole("spinbutton", { name: /leg 1 target value/i })).toBeInTheDocument();
  });

  it("switching to feature target_type calls onChange with target_value=null", () => {
    const onChange = vi.fn();
    render(
      <LegRow leg={makeLeg({ target_type: "%", target_value: 2.0 })} index={0} totalLegs={1} onChange={onChange} onRemove={vi.fn()} />,
    );
    fireEvent.change(screen.getByRole("combobox", { name: /leg 1 target type/i }), {
      target: { value: "feature" },
    });
    const updated = onChange.mock.calls[0][0] as StrategyLegV4Draft;
    expect(updated.target_value).toBeNull();
  });

  it("on_fill_action propagates from OnFillActionSubform", () => {
    const onChange = vi.fn();
    render(
      <LegRow leg={makeLeg({ on_fill_action: { kind: "be_exact" } })} index={0} totalLegs={1} onChange={onChange} onRemove={vi.fn()} />,
    );
    // Switch on_fill_action kind to be_plus
    fireEvent.change(screen.getByRole("combobox", { name: /on fill action kind/i }), {
      target: { value: "be_plus" },
    });
    const updated = onChange.mock.calls[0][0] as StrategyLegV4Draft;
    expect(updated.on_fill_action.kind).toBe("be_plus");
  });

  it("remove button is disabled when totalLegs=1", () => {
    render(
      <LegRow leg={makeLeg()} index={0} totalLegs={1} onChange={vi.fn()} onRemove={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /remove leg 1/i })).toBeDisabled();
  });

  it("remove button is enabled when totalLegs>1", () => {
    render(
      <LegRow leg={makeLeg()} index={0} totalLegs={2} onChange={vi.fn()} onRemove={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /remove leg 1/i })).not.toBeDisabled();
  });

  it("clicking Remove fires onRemove", () => {
    const onRemove = vi.fn();
    render(
      <LegRow leg={makeLeg()} index={0} totalLegs={2} onChange={vi.fn()} onRemove={onRemove} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /remove leg 1/i }));
    expect(onRemove).toHaveBeenCalledOnce();
  });
});
