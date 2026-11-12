import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "../i18n";
import { ApiError } from "../api/client";
import { DialogFrame } from "./DialogFrame";
import { Toaster, toast, toastError } from "./Toast";

describe("toasts", () => {
  it("say that something worked", () => {
    render(<Toaster />);
    act(() => toast("Salvo."));
    expect(screen.getByRole("status")).toHaveTextContent("Salvo.");
    expect(screen.getByText("Salvo.").parentElement).toHaveAttribute("data-kind", "success");
  });

  it("say a failure in the user's language, with its support code", () => {
    render(<Toaster />);
    act(() => toastError(new ApiError("invalid_email", 422, "req42")));
    const shown = screen.getByRole("status");
    expect(shown).toHaveTextContent("Informe um e-mail válido");
    expect(shown).toHaveTextContent("req42");
    expect(shown.firstElementChild).toHaveAttribute("data-kind", "error");
  });

  it("say an unknown failure plainly", () => {
    render(<Toaster />);
    act(() => toastError(new Error("TypeError: x is undefined")));
    expect(screen.getByRole("status")).not.toHaveTextContent("TypeError");
  });

  it("stay readable and usable over an open dialog, whose Desfazer doesn't close it", async () => {
    const onClose = vi.fn();
    const undo = vi.fn();
    render(
      <>
        <Toaster />
        <DialogFrame title="Projeto" onClose={onClose}>
          <p>Conteúdo</p>
        </DialogFrame>
      </>,
    );
    act(() => toast("Arquivado.", undo));
    // A modal hides the rest of the page from screen readers and the pointer; not the toasts.
    expect(screen.getByRole("status")).toHaveTextContent("Arquivado.");
    await userEvent.click(screen.getByRole("button", { name: "Desfazer" }));
    expect(undo).toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });
});
