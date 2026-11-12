import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "../i18n";
import { Button } from "./Button";
import { PendingContent } from "./PendingContent";
import { ProgressBar } from "./ProgressBar";

describe("Button pending", () => {
  it("shows a spinner while its action runs, keeps its label as its name, and ignores presses", async () => {
    const onPress = vi.fn();
    const { rerender } = render(
      <Button variant="primary" pending={false} onPress={onPress}>
        Salvar
      </Button>,
    );
    expect(screen.queryByRole("progressbar")).toBeNull();
    rerender(
      <Button variant="primary" pending onPress={onPress}>
        Salvar
      </Button>,
    );
    const button = screen.getByRole("button", { name: /^Salvar/ });
    expect(within(button).getByRole("progressbar", { name: "Aguarde…" })).toBeInTheDocument();
    expect(button).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(button);
    expect(onPress).not.toHaveBeenCalled();
  });

  it("doesn't send its form while pending", async () => {
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <input aria-label="Nome" />
        <Button type="submit" pending>
          Salvar
        </Button>
      </form>,
    );
    await userEvent.type(screen.getByLabelText("Nome"), "Casa{Enter}");
    await userEvent.click(screen.getByRole("button", { name: /^Salvar/ }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("keeps focus as its action starts and stops", () => {
    const shown = (pending: boolean) => (
      <form>
        <Button type="submit" pending={pending}>
          Salvar
        </Button>
      </form>
    );
    const { rerender } = render(shown(false));
    screen.getByRole("button", { name: "Salvar" }).focus();
    rerender(shown(true));
    expect(screen.getByRole("button", { name: /^Salvar/ })).toHaveFocus();
    rerender(shown(false));
    expect(screen.getByRole("button", { name: "Salvar" })).toHaveFocus();
  });

  it("leaves a button without `pending` as it was", () => {
    render(<Button>Cancelar</Button>);
    expect(screen.getByRole("button", { name: "Cancelar" }).textContent).toBe("Cancelar");
  });
});

describe("PendingContent", () => {
  it("puts the spinner in a plain button too, its label still there", () => {
    render(
      <button type="button" disabled aria-busy>
        <PendingContent pending>Adicionar</PendingContent>
      </button>,
    );
    const button = screen.getByRole("button", { name: /^Adicionar/ });
    expect(within(button).getByRole("progressbar")).toBeInTheDocument();
  });
});

describe("ProgressBar", () => {
  it("is the bar alone, named for screen readers, without a caption", () => {
    render(<ProgressBar value={0.4} label="Enviando planta.pdf" />);
    const bar = screen.getByRole("progressbar", { name: "Enviando planta.pdf" });
    expect(bar).toHaveAttribute("value", "0.4");
    expect(screen.queryByText("40%")).toBeNull();
  });

  it("shows its caption and the percentage above the bar", () => {
    render(<ProgressBar value={0.25} label="Enviando 3 de 12…" caption="Enviando 3 de 12…" />);
    expect(screen.getByText("Enviando 3 de 12…")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Enviando 3 de 12…" })).toHaveAttribute("value", "0.25");
  });
});
