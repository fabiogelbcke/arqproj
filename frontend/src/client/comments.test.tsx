// Comments on stages and files (A49): a client signs with a name remembered on the
// device, staff as the office and may remove any; switched off, nothing shows.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18next from "i18next";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fakeApi, TENANT } from "../test/render";
import { ClientApp } from "./ClientApp";
import type { Page } from "./format";
import { entriesFor } from "./Updates";

vi.mock("./Tour", () => ({ startTour: vi.fn() }));

const PAGE: Page = {
  id: "6f1c1d1e-0000-4000-8000-0000000000c1",
  office: { name: "Alinea", logo_url: null, logo_dark_url: null },
  team: [],
  locale: "pt-BR",
  timezone: "America/Sao_Paulo",
  name: "Casa Jardim",
  client_name: "Família Oliveira",
  project_type: "Reforma",
  project_type_key: "renovation",
  description: "",
  cover_url: null,
  features: ["comments"],
  completed: false,
  current_position: null,
  last_update: "2026-11-01T12:00:00Z",
  details: [],
  stages: [
    { position: 1, title: "Briefing", about: null, notes: "", completed: false },
    { position: 2, title: "Obra", about: null, notes: "", completed: false },
  ],
  next_meeting: null,
  in_proposal: false,
  proposal: null,
  proposal_url: null,
};

const said = (id: string, name: string, body: string, author: "client" | "staff" = "client") => ({
  id,
  author,
  name,
  body,
  created_at: "2026-11-02T15:00:00Z",
  removable: false,
});

/** As an owner signed in gets them: every comment removable. */
const asOwner = () => ({
  stages: FILES_BASE().stages.map((stage) => ({
    ...stage,
    comments: stage.comments.map((c) => ({ ...c, removable: true })),
    groups: stage.groups.map((g) => ({ ...g, files: g.files.map((f) => ({ ...f, comments: f.comments.map((c) => ({ ...c, removable: true })) })) })),
  })),
});

const PLANTA = {
  key: "k-planta",
  name: "Planta.pdf",
  kind: "pdf",
  size: 1000,
  modified_at: "2026-11-01T12:00:00Z",
  older: [],
  comments: [said("c1", "Maria", "Faltou a garagem")],
};

function FILES_BASE() {
  return {
  stages: [
    { position: 1, groups: [{ folder: null, files: [PLANTA] }], comments: [said("c2", "Equipe Alinea", "Revisão enviada.", "staff")] },
    { position: 2, groups: [], comments: [] as ReturnType<typeof said>[] },
  ],
  };
}
const FILES = FILES_BASE();

