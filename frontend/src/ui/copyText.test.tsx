import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "../i18n";
import { copyText } from "./copyText";
import { LinkToCopy } from "./LinkToCopy";
import { Toaster } from "./Toast";

const LINK = "https://alinea.myunio.app/casa-jardim";

function clipboard(writeText: ((text: string) => Promise<void>) | null) {
  vi.stubGlobal("navigator", { ...navigator, clipboard: writeText ? { writeText: vi.fn(writeText) } : undefined });
}

afterEach(() => vi.unstubAllGlobals());

describe("copyText", () => {
  it("copies and says so", async () => {
    clipboard(async () => undefined);
    render(<Toaster />);
    await act(async () => expect(await copyText(LINK)).toBe(true));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(LINK);
    expect(screen.getByRole("status")).toHaveTextContent("Link copiado.");
    expect(screen.getByText("Link copiado.").parentElement).toHaveAttribute("data-kind", "success");
  });

  it("says it couldn't, with the link to copy by hand, when the browser refuses", async () => {
    clipboard(() => Promise.reject(new DOMException("Denied", "NotAllowedError")));
    render(<Toaster />);
    await act(async () => expect(await copyText(LINK)).toBe(false));
    const shown = screen.getByRole("status");
    expect(shown).toHaveTextContent(`Não foi possível copiar. O link é ${LINK}`);
    expect(shown.firstElementChild).toHaveAttribute("data-kind", "error");
    expect(shown).not.toHaveTextContent("NotAllowedError");
  });

  it("says it couldn't when the browser has no clipboard at all (not over HTTPS)", async () => {
    clipboard(null);
    render(<Toaster />);
    await act(async () => expect(await copyText(LINK)).toBe(false));
    expect(screen.getByRole("status").firstElementChild).toHaveAttribute("data-kind", "error");
  });

  it("uses the caller's words where given", async () => {
    clipboard(null);
    render(<Toaster />);
    await act(async () => void (await copyText(LINK, { failed: "Selecione o link." })));
    expect(screen.getByRole("status")).toHaveTextContent("Selecione o link.");
  });
});

describe("LinkToCopy", () => {
  it("never shows a failed copy as done: it points to the link on screen", async () => {
    clipboard(null);
    render(
      <>
        <Toaster />
        <LinkToCopy link={LINK} label="Link de convite" />
      </>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Copiar link" }));
    const shown = screen.getByRole("status");
    expect(shown).toHaveTextContent("Não foi possível copiar. Selecione o link e copie manualmente.");
    expect(shown.firstElementChild).toHaveAttribute("data-kind", "error");
  });

  it("copies its link", async () => {
    clipboard(async () => undefined);
    render(
      <>
        <Toaster />
        <LinkToCopy link={LINK} label="Link de convite" />
      </>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Copiar link" }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(LINK);
    expect(await screen.findByText("Link copiado.")).toBeInTheDocument();
  });
});
