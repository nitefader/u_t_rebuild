import { describe, expect, it } from "vitest";
import { STARTER_STRATEGIES } from "./starterStrategies";

const UUID_V4_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("STARTER_STRATEGIES UUID conformance", () => {
  it("has 10 starters", () => {
    expect(STARTER_STRATEGIES).toHaveLength(10);
  });

  it("every stop.id is a UUID v4", () => {
    for (const starter of STARTER_STRATEGIES) {
      for (const stop of starter.draft.stops) {
        expect(
          UUID_V4_RE.test(stop.id),
          `${starter.name}: stop.id "${stop.id}" is not UUID v4`,
        ).toBe(true);
      }
    }
  });

  it("every leg.id is a UUID v4", () => {
    for (const starter of STARTER_STRATEGIES) {
      for (const leg of starter.draft.legs) {
        expect(
          UUID_V4_RE.test(leg.id),
          `${starter.name}: leg.id "${leg.id}" is not UUID v4`,
        ).toBe(true);
      }
    }
  });

  it("every logical_exit.id is a UUID v4", () => {
    for (const starter of STARTER_STRATEGIES) {
      const exits = [
        ...(starter.draft.logical_exits?.long ?? []),
        ...(starter.draft.logical_exits?.short ?? []),
      ];
      for (const exit of exits) {
        expect(
          UUID_V4_RE.test(exit.id),
          `${starter.name}: logical_exit.id "${exit.id}" is not UUID v4`,
        ).toBe(true);
      }
    }
  });

  it("stop and leg IDs are unique across all starters", () => {
    const seen = new Set<string>();
    for (const starter of STARTER_STRATEGIES) {
      for (const stop of starter.draft.stops) {
        expect(seen.has(stop.id), `Duplicate stop.id "${stop.id}" in ${starter.name}`).toBe(false);
        seen.add(stop.id);
      }
      for (const leg of starter.draft.legs) {
        expect(seen.has(leg.id), `Duplicate leg.id "${leg.id}" in ${starter.name}`).toBe(false);
        seen.add(leg.id);
      }
    }
  });
});
