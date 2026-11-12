import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Button, DialogTrigger } from "react-aria-components";
import { describe, expect, it, vi } from "vitest";

import "../i18n";
import { DialogFrame } from "./DialogFrame";

function Framed({ busy = false, onClose }: { busy?: boolean; onClose: () => void }) {
  return (
    <>
      <p>A página</p>
      <DialogFrame title="Projeto" busy={busy} onClose={onClose}>
        <p>Conteúdo</p>
      </DialogFrame>
    </>
  );
}

describe("DialogFrame", () => {
  it("closes with ×, Esc and a click outside", async () => {
    const onClose = vi.fn();
    render(<Framed onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));
    await userEvent.keyboard("{Escape}");
    await userEvent.click(document.body);
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("stays open while busy: the × is disabled, and Esc and a click outside do nothing", async () => {
    const onClose = vi.fn();
    render(<Framed busy onClose={onClose} />);
    expect(screen.getByRole("button", { name: "Fechar" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));
    await userEvent.keyboard("{Escape}");
    await userEvent.click(document.body);
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Projeto" })).toBeInTheDocument();
  });

  it("closes again once no longer busy", async () => {
    const onClose = vi.fn();
    const { rerender } = render(<Framed busy onClose={onClose} />);
    rerender(<Framed onClose={onClose} />);
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("keeps a DialogTrigger's dialog open while busy too", async () => {
    function Triggered() {
      const [busy, setBusy] = useState(false);
      return (
        <DialogTrigger>
          <Button>Abrir</Button>
          <DialogFrame title="Trocar" busy={busy}>
            <Button onPress={() => setBusy(true)}>Salvar</Button>
          </DialogFrame>
        </DialogTrigger>
      );
    }
    render(<Triggered />);
    await userEvent.click(screen.getByRole("button", { name: "Abrir" }));
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(screen.getByRole("dialog", { name: "Trocar" })).toBeInTheDocument();
  });
});
