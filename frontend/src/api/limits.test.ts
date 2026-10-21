import { describe, expect, it } from "vitest";

import { LIMITS } from "./limits";

// Every screen's source, as text.
const sources = import.meta.glob<string>(["../**/*.tsx", "!../**/*.test.tsx"], {
  query: "?raw",
  import: "default",
  eager: true,
});

/** maxLength written as a number of its own, instead of read from LIMITS. */
function ownLimits(source: string): string[] {
  return source.match(/maxLength=(\{\s*\d+\s*\}|"\d+")/g) ?? [];
}

describe("field limits", () => {
  it("come from the server, as positive whole numbers", () => {
    expect(Object.keys(LIMITS).length).toBeGreaterThan(0);
    for (const value of Object.values(LIMITS)) expect(Number.isInteger(value) && value > 0).toBe(true);
  });

  it("are never written into a screen: every maxLength reads LIMITS", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(20);
    const found = Object.entries(sources).flatMap(([file, source]) => ownLimits(source).map((m) => `${file}: ${m}`));
    expect(found).toEqual([]);
  });

  it("would notice a screen's own number (the check above can fail)", () => {
    expect(ownLimits('<input maxLength={40} /> <input maxLength="60" />')).toHaveLength(2);
    expect(ownLimits("<input maxLength={LIMITS.meetingTitle} />")).toEqual([]);
  });
});