function open(page: Partial<Page> = {}, extra: Parameters<typeof fakeApi>[0] = {}, files: unknown = FILES) {
  window.history.pushState({}, "", "/casa-jardim");
  const sent = fakeApi({
    "GET /api/tenant": () => ({ body: TENANT }),
    "GET /api/pages/casa-jardim": () => ({ body: { ...PAGE, ...page } }),
    "GET /api/pages/casa-jardim/files": () => ({ body: files }),
    ...extra,
  });
  render(<ClientApp />);
  return sent;
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("comments", () => {
  it("show nowhere while switched off for the office", async () => {
    const off = {
      stages: [
        { position: 1, groups: [{ folder: null, files: [{ ...PLANTA, comments: null }] }], comments: null },
        { position: 2, groups: [], comments: null },
      ],
    };
    open({ features: [] }, {}, off);
    const stage = await screen.findByRole("region", { name: "Briefing" });
    await within(stage).findByRole("button", { name: "Abrir Planta.pdf" });
    expect(within(stage).queryByRole("button", { name: /coment/i })).not.toBeInTheDocument();
    await userEvent.click(within(stage).getByRole("button", { name: "Abrir Planta.pdf" }));
    const preview = await screen.findByRole("dialog", { name: "Planta.pdf" });
    expect(within(preview).queryByRole("region", { name: /Comentários/ })).not.toBeInTheDocument();
  });

  it("let a client comment on a stage, asking the name once per device", async () => {
    // As the server: what was posted is listed from then on.
    const posted: ReturnType<typeof said>[] = [];
    const sent = open(
      {},
      {
        "POST /api/pages/casa-jardim/comments": (body) => {
          const { body: text, name } = body as { body: string; name: string };
          posted.push(said(`new-${posted.length}`, name, text.trim()));
          return { body: posted.at(-1) };
        },
        "GET /api/pages/casa-jardim/files": () => ({
          body: { stages: [{ ...FILES.stages[0], comments: [...FILES.stages[0]!.comments, ...posted] }, FILES.stages[1]] },
        }),
      },
    );
    const stage = await screen.findByRole("region", { name: "Briefing" });
    await userEvent.click(await within(stage).findByRole("button", { name: "1 comentário" }));
    const thread = within(stage).getByRole("region", { name: "Comentários sobre Briefing" });
    expect(within(thread).getByText("Revisão enviada.")).toBeInTheDocument();
    expect(within(thread).getByText("Escritório")).toBeInTheDocument(); // the office's, marked
    const send = within(thread).getByRole("button", { name: "Enviar comentário" });
    await userEvent.type(within(thread).getByLabelText("Seu comentário"), "Podemos rever a sala?");
    expect(send).toBeDisabled(); // no name yet
    await userEvent.type(within(thread).getByLabelText("Seu nome"), "Maria");
    await userEvent.click(send);
    expect(await within(thread).findByText("Podemos rever a sala?")).toBeInTheDocument();
    expect(sent.find((r) => r.method === "POST")?.body).toEqual({ body: "Podemos rever a sala?", position: 1, name: "Maria" });
    // Remembered: the next comment goes as Maria, without asking.
    expect(within(thread).queryByLabelText("Seu nome")).not.toBeInTheDocument();
    expect(within(thread).getByText(/Comentando como Maria/)).toBeInTheDocument();
    await userEvent.type(within(thread).getByLabelText("Seu comentário"), "E a cozinha?{Control>}{Enter}{/Control}");
    await waitFor(() => expect(sent.filter((r) => r.method === "POST")).toHaveLength(2));
    expect(sent.filter((r) => r.method === "POST")[1]!.body).toMatchObject({ name: "Maria", body: "E a cozinha?" });
    expect(localStorage.getItem("comment-name")).toBe("Maria");
  });

  it("show a file's count on its card, and its conversation under its preview", async () => {
    localStorage.setItem("comment-name", "João");
    const sent = open({}, {
      "POST /api/pages/casa-jardim/comments": () => ({ body: said("c9", "João", "Recebido") }),
    });
    const card = (await screen.findByRole("button", { name: "Abrir Planta.pdf" })).closest(".file") as HTMLElement;
    expect(within(card).getByLabelText("1 comentário")).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Abrir Planta.pdf" }));
    const preview = await screen.findByRole("dialog", { name: "Planta.pdf" });
    const thread = within(preview).getByRole("region", { name: "Comentários sobre Planta.pdf" });
    expect(within(thread).getByText("Faltou a garagem")).toBeInTheDocument();
    await userEvent.type(within(thread).getByLabelText("Seu comentário"), "Recebido");
    await userEvent.click(within(thread).getByRole("button", { name: "Enviar comentário" }));
    expect(await within(thread).findByText("Recebido")).toBeInTheDocument();
    expect(sent.find((r) => r.method === "POST")?.body).toEqual({ body: "Recebido", key: "k-planta", name: "João" });
  });

  it("say what went wrong, and keep what was typed, when a comment is refused", async () => {
    localStorage.setItem("comment-name", "Maria");
    open({}, {
      "POST /api/pages/casa-jardim/comments": () => ({ status: 429, body: { error: "too_many_comments" } }),
    });
    const stage = await screen.findByRole("region", { name: "Briefing" });
    await userEvent.click(await within(stage).findByRole("button", { name: "1 comentário" }));
    const box = within(stage).getByLabelText("Seu comentário");
    await userEvent.type(box, "Olá");
    await userEvent.click(within(stage).getByRole("button", { name: "Enviar comentário" }));
    expect(await screen.findByText(/Muitos comentários seguidos/)).toBeInTheDocument();
    expect(box).toHaveValue("Olá");
  });

  it("let staff comment as the office and remove any comment", async () => {
    const sent = open(
      { staff: { project_id: "p-1", status: "active", row_version: 4, recipients: [] } } as Partial<Page>,
      {
        "GET /api/me": () => ({ body: { name: "Ana", email: "ana@alinea.example", csrf_token: "csrf-9" } }),
        "DELETE /api/pages/casa-jardim/comments/c1": () => ({ status: 204 }),
      },
      asOwner(),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Abrir Planta.pdf" }));
    const preview = await screen.findByRole("dialog", { name: "Planta.pdf" });
    const thread = within(preview).getByRole("region", { name: "Comentários sobre Planta.pdf" });
    expect(within(thread).queryByLabelText("Seu nome")).not.toBeInTheDocument();
    expect(within(thread).getByText("Você comenta pela equipe do escritório.")).toBeInTheDocument();
    await userEvent.click(within(thread).getByRole("button", { name: "Remover o comentário de Maria" }));
    // Asked in the comment itself: a dialog would sit under the preview's.
    const asked = within(thread).getByRole("group", { name: "Remover este comentário?" });
    await userEvent.click(within(asked).getByRole("button", { name: "Manter" }));
    expect(within(thread).getByText("Faltou a garagem")).toBeInTheDocument();
    await userEvent.click(within(thread).getByRole("button", { name: "Remover o comentário de Maria" }));
    await userEvent.click(within(thread).getByRole("button", { name: "Remover" }));
    await waitFor(() => expect(within(thread).queryByText("Faltou a garagem")).not.toBeInTheDocument());
    expect(sent.some((r) => r.method === "DELETE" && r.path.endsWith("/comments/c1"))).toBe(true);
  });

  it("offers no removal to clients", async () => {
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Abrir Planta.pdf" }));
    const preview = await screen.findByRole("dialog", { name: "Planta.pdf" });
    expect(within(preview).queryByRole("button", { name: /Remover/ })).not.toBeInTheDocument();
  });

  it("name the office's comment in the updates, by its stage and file", () => {
    const t = i18next.t.bind(i18next) as (key: string, values?: Record<string, unknown>) => string;
    const entries = entriesFor(
      PAGE,
      [
        { id: "u1", kind: "office_commented", occurred_at: "2026-11-02T12:00:00Z", stage_position: 1, name: "Planta.pdf" },
        { id: "u2", kind: "office_commented", occurred_at: "2026-11-01T12:00:00Z", stage_position: 2, name: null },
      ],
      t,
      "pt-BR",
    );
    expect(entries.map((e) => [e.title, e.context])).toEqual([
      ["Comentário do escritório", "Planta.pdf · 01 Briefing"],
      ["Comentário do escritório", "02 Obra"],
    ]);
  });
});

describe("a comment being sent", () => {
  it("keeps what is typed meanwhile", async () => {
    localStorage.setItem("comment-name", "Maria");
    let answer = (_: unknown) => {};
    open({}, {
      "POST /api/pages/casa-jardim/comments": () =>
        new Promise((resolve) => (answer = () => resolve({ body: said("c3", "Maria", "Primeiro") }))),
    });
    const stage = await screen.findByRole("region", { name: "Briefing" });
    await userEvent.click(await within(stage).findByRole("button", { name: "1 comentário" }));
    const box = within(stage).getByLabelText("Seu comentário");
    await userEvent.type(box, "Primeiro");
    await userEvent.click(within(stage).getByRole("button", { name: "Enviar comentário" }));
    await userEvent.clear(box);
    await userEvent.type(box, "Segundo");
    answer(null);
    expect(await within(stage).findByText("Primeiro")).toBeInTheDocument();
    expect(box).toHaveValue("Segundo");
  });
});

describe("a conversation closed and opened again", () => {
  it("keeps what was posted and removed, and the card's count follows", async () => {
    localStorage.setItem("comment-name", "Maria");
    open(
      { staff: { project_id: "p-1", status: "active", row_version: 4, recipients: [] } } as Partial<Page>,
      {
        "GET /api/me": () => ({ body: { name: "Ana", email: "ana@alinea.example", csrf_token: "csrf-9" } }),
        "POST /api/pages/casa-jardim/comments": () => ({ body: { ...said("c9", "Ana", "Recebido", "staff"), removable: true } }),
        "DELETE /api/pages/casa-jardim/comments/c1": () => ({ status: 204 }),
      },
      asOwner(),
    );
    const card = (await screen.findByRole("button", { name: "Abrir Planta.pdf" })).closest(".file") as HTMLElement;
    await userEvent.click(within(card).getByRole("button", { name: "Abrir Planta.pdf" }));
    let preview = await screen.findByRole("dialog", { name: "Planta.pdf" });
    await userEvent.type(within(preview).getByLabelText("Seu comentário"), "Recebido");
    await userEvent.click(within(preview).getByRole("button", { name: "Enviar comentário" }));
    await within(preview).findByText("Recebido");
    await userEvent.click(within(preview).getByRole("button", { name: "Remover o comentário de Maria" }));
    await userEvent.click(within(preview).getByRole("button", { name: "Remover" }));
    await waitFor(() => expect(within(preview).queryByText("Faltou a garagem")).not.toBeInTheDocument());
    await userEvent.click(within(preview).getByRole("button", { name: "Fechar" }));
    // Opened again: as it was left, not as first listed.
    await userEvent.click(within(card).getByRole("button", { name: "Abrir Planta.pdf" }));
    preview = await screen.findByRole("dialog", { name: "Planta.pdf" });
    expect(within(preview).getByText("Recebido")).toBeInTheDocument();
    expect(within(preview).queryByText("Faltou a garagem")).not.toBeInTheDocument();
    expect(within(card).getByLabelText("1 comentário")).toBeInTheDocument();
  });
});

describe("removing", () => {
  it("lets a client take back what this device posted, and only that", async () => {
    localStorage.setItem("comment-name", "Maria");
    const sent = open({}, {
      "POST /api/pages/casa-jardim/comments": () => ({ body: { ...said("c7", "Maria", "Por engano"), receipt: "r-7" } }),
      "DELETE /api/pages/casa-jardim/comments/c7": () => ({ status: 204 }),
    });
    const stage = await screen.findByRole("region", { name: "Briefing" });
    await userEvent.click(await within(stage).findByRole("button", { name: "1 comentário" }));
    const thread = within(stage).getByRole("region", { name: "Comentários sobre Briefing" });
    expect(within(thread).queryByRole("button", { name: /Remover/ })).not.toBeInTheDocument(); // the office's
    await userEvent.type(within(thread).getByLabelText("Seu comentário"), "Por engano");
    await userEvent.click(within(thread).getByRole("button", { name: "Enviar comentário" }));
    await userEvent.click(await within(thread).findByRole("button", { name: "Remover o comentário de Maria" }));
    await userEvent.click(within(thread).getByRole("button", { name: "Remover" }));
    await waitFor(() => expect(within(thread).queryByText("Por engano")).not.toBeInTheDocument());
    const removal = sent.find((r) => r.method === "DELETE")!;
    expect(removal.headers.get("X-Comment-Receipt")).toBe("r-7");
    expect(JSON.parse(localStorage.getItem("comment-receipts")!)).toEqual({});
  });

  it("remembers on the device which comments it may take back", async () => {
    localStorage.setItem("comment-receipts", JSON.stringify({ c1: "r-1" }));
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Abrir Planta.pdf" }));
    const preview = await screen.findByRole("dialog", { name: "Planta.pdf" });
    expect(within(preview).getByRole("button", { name: "Remover o comentário de Maria" })).toBeInTheDocument();
  });

  it("offers a member removal only where the server allows it", async () => {
    const files = asOwner();
    files.stages[0]!.comments[0]!.removable = false; // someone else's
    open(
      { staff: { project_id: "p-1", status: "active", row_version: 4, recipients: [] } } as Partial<Page>,
      { "GET /api/me": () => ({ body: { name: "Bia", email: "bia@alinea.example", csrf_token: "csrf-9" } }) },
      files,
    );
    const stage = await screen.findByRole("region", { name: "Briefing" });
    await userEvent.click(await within(stage).findByRole("button", { name: "1 comentário" }));
    expect(within(stage).queryByRole("button", { name: /Remover/ })).not.toBeInTheDocument();
  });
});
