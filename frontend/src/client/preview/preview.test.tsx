import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fakeApi } from "../../test/render";
import { PreviewApp, PreviewFrame } from "./PreviewApp";
import { CONTROLS, KEYS, readSettings, writeSettings } from "./settings";
import { previewData } from "./variant";

const NOW = new Date("2026-10-20T12:00:00Z");
const ZONE = "America/Sao_Paulo";
const start = readSettings("");

afterEach(() => vi.unstubAllGlobals());

describe("the preview's settings", () => {
  it("start from each control's initial value, so an empty address is the plain example", () => {
    for (const key of KEYS) expect(start[key]).toBe(CONTROLS[key].initial);
    expect(writeSettings(start)).toBe("");
  });

  it("round-trip through the address, writing only what changed", () => {
    const changed = { ...start, view: "staff", cover: false, stages: 11, longNames: true } as const;
    const query = writeSettings(changed);
    expect(new URLSearchParams(query).size).toBe(4);
    expect(readSettings(query)).toEqual(changed);
  });

  it("keep the start for unknown or broken values, and hold numbers to their range", () => {
    const read = readSettings("view=admin&theme=&stages=99&files=-3&length=abc&evil=1&cover=0");
    expect(read).toEqual({ ...start, stages: CONTROLS.stages.max, files: CONTROLS.files.min, cover: false });
  });
});

describe("the preview's data", () => {
  const data = (query: string) => previewData(readSettings(query), NOW, ZONE);

  it("has as many stages as asked, past the example's own, with files up to the current stage", () => {
    const { project } = data("stages=10&files=5");
    expect(project.stages).toHaveLength(10);
    expect(new Set(project.stages.map((stage) => stage.title)).size).toBe(10);
    const counts = project.stages.map((stage) => stage.groups.flatMap((group) => group.files).length);
    expect(counts).toEqual([5, 5, 5, 0, 0, 0, 0, 0, 0, 0]);
    // Every file is a different one to the page.
    const keys = project.stages.flatMap((stage) => stage.groups.flatMap((group) => group.files.map((f) => f.key)));
    expect(new Set(keys).size).toBe(15);
  });

  it("keeps the current stage and the updates within fewer stages", () => {
    const { project } = data("stages=1");
    expect(project.current_position).toBe(1);
    expect(project.updates.every((update) => (update.stage_position ?? 0) <= 1)).toBe(true);
  });

  it("drops the cover, the meeting (and its updates) and the client's emails when asked", () => {
    const { project, recipients } = data("cover=0&meeting=none&emails=0");
    expect(project.cover_url).toBeNull();
    expect(project.next_meeting).toBeNull();
    expect(project.updates.some((update) => update.kind.startsWith("meeting"))).toBe(false);
    expect(recipients).toEqual([]);
  });

  it("writes a description of each kind, a long one up to the length asked", () => {
    expect(data("description=none").project.description).toBe("");
    const short = data("description=short").project.description;
    expect(short.length).toBeGreaterThan(0);
    expect(short.length).toBeLessThan(80);
    for (const length of [200, 1500, 4000]) {
      const text = data(`length=${length}`).project.description;
      expect(text.length).toBeLessThanOrEqual(length);
      expect(text.length).toBeGreaterThan(length - 100);
    }
  });

  it("gives long names to stages and files, one with nowhere to break", () => {
    const { project } = data("longNames=1");
    const files = project.stages.flatMap((stage) => stage.groups.flatMap((group) => group.files.map((f) => f.name)));
    expect(files.some((name) => name.length > 80 && !name.includes(" "))).toBe(true);
    // A long name is still its file's kind: a photo's ends in .jpg, a drawing's in .dwg.
    const all = project.stages.flatMap((stage) => stage.groups.flatMap((group) => group.files));
    const usual = data("").project.stages.flatMap((stage) => stage.groups.flatMap((group) => group.files));
    all.forEach((file, i) => expect(file.name.split(".").pop()).toBe(usual[i]!.name.split(".").pop()));
    expect(project.stages.some((stage) => stage.title.length > 60)).toBe(true);
    expect(data("").project.stages.every((stage) => stage.title.length < 60)).toBe(true);
  });

  it("is the staff's or the client's view", () => {
    expect(data("view=staff").staff).toBe(true);
    expect(data("").staff).toBe(false);
  });
});

describe("the preview page", () => {
  beforeEach(() => window.history.pushState({}, "", "/painel/previa?frame&meeting=long"));

  it("draws the page from the address without a single request reaching the server", async () => {
    const sent = fakeApi({});
    render(<PreviewFrame />);
    expect(await screen.findByRole("heading", { level: 1, name: "Casa das Araucárias" })).toBeInTheDocument();
    expect(screen.getAllByText("Estúdio Vale Verde").length).toBeGreaterThan(0);
    expect(await screen.findByText(/Apresentação do estudo preliminar de implantação/)).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Ferramentas do escritório" })).toBeNull();
    expect(sent).toEqual([]);
  });

  it("follows the panel's messages, and only those from its own address", async () => {
    const sent = fakeApi({});
    render(<PreviewFrame />);
    await screen.findByRole("heading", { level: 1, name: "Casa das Araucárias" });
    const send = (origin: string) =>
      act(() =>
        window.dispatchEvent(
          new MessageEvent("message", {
            origin,
            data: { type: "preview-settings", settings: { ...start, view: "staff", theme: "dark" } },
          }),
        ),
      );
    send("https://elsewhere.example");
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole("navigation", { name: "Ferramentas do escritório" })).toBeNull();

    send(window.location.origin);
    expect(await screen.findByRole("navigation", { name: "Ferramentas do escritório" })).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(sent).toEqual([]);
  });

  it("lets staff open an editor, whose lists stay in the browser too", async () => {
    window.history.pushState({}, "", "/painel/previa?frame&view=staff");
    const sent = fakeApi({});
    render(<PreviewFrame />);
    await userEvent.click(await screen.findByRole("button", { name: "Editar" }));
    await userEvent.click(await screen.findByRole("button", { name: "Editar informações" }));
    expect(await screen.findByRole("button", { name: "Salvar" })).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50)); // the editor's lists, asked for
    expect(sent).toEqual([]);
  });

  it("keeps the panel's choices in the address and sends each to the frame", async () => {
    window.history.pushState({}, "", "/painel/previa?stages=4");
    render(<PreviewApp />);
    const frame = screen.getByTitle("Página do projeto") as HTMLIFrameElement;
    expect(frame.getAttribute("src")).toBe("/painel/previa?frame&stages=4");
    const posted = vi.spyOn(frame.contentWindow!, "postMessage");

    await userEvent.click(screen.getByLabelText("Celular"));
    await userEvent.click(screen.getByLabelText("Foto de capa"));
    await waitFor(() => expect(readSettings(window.location.search)).toEqual({ ...start, stages: 4, width: "phone", cover: false }));
    expect(posted).toHaveBeenLastCalledWith(
      { type: "preview-settings", settings: { ...start, stages: 4, width: "phone", cover: false } },
      window.location.origin,
    );
    expect(frame.parentElement).toHaveClass("preview-phone");
  });
});
