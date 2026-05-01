/**
 * Tests for LongShortTabs — tab switch; mirror calls API; mirror disabled when source empty.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { installFetchMock, renderRoute } from "@/test/renderRoute";
import { LongShortTabs } from "./LongShortTabs";

const MIRROR_RESPONSE = { mirrored_text: "5m.rsi(14) < 30" };

describe("<LongShortTabs />", () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders Long and Short tabs", () => {
    renderRoute(
      <LongShortTabs
        activeSide="long"
        longText=""
        shortText=""
        onChange={vi.fn()}
        onMirror={vi.fn()}
      />,
    );
    expect(screen.getByRole("tab", { name: /Long/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Short/i })).toBeInTheDocument();
  });

  it("Mirror button is disabled when source side is empty", () => {
    renderRoute(
      <LongShortTabs
        activeSide="long"
        longText=""
        shortText=""
        onChange={vi.fn()}
        onMirror={vi.fn()}
      />,
    );
    const mirrorBtn = screen.getByRole("button", { name: /mirror to short/i });
    expect(mirrorBtn).toBeDisabled();
  });

  it("Mirror button is enabled when source side has text", () => {
    renderRoute(
      <LongShortTabs
        activeSide="long"
        longText="5m.rsi(14) > 70"
        shortText=""
        onChange={vi.fn()}
        onMirror={vi.fn()}
      />,
    );
    const mirrorBtn = screen.getByRole("button", { name: /mirror to short/i });
    expect(mirrorBtn).not.toBeDisabled();
  });

  it("calls onChange(short) when Short tab is clicked", () => {
    const onChange = vi.fn();
    renderRoute(
      <LongShortTabs
        activeSide="long"
        longText="5m.rsi(14) > 70"
        shortText=""
        onChange={onChange}
        onMirror={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Short/i }));
    expect(onChange).toHaveBeenCalledWith("short", "");
  });

  it("calls onMirror with mirrored text on Mirror click", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/strategies/expression/mirror",
        method: "POST",
        body: MIRROR_RESPONSE,
      },
    ]);
    const onMirror = vi.fn();
    renderRoute(
      <LongShortTabs
        activeSide="long"
        longText="5m.rsi(14) > 70"
        shortText=""
        onChange={vi.fn()}
        onMirror={onMirror}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /mirror to short/i }));

    await waitFor(() => {
      expect(onMirror).toHaveBeenCalledWith(MIRROR_RESPONSE.mirrored_text, "short");
    });
  });
});
