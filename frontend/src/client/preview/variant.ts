// The preview page's data: the example project (../example/fixture.ts) changed by
// the panel's settings. Fictional and in Brazilian Portuguese, like all demo data.
import type { ExamplePreview } from "../example/exampleApi";
import { exampleProject, type ExampleFile, type ExampleStage } from "../example/fixture";
import { LIMITS } from "../../api/limits";
import type { Settings } from "./settings";

export const PREVIEW_OFFICE = { name: "Estúdio Vale Verde", logo_url: null, logo_dark_url: null };
const CLIENT_EMAILS = ["marina.andrade@exemplo.com.br", "paulo.andrade@exemplo.com.br"];

const SHORT_DESCRIPTION = "Residência de veraneio entre araucárias.";
// Repeated up to the length asked for.
const PARAGRAPHS = [
  "Residência de veraneio num terreno em aclive, entre araucárias que serão preservadas. " +
    "A casa se abre para a vista do vale, com uma varanda contínua e a sala integrada à cozinha.",
  "- Estrutura mista de concreto e madeira\n- Três suítes e escritório\n- Piscina na cota mais baixa do terreno",
  "O programa foi revisto depois do levantamento topográfico: a garagem desce meio nível e libera " +
    "a frente do lote para o jardim. As aberturas a oeste ganham brises de madeira para o sol da tarde.",
];

const MORE_STAGES = ["Interiores", "Paisagismo", "Luminotécnico", "Compatibilização", "Acompanhamento de Obra"];
// "Long" is the longest the server allows (api/limits.ts): these are cut to it, as
// typing stops there.
const LONG_STAGE = "Estudos Preliminares, Anteprojeto e Compatibilização com os Projetos Complementares";
// Long names (each file keeps its own extension), one with no spaces to break at.
const LONG_FILES = [
  "Planta baixa do pavimento térreo - revisão 04 - compatibilizada com estrutural e hidrossanitário",
  "Implantacao_geral_estudo_A_revisao_final_v3_aprovada_pelo_cliente_com_ajustes_da_prefeitura",
  "Perspectiva da varanda ao entardecer vista a partir do jardim inferior junto à piscina",
];

/** The text made exactly the field's limit: repeated if short, cut where typing stops. */
function fit(text: string, limit: number): string {
  return text.padEnd(limit, ` ${text}`).slice(0, limit);
}

const MEETINGS = {
  short: { title: "Reunião", location: "No escritório" },
  long: {
    title: fit("Apresentação do estudo preliminar de implantação e cobertura", LIMITS.meetingTitle),
    location: fit("Rua das Araucárias, 1234, sala 56, Centro, Urubici - SC, junto à praça", LIMITS.meetingLocation),
  },
};

function description(settings: Settings): string {
  if (settings.description === "none") return "";
  if (settings.description === "short") return SHORT_DESCRIPTION;
  let text = "";
  for (let i = 0; text.length < settings.length; i += 1) text += (text ? "\n" : "") + PARAGRAPHS[i % PARAGRAPHS.length];
  const cut = text.slice(0, settings.length);
  return cut.length < text.length ? cut.slice(0, cut.lastIndexOf(" ")).trimEnd() + "." : cut;
}

/** What the preview's page shows for these settings. */
export function previewData(settings: Settings, now: Date, timeZone: string): ExamplePreview {
  const base = exampleProject(now, timeZone);
  // The fixture's files, as patterns for as many as asked for (images, PDFs, a drawing).
  const patterns = base.stages.flatMap((stage) => stage.groups.flatMap((group) => group.files));
  let key = 0;
  // In every stage: the page takes files in any of them.
  const files = (position: number): ExampleFile[] =>
    Array.from({ length: settings.files }, (_, i) => {
      const pattern = patterns[(position + i) % patterns.length]!;
      const extension = pattern.name.slice(pattern.name.lastIndexOf("."));
      const name = settings.longNames && i < LONG_FILES.length ? LONG_FILES[i]! + extension : pattern.name;
      return { ...pattern, key: `previa-${(key += 1)}`, name };
    });
  const stages: ExampleStage[] = Array.from({ length: settings.stages }, (_, i) => {
    const stage = base.stages[i] ?? { title: MORE_STAGES[i - base.stages.length] ?? `Etapa ${i + 1}`, about: null, notes: "", completed: false, groups: [] };
    const title = settings.longNames && i % 2 === 0 ? fit(LONG_STAGE, LIMITS.stageTitle) : stage.title;
    const shown = files(i + 1);
    return { ...stage, title, groups: shown.length ? [{ folder: null, files: shown }] : [] };
  });
  const meeting = settings.meeting === "none" ? null : { ...base.next_meeting!, ...MEETINGS[settings.meeting] };
  return {
    project: {
      ...base,
      description: description(settings),
      cover_url: settings.cover ? base.cover_url : null,
      stages,
      next_meeting: meeting,
      // Only what the stages shown have: a stage's update needs its stage.
      updates: base.updates.filter(
        (update) => (update.stage_position ?? 0) <= settings.stages && (meeting || !update.kind.startsWith("meeting")),
      ),
    },
    office: PREVIEW_OFFICE,
    staff: settings.view === "staff",
    recipients: settings.emails ? CLIENT_EMAILS : [],
  };
}
