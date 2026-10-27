import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SiteFooter } from "./UnioMark";

describe("SiteFooter", () => {
  it("keeps Unio's legal pages with Unio's logo, apart from the office's name", () => {
    render(<SiteFooter office="Estúdio Ipê" />);
    const legal = screen.getByRole("navigation", { name: "Informações legais" });
    const brand = document.querySelector("a[href=\"https://myunio.app/\"]")!.parentElement!;
    // Next to the office's name they would read as the office's own policies.
    expect(brand).toContainElement(legal);
    expect(legal).toContainElement(screen.getByRole("link", { name: "Política de Privacidade" }));
    expect(legal).toContainElement(screen.getByRole("link", { name: "Termos de Uso" }));
    const office = screen.getByText("Estúdio Ipê");
    expect(brand).not.toContainElement(office);
    expect(legal).not.toContainElement(office);
  });
});
