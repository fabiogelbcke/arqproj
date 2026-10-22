import { describe, expect, it } from "vitest";

import { initial } from "./Avatar";

describe("the avatar's initial", () => {
  it("is the first letter, as a capital, accents kept", () => {
    expect(initial("beatriz Souza")).toBe("B");
    expect(initial("  ícaro")).toBe("Í");
  });

  it("is a ? for a name with no letters at all", () => {
    expect(initial("   ")).toBe("?");
  });
});
