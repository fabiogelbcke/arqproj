import { describe, expect, it } from "vitest";

import { splitTitle } from "./titleLead";

describe("a project title's lead", () => {
  it("is the longest type the name starts with", () => {
    expect(splitTitle("Casa de praia Silva")).toEqual({ lead: "Casa de praia", rest: "Silva" });
    expect(splitTitle("Casa Jardim")).toEqual({ lead: "Casa", rest: "Jardim" });
    expect(splitTitle("Apartamento duplex Leblon")).toEqual({ lead: "Apartamento duplex", rest: "Leblon" });
  });

  it("ignores case and accents, and keeps the name as written", () => {
    expect(splitTitle("CASA DE PRAIA Silva")).toEqual({ lead: "CASA DE PRAIA", rest: "Silva" });
    expect(splitTitle("Residencia Oliveira")).toEqual({ lead: "Residencia", rest: "Oliveira" });
    expect(splitTitle("Clínica odontológica Sorriso")).toEqual({ lead: "Clínica odontológica", rest: "Sorriso" });
  });

  it("matches whole words only", () => {
    expect(splitTitle("Casarão Mendes")).toEqual({ lead: "Casarão", rest: "Mendes" }); // its own type
    expect(splitTitle("Casamento Silva")).toEqual({ lead: "Casamento", rest: "Silva" }); // not "Casa"
  });

  it("leads with a kind of work too", () => {
    expect(splitTitle("Reforma Apartamento Lima")).toEqual({ lead: "Reforma", rest: "Apartamento Lima" });
  });

  it("falls back to the first word", () => {
    expect(splitTitle("Projeto Aurora Norte")).toEqual({ lead: "Projeto", rest: "Aurora Norte" });
    expect(splitTitle("  Aurora  ")).toEqual({ lead: "Aurora", rest: "" });
  });

  it("is the whole name when the name is just a type", () => {
    expect(splitTitle("Casa de campo")).toEqual({ lead: "Casa de campo", rest: "" });
  });

  it("works whichever way the accents were typed", () => {
    const decomposed = "Clínica Sorriso".normalize("NFD");
    expect(splitTitle(decomposed)).toEqual({ lead: "Clínica", rest: "Sorriso" });
  });
});
