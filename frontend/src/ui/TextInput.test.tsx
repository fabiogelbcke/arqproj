import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { TextInput } from "./TextInput";

function Field({ max }: { max?: number }) {
  const [value, setValue] = useState("Visita");
  return <TextInput aria-label="Assunto" value={value} maxLength={max} onChange={(e) => setValue(e.target.value)} />;
}

describe("the text input", () => {
  it("counts toward its maximum length as you type, and stops there", async () => {
    render(<Field max={10} />);
    expect(screen.getByText("6/10")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Assunto"), " à obra");
    expect(screen.getByLabelText("Assunto")).toHaveValue("Visita à o"); // the limit stops it
    expect(screen.getByText("10/10")).toBeInTheDocument();
  });

  it("keeps the counter from screen readers, which announce the limit themselves", () => {
    render(<Field max={10} />);
    expect(screen.getByText("6/10")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByLabelText("Assunto")).toHaveAttribute("maxLength", "10");
  });

  it("shows no counter without a maximum length", () => {
    render(<Field />);
    expect(screen.queryByText(/\/\d+$/)).toBeNull();
  });
});
