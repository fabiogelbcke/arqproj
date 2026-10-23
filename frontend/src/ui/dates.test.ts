import { describe, expect, it } from "vitest";

import { relativeDay } from "./dates";

const SP = "America/Sao_Paulo";
const NOW = new Date("2026-10-22T15:00:00Z"); // 12:00 in São Paulo
const at = (value: string) => relativeDay(value, NOW, "pt-BR", SP);

describe("relative days", () => {
  it("says today, yesterday and days ago", () => {
    expect(at("2026-10-22T03:30:00Z")).toBe("hoje"); // 00:30 in São Paulo
    expect(at("2026-10-22T02:30:00Z")).toBe("ontem"); // 23:30 the day before, there
    expect(at("2026-10-19T12:00:00Z")).toBe("há 3 dias");
  });

  it("says weeks from a week, and the date itself past a month", () => {
    expect(at("2026-10-15T12:00:00Z")).toBe("há 1 semana");
    expect(at("2026-09-25T12:00:00Z")).toBe("há 3 semanas");
    expect(at("2026-09-20T12:00:00Z")).toBe("20/09/2026");
  });

  it("calls a moment just ahead of this clock today", () => {
    expect(at("2026-10-22T16:00:00Z")).toBe("hoje");
  });
});
