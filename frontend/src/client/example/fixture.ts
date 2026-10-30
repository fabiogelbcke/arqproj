// The example project's fictional content (plan section 16, "Onboarding help"), in
// Brazilian Portuguese like all demo data. Dates are counted from today, so the
// meeting is always ahead and the files are recent.
import type { Schemas } from "../../api/client";
import roof from "../../projects/covers/capa-01.jpg";
import house from "./images/capa-exemplo.jpg";
import pool from "../../projects/covers/capa-07.jpg";
import facade from "../../projects/covers/capa-09.jpg";
import type { Detail } from "../format";
import dwg from "./files/planta-exemplo.dwg?url";
import pdf from "./files/folha-exemplo.pdf?url";

export const EXAMPLE_TIMEZONE = "America/Sao_Paulo"; // without a signed-in office's own
// The office the example belongs to where no office answers: on Unio's own address,
// which the home links to. On an office's address, that office's name and logo.
export const EXAMPLE_OFFICE = "Estúdio Vale Arquitetura";

/** A file as the page lists it, plus where its bytes are (bundled, or uploaded here). */
export type ExampleFile = Schemas["FileOut"] & { url: string };
export type ExampleStage = Omit<Schemas["StageOut"], "position"> & {
  groups: { folder: string | null; files: ExampleFile[] }[];
};
export type ExampleProject = {
  name: string;
  client_name: string;
  project_type: string;
  project_type_key: string;
  description: string;
  cover_url: string | null;
  team: string[]; // "Responsável" (A41)
  proposal_url: string | null; // the accepted proposal's PDF, before the stages (A42)
  status: "active" | "completed";
  last_update: string;
  details: Detail[];
  stages: ExampleStage[];
  next_meeting: Schemas["MeetingOut"] | null;
  updates: Schemas["UpdateOut"][]; // newest first
};

/** "2026-10-21" and "14:00" in the office's time zone, as an instant. */
export function atOfficeTime(day: string, time: string, timeZone: string): string {
  const wanted = Date.parse(`${day}T${time}:00Z`);
  // The zone's offset at that moment: the same instant read on its clock.
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
      .formatToParts(new Date(wanted))
      .map((part) => [part.type, part.value]),
  );
  const seen = Date.parse(`${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:00Z`);
  return new Date(wanted - (seen - wanted)).toISOString();
}

const DAY = 24 * 60 * 60 * 1000;

export function exampleProject(now: Date, timeZone: string): ExampleProject {
  const ago = (days: number) => new Date(now.getTime() - days * DAY).toISOString();
  const inDays = (days: number) => new Date(now.getTime() + days * DAY).toISOString().slice(0, 10);
  let key = 0;
  const file = (name: string, kind: "image" | "pdf" | "other", url: string, size: number, days: number): ExampleFile => ({
    key: `exemplo-${(key += 1)}`,
    name,
    kind,
    size,
    modified_at: ago(days),
    url,
    updated: false,
    clash: false,
    older: [],
  });
  const meetingDay = inDays(6);
  return {
    name: "Casa das Araucárias",
    client_name: "Família Andrade",
    project_type: "Projeto Arquitetônico",
    project_type_key: "architecture",
    description:
      "Residência de veraneio num terreno em aclive, entre araucárias que serão preservadas.\n" +
      "A casa se abre para a vista do vale, com uma varanda contínua e a sala integrada à cozinha.\n" +
      "- Estrutura mista de concreto e madeira\n" +
      "- Três suítes e escritório\n" +
      "- Piscina na cota mais baixa do terreno",
    cover_url: house,
    team: ["Paula Ribeiro"],
    proposal_url: pdf,
    status: "active",
    last_update: ago(1),
    details: [
      { key: "location", label: "Localização", type: "text", value: "Urubici, SC" },
      { key: "site_area", label: "Área do terreno", type: "area", value: 2400 },
      { key: "built_area", label: "Área construída", type: "area", value: 320 },
      { key: "start_date", label: "Início", type: "date", value: inDays(-75) },
      { key: "expected_delivery", label: "Previsão de entrega", type: "date", value: inDays(120) },
    ],
    stages: [
      {
        title: "Briefing e Levantamento",
        completed: true,
        about: "Entendimento das necessidades e das características do espaço.",
        notes: "Levantamento topográfico recebido. As árvores marcadas no mapa ficam onde estão.",
        groups: [
          { folder: null, files: [file("Programa de necessidades.pdf", "pdf", pdf, 96_256, 52)] },
          {
            folder: "Referências",
            files: [
              file("Piscina com vista.jpg", "image", pool, 1_843_200, 50),
              file("Fachada com brises.jpg", "image", facade, 1_536_000, 50),
            ],
          },
        ],
      },
      {
        title: "Estudos Preliminares / Anteprojeto",
        completed: false,
        about: "Organização dos ambientes e definição do conceito.",
        notes: "Enviamos duas opções de implantação. Vamos conversar sobre elas na próxima reunião.",
        groups: [
          {
            folder: null,
            files: [
              file("Implantação - estudo A.pdf", "pdf", pdf, 2_412_544, 3),
              // A document in its second version (A25): "Atualizado", with the first kept.
              {
                ...file("Planta baixa - térreo.pdf", "pdf", pdf, 1_310_720, 1),
                version: 2,
                updated: true,
                older: [{ ...file("Planta baixa - térreo.pdf", "pdf", pdf, 1_298_432, 3), version: 1 }],
              },
              file("Planta baixa - térreo.dwg", "other", dwg, 5_872_025, 3),
              file("Estudo de cobertura.jpg", "image", roof, 1_228_800, 1),
            ],
          },
        ],
      },
      {
        title: "Projeto 3D",
        completed: false,
        about: "Visualização dos espaços, materiais e volumes.",
        notes: "",
        groups: [],
      },
      {
        title: "Projeto Legal",
        completed: false,
        about: "Documentos para a aprovação na prefeitura.",
        notes: "",
        groups: [],
      },
      {
        title: "Projeto Executivo",
        completed: false,
        about: "Detalhamento técnico das soluções aprovadas.",
        notes: "",
        groups: [],
      },
      {
        title: "Entrega Final",
        completed: false,
        about: "Organização da documentação final do projeto.",
        notes: "",
        groups: [],
      },
    ],
    next_meeting: {
      title: "Apresentação do estudo",
      starts_at: atOfficeTime(meetingDay, "14:00", timeZone),
      ends_at: atOfficeTime(meetingDay, "15:00", timeZone),
      location: "No escritório",
      link: null,
    },
    updates: [
      { id: "exemplo-u1", kind: "file_published", occurred_at: ago(1), stage_position: 2, name: "Estudo de cobertura.jpg" },
      { id: "exemplo-u6", kind: "file_published", occurred_at: ago(1), stage_position: 2, name: "Planta baixa - térreo.pdf" },
      { id: "exemplo-u2", kind: "note_changed", occurred_at: ago(3), stage_position: 2 },
      { id: "exemplo-u3", kind: "file_published", occurred_at: ago(3), stage_position: 2, name: "Implantação - estudo A.pdf" },
      { id: "exemplo-u4", kind: "meeting_scheduled", occurred_at: ago(4), stage_position: null },
      { id: "exemplo-u5", kind: "stage_completed", occurred_at: ago(20), stage_position: 1 },
    ],
  };
}
