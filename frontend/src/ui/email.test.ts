import { describe, expect, it } from "vitest";

import cases from "./email.cases.json";
import { emailSuggestion, isEmail, splitEmails, tidyEmail } from "./email";

// The same cases as the server's rule (backend/tests/test_emails.py).
describe("isEmail", () => {
  it.each(cases.valid)("accepts %s", (email) => expect(isEmail(email)).toBe(true));
  it.each(cases.invalid)("refuses %j", (email) => expect(isEmail(email)).toBe(false));
});

describe("tidyEmail", () => {
  it("trims, lowercases, and takes off what a pasted address brings along", () => {
    expect(tidyEmail("  Ana@Gmail.COM ")).toBe("ana@gmail.com");
    expect(tidyEmail("<ana@gmail.com>")).toBe("ana@gmail.com");
    expect(tidyEmail("mailto:ana@gmail.com")).toBe("ana@gmail.com");
  });
});

describe("emailSuggestion", () => {
  it.each([
    ["ana@gmial.com", "ana@gmail.com"],
    ["ana@gmail.con", "ana@gmail.com"],
    ["ana@gmal.com", "ana@gmail.com"],
    ["ana@hotmal.com", "ana@hotmail.com"],
    ["ana@hotmial.com.br", "ana@hotmail.com.br"],
    ["ana@outlok.com", "ana@outlook.com"],
    ["ana@yaho.com.br", "ana@yahoo.com.br"],
    ["ana@icloud.co", "ana@icloud.com"],
    ["ana@escritorio.con", "ana@escritorio.com"],
    ["ana@escritorio.com.bt", "ana@escritorio.com.br"],
  ])("suggests %s → %s", (typed, meant) => expect(emailSuggestion(typed)).toBe(meant));

  it.each(["ana@gmail.com", "ana@escritorio.com.br", "ana@arq.br", "ana@me.com", "ana@mail.com", "ana", "ana@"])(
    "leaves %s alone",
    (email) => expect(emailSuggestion(email)).toBeNull(),
  );
});

describe("splitEmails", () => {
  it("splits a pasted list on commas, semicolons, spaces and lines", () => {
    expect(splitEmails("Ana@x.com, bia@y.com.br;caio@z.com\n dani@w.com  ")).toEqual([
      "ana@x.com",
      "bia@y.com.br",
      "caio@z.com",
      "dani@w.com",
    ]);
    expect(splitEmails(" , ;")).toEqual([]);
  });
});
