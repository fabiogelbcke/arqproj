import { describe, expect, it } from "vitest";

import cases from "./phone.cases.json";
import { formatPhone, parsePhone } from "./phone";

// The same cases as the server's rule (backend/tests/test_whatsapp.py).
describe("parsePhone", () => {
  it.each(cases.valid)("reads %s as %s", (typed, stored) => expect(parsePhone(typed)).toBe(stored));
  it.each(cases.invalid)("refuses %j", (typed) => expect(parsePhone(typed)).toBeNull());
});

describe("formatPhone", () => {
  it("shows a Brazilian mobile as people write it, another country with its +", () => {
    expect(formatPhone("5511987654321")).toBe("(11) 98765-4321");
    expect(formatPhone("351912345678")).toBe("+351912345678");
  });
});
