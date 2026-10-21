import { describe, expect, it } from "vitest";

import { catalogs } from "../i18n";
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

// Error messages that tell people a field's limit, by the limit they tell.
const TOLD: Record<string, keyof typeof LIMITS> = {
  invalid_project_name: "projectName",
  invalid_client_name: "clientName",
  invalid_office_name: "officeName",
  invalid_staff_name: "staffName",
  invalid_meeting: "meetingTitle",
  invalid_detail: "detailText",
};

/** The numbers a message mentions. */
function numbersIn(message: string): number[] {
  return (message.match(/\d+/g) ?? []).map(Number);
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

  it("are what the error messages tell, in every language", () => {
    for (const [locale, catalog] of Object.entries(catalogs))
      for (const [code, limit] of Object.entries(TOLD)) {
        const message = (catalog.errors as Record<string, string>)[code]!;
        expect(numbersIn(message), `${locale} ${code}`).toContain(LIMITS[limit]);
      }
  });

  it("would notice a message telling an old limit", () => {
    expect(numbersIn("Informe o nome do projeto, com até 120 caracteres.")).not.toContain(LIMITS.projectName);
  });
});
