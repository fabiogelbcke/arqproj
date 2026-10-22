import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { describe, expect, it } from "vitest";

import { PopoverDetails } from "./PopoverDetails";
import { useDismiss } from "./useDismiss";

/** A menu drawn by hand. "whole": button and list in the one element given (a
 *  file's "⋯" menu); "split": the two given apart (the file preview's "Enviar");
 *  "buttonOnly": only the button given, the list left out (for the self-test). */
function Menu({ mode = "whole" }: { mode?: "whole" | "split" | "buttonOnly" }) {
  const [open, setOpen] = useState(false);
  const whole = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  useDismiss(mode === "split" ? [button, list] : mode === "whole" ? whole : button, open, () => setOpen(false));
  const items = open && (
    <ul ref={list} aria-label="Itens">
      <li>
        <button type="button">Item</button>
      </li>
    </ul>
  );
  return (
    <>
      <div ref={whole}>
        <button ref={button} type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
          Menu
        </button>
        {mode === "whole" && items}
      </div>
      <p>Between</p>
      {mode !== "whole" && items}
    </>
  );
}

describe("useDismiss", () => {
  it("closes on a click outside, not on one inside, and its button still toggles it", async () => {
    render(<Menu mode="split" />);
    const button = screen.getByRole("button", { name: "Menu" });
    await userEvent.click(button);
    await userEvent.click(screen.getByText("Item"));
    expect(screen.getByRole("list", { name: "Itens" })).toBeInTheDocument();
    await userEvent.click(button); // its own button closes it, rather than closing and reopening
    expect(screen.queryByRole("list")).toBeNull();
    await userEvent.click(button);
    await userEvent.click(screen.getByText("Between"));
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("closes with Esc", async () => {
    render(<Menu />);
    await userEvent.click(screen.getByRole("button", { name: "Menu" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("gives the focus back to its button when Esc closes it from inside", async () => {
    for (const mode of ["whole", "split"] as const) {
      const { unmount } = render(<Menu mode={mode} />);
      await userEvent.click(screen.getByRole("button", { name: "Menu" }));
      screen.getByRole("button", { name: "Item" }).focus();
      await userEvent.keyboard("{Escape}");
      expect(screen.queryByRole("list")).toBeNull();
      expect(screen.getByRole("button", { name: "Menu" })).toHaveFocus();
      unmount();
    }
  });

  it("counts a click outside the element it was given as outside", async () => {
    // Self-test: the list sits outside the one element given, so a click on it closes the menu.
    render(<Menu mode="buttonOnly" />);
    await userEvent.click(screen.getByRole("button", { name: "Menu" }));
    await userEvent.click(screen.getByText("Item"));
    expect(screen.queryByRole("list")).toBeNull();
  });
});

describe("PopoverDetails", () => {
  it("closes on a click outside it or Esc, and stays open for a click inside", async () => {
    render(
      <>
        <PopoverDetails>
          <summary>Adicionar à agenda</summary>
          <a href="#google">Google Agenda</a>
        </PopoverDetails>
        <p>Elsewhere</p>
      </>,
    );
    const details = screen.getByText("Adicionar à agenda").closest("details")!;
    await userEvent.click(screen.getByText("Adicionar à agenda"));
    expect(details.open).toBe(true);
    await userEvent.click(screen.getByText("Google Agenda"));
    expect(details.open).toBe(true);
    await userEvent.click(screen.getByText("Elsewhere"));
    expect(details.open).toBe(false);
    await userEvent.click(screen.getByText("Adicionar à agenda"));
    expect(details.open).toBe(true);
    await userEvent.keyboard("{Escape}");
    expect(details.open).toBe(false);
    // From inside, Esc gives the focus back to its summary.
    await userEvent.click(screen.getByText("Adicionar à agenda"));
    screen.getByText("Google Agenda").focus();
    await userEvent.keyboard("{Escape}");
    expect(details.open).toBe(false);
    expect(screen.getByText("Adicionar à agenda")).toHaveFocus();
  });
});
