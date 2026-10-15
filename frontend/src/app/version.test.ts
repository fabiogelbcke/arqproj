import { describe, expect, it } from "vitest";

import { isNewerBuild, newVersionStore } from "./version";

describe("noticing a new deploy", () => {
  it("compares release builds only", () => {
    expect(isNewerBuild("2026-10-15.1", "2026-10-15.1")).toBe(false);
    expect(isNewerBuild("2026-10-15.1", "2026-10-16.1")).toBe(true);
    expect(isNewerBuild("dev", "2026-10-16.1")).toBe(false); // local build
    expect(isNewerBuild("2026-10-15.1", "dev")).toBe(false); // local server
    expect(isNewerBuild("2026-10-15.1", null)).toBe(false); // no header
  });

  it("offers a reload when a file of this build can no longer be loaded", () => {
    const event = new Event("vite:preloadError", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true); // no crash, no automatic reload
    expect(newVersionStore.snapshot()).toBe(true);
  });
});
