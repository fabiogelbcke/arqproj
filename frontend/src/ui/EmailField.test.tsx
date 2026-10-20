import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Form } from "react-aria-components";
import { describe, expect, it, vi } from "vitest";

import { EmailField } from "./EmailField";
import { EmailListField } from "./EmailListField";

describe("the email field", () => {
  it("tidies the address when it's left, and says nothing of a good one", async () => {
    render(<EmailField label="E-mail" />);
    await userEvent.type(screen.getByLabelText("E-mail"), "  Ana@Escritorio.com.BR ");
    await userEvent.tab();
    expect(screen.getByLabelText("E-mail")).toHaveValue("ana@escritorio.com.br");
    expect(screen.queryByText(/Confira o e-mail/)).toBeNull();
  });

  it("says when it isn't an address once it's left, not while it's typed", async () => {
    render(<EmailField label="E-mail" />);
    const field = screen.getByLabelText("E-mail");
    await userEvent.type(field, "ana@gmail");
    expect(screen.queryByText(/Confira o e-mail/)).toBeNull();
    await userEvent.tab();
    expect(screen.getByText(/Confira o e-mail/)).toBeInTheDocument();
    // Fixed: the message goes as soon as it's an address.
    await userEvent.type(field, ".com");
    expect(screen.queryByText(/Confira o e-mail/)).toBeNull();
  });

  it("offers the likely address for a typo in the domain, and takes it on a click", async () => {
    render(<EmailField label="E-mail" />);
    await userEvent.type(screen.getByLabelText("E-mail"), "ana@gmial.com");
    await userEvent.tab();
    await userEvent.click(screen.getByRole("button", { name: "ana@gmail.com" }));
    expect(screen.getByLabelText("E-mail")).toHaveValue("ana@gmail.com");
    expect(screen.queryByText(/Você quis dizer/)).toBeNull();
  });

  it("keeps a form from being sent with an address that isn't one", async () => {
    const sent = vi.fn();
    render(
      <Form onSubmit={(event) => (event.preventDefault(), sent())}>
        <EmailField label="E-mail" name="email" />
        <button type="submit">Enviar</button>
      </Form>,
    );
    await userEvent.type(screen.getByLabelText("E-mail"), "ana@");
    await userEvent.click(screen.getByRole("button", { name: "Enviar" }));
    expect(sent).not.toHaveBeenCalled();
    expect(screen.getByText(/Confira o e-mail/)).toBeInTheDocument();
  });

  it("keeps it from being sent with Enter too, before the field is left", async () => {
    const sent = vi.fn();
    render(
      <Form onSubmit={(event) => (event.preventDefault(), sent())}>
        <EmailField label="E-mail" name="email" />
        <button type="submit">Enviar</button>
      </Form>,
    );
    await userEvent.type(screen.getByLabelText("E-mail"), "ana@gmail{Enter}");
    expect(sent).not.toHaveBeenCalled();
    expect(await screen.findByText(/Confira o e-mail/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("E-mail"), ".com{Enter}");
    expect(sent).toHaveBeenCalledOnce();
  });
});

function List({ start = [] as string[], locked = [] as string[] }) {
  const [emails, setEmails] = useState(start);
  const [draft, setDraft] = useState("");
  return (
    <>
      <EmailListField
        label="E-mails do cliente"
        emails={emails}
        onChange={setEmails}
        draft={draft}
        onDraft={setDraft}
        max={3}
        locked={(email) => (locked.includes(email) ? "Cancelou os e-mails" : null)}
        addLabel="Adicionar"
        newLabel="Novo e-mail"
        removeLabel={(email) => `Remover ${email}`}
      />
      <output data-testid="list">{emails.join(" ")}</output>
    </>
  );
}
const listed = () => screen.getByTestId("list").textContent;

describe("the email list", () => {
  it("adds several pasted at once, each once, and keeps the ones that aren't addresses to fix", async () => {
    render(<List start={["bia@x.com.br"]} />);
    await userEvent.click(screen.getByLabelText("Novo e-mail"));
    await userEvent.paste("Ana@Gmail.com, bia@x.com.br; caio@\nana@gmail.com");
    expect(listed()).toBe("bia@x.com.br ana@gmail.com");
    expect(screen.getByLabelText("Novo e-mail")).toHaveValue("caio@");
    expect(screen.getByRole("alert")).toHaveTextContent("Este não parece um e-mail: caio@");
  });

  it("adds what's typed on Enter or a comma, up to the maximum", async () => {
    render(<List />);
    const field = screen.getByLabelText("Novo e-mail");
    await userEvent.type(field, "ana@x.com{Enter}bia@x.com,caio@x.com{Enter}");
    expect(listed()).toBe("ana@x.com bia@x.com caio@x.com");
    expect(screen.queryByLabelText("Novo e-mail")).toBeNull(); // full
  });

  it("offers the fix for a typo, on an added address and on one being typed", async () => {
    render(<List start={["ana@hotmal.com"]} />);
    await userEvent.click(screen.getByRole("button", { name: "ana@hotmail.com" }));
    expect(listed()).toBe("ana@hotmail.com");
    await userEvent.type(screen.getByLabelText("Novo e-mail"), "bia@gmail.con");
    await userEvent.click(screen.getByRole("button", { name: "bia@gmail.com" }));
    expect(screen.getByLabelText("Novo e-mail")).toHaveValue("bia@gmail.com");
  });

  it("keeps the addresses past the maximum in the box, and says why", async () => {
    render(<List start={["ana@x.com", "bia@x.com"]} />);
    await userEvent.click(screen.getByLabelText("Novo e-mail"));
    await userEvent.paste("caio@x.com, dani@x.com, edu@x.com");
    expect(listed()).toBe("ana@x.com bia@x.com caio@x.com"); // 3 at most here
    expect(screen.getByLabelText("Novo e-mail")).toHaveValue("dani@x.com, edu@x.com");
    expect(screen.getByRole("alert")).toHaveTextContent("Já são 3 e-mails, o máximo.");
  });

  it("removes an address, except one the client unsubscribed", async () => {
    render(<List start={["ana@x.com", "bia@x.com"]} locked={["bia@x.com"]} />);
    expect(screen.queryByRole("button", { name: "Remover bia@x.com" })).toBeNull();
    expect(screen.getByText("Cancelou os e-mails")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remover ana@x.com" }));
    expect(listed()).toBe("bia@x.com");
  });
});
