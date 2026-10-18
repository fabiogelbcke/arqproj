import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "../i18n";
import { ApiError } from "../api/client";
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
});
