import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "../i18n";
import { ChangeWarning } from "../admin/Settings";
import { ConfirmDialog } from "./ConfirmDialog";
import { NameDialog } from "./NameDialog";

function confirm(props: { danger?: boolean; busy?: boolean } = {}) {
  const calls = { onConfirm: vi.fn(), onCancel: vi.fn() };
  render(
    <>
      <p>A página</p>
      <ConfirmDialog title="Arquivar projeto?" text="Ele sai do painel." confirm="Arquivar" {...props} {...calls} />
    </>,
  );
  return calls;
}

describe("ConfirmDialog", () => {
  it("starts on the action, and Cancelar, Esc or a click outside leave without it", async () => {
    const { onConfirm, onCancel } = confirm();
    expect(screen.getByRole("button", { name: "Arquivar" })).toHaveFocus();
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await userEvent.keyboard("{Escape}");
    await userEvent.click(document.body);
    expect(onCancel).toHaveBeenCalledTimes(3);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("starts on Cancelar when the action destroys something, so Enter can't do it by accident", async () => {
    const { onConfirm, onCancel } = confirm({ danger: true });
    expect(screen.getByRole("button", { name: "Cancelar" })).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("can't be left while the action runs: Cancelar, Esc and a click outside do nothing", async () => {
    const { onConfirm, onCancel } = confirm({ busy: true });
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
    const action = screen.getByRole("button", { name: /^Arquivar/ });
    expect(within(action).getByRole("progressbar", { name: "Aguarde…" })).toBeInTheDocument(); // it runs
    expect(action).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(action);
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    screen.getByRole("alertdialog").focus();
    await userEvent.keyboard("{Escape}");
    await userEvent.click(document.body);
    expect(onCancel).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe("NameDialog", () => {
  it("can't be left while the name is saved: Cancelar, Esc and a click outside do nothing", async () => {
    const onCancel = vi.fn();
    render(
      <>
        <p>A página</p>
        <NameDialog title="Renomear seção" label="Nome" initial="Plantas" confirm="Salvar" busy onConfirm={vi.fn()} onCancel={onCancel} />
      </>,
    );
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    screen.getByLabelText("Nome").focus();
    await userEvent.keyboard("{Escape}");
    await userEvent.click(document.body);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("is left with Esc when nothing runs", async () => {
    const onCancel = vi.fn();
    render(<NameDialog title="Renomear seção" label="Nome" initial="Plantas" confirm="Salvar" onConfirm={vi.fn()} onCancel={onCancel} />);
    await userEvent.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

describe("ChangeWarning (admin)", () => {
  it("can't be left while the change saves: \"Voltar e revisar\" and Esc do nothing", async () => {
    const onCancel = vi.fn();
    render(<ChangeWarning changes={["3 projetos mudam de etapa"]} busy onConfirm={vi.fn()} onCancel={onCancel} />);
    expect(screen.getByRole("button", { name: "Voltar e revisar" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Voltar e revisar" }));
    screen.getByRole("alertdialog").focus();
    await userEvent.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
  });
});
