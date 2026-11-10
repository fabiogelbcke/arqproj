// The project type and its stages, as a new project chooses them: the type in
// the creation form ("Novo projeto" and "Nova proposta"), the stages in the first
// of the project's setup steps on its page (an accepted proposal's too).
import { useState } from "react";
import { Checkbox, CheckboxGroup, Label, Radio, RadioGroup, Text } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { LIMITS } from "../api/limits";
import { Button } from "../ui/Button";
import { TextField } from "../ui/TextField";
import type { CreationOptions } from "./projects";
import uiStyles from "../ui/ui.module.css";
import styles from "./projects.module.css";

const OWN = "own:";
/** The type the office names itself, per project (2 Nov 2026). */
export const OTHER_TYPE = "other";

/** Lowercase, without accents, punctuation or a word's plural:
 *  "Detalhamentos – Especificações" → "detalhamento especificacao". */
function plain(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .split(" ")
    .map(singular)
    .join(" ");
}

/** A Portuguese word without its plural, accents already gone: ões and ães →
 *  ão ("especificacoes" → "especificacao"), ais → al, eis → el, else a final s. */
function singular(word: string): string {
  if (word.length <= 3) return word;
  if (word.endsWith("oes") || word.endsWith("aes")) return `${word.slice(0, -3)}ao`;
  if (word.endsWith("ais")) return `${word.slice(0, -3)}al`;
  if (word.endsWith("eis")) return `${word.slice(0, -3)}el`;
  return word.endsWith("s") ? word.slice(0, -1) : word;
}

/** An accepted proposal's services as the project's stages, one each (2 Nov
 *  2026): the built-in stage a service matches, else the office's own stage named
 *  as the service. They match when one name, plainly written, contains the other
 *  ("Projeto Executivo de Arquitetura" → Projeto Executivo); too short a name
 *  ("Projeto") matches no stage, or it would match half the list. */
export function stagesFromServices(
  stages: { key: string; title: string }[],
  services: string[],
): { builtin: string[]; own: string[] } {
  const builtin: string[] = [];
  const own: string[] = [];
  for (const service of services) {
    const name = plain(service);
    if (!name) continue;
    const stage = stages.find((option) => {
      const title = plain(option.title);
      if (name === title) return true;
      const [short, long] = name.length < title.length ? [name, title] : [title, name];
      return short.length >= 8 && long.includes(short);
    });
    if (stage) {
      if (!builtin.includes(stage.key)) builtin.push(stage.key);
    } else if (!own.some((title) => plain(title) === name)) {
      own.push(service.trim().slice(0, LIMITS.stageTitle));
    }
  }
  return { builtin, own };
}

/** What is chosen: the type, its built-in stages (in the shared order) and the
 *  office's own, named as typed. */
export function useStageChoice(options: CreationOptions | undefined, initialType?: string) {
  const [typeKey, setTypeKey] = useState<string | null>(initialType ?? null);
  // null: the chosen type's usual stages; a list once staff tick or untick one.
  const [ticked, setTicked] = useState<string[] | null>(null);
  // The office's own stages, named here, after the built-in ones; unticking one drops it.
  const [own, setOwn] = useState<string[]>([]);
  // "Outro"'s name, as typed; sent only with that type.
  const [customType, setCustomType] = useState("");
  const types = options?.types ?? [];
  // The project's own type even when hidden for new projects (A44); else the first
  // that may be chosen.
  const type = types.find((option) => option.key === typeKey) ?? types.find((option) => !option.hidden);
  const order = (options?.stages ?? []).map((stage) => stage.key);
  const stages = (ticked ?? type?.stages ?? []).slice().sort((a, b) => order.indexOf(a) - order.indexOf(b));
  const typed = type?.key === OTHER_TYPE ? customType.trim() : null;
  return {
    options,
    type,
    stages,
    own,
    customType,
    typed,
    setTypeKey,
    setTicked,
    setOwn,
    setCustomType,
  };
}

export type StageChoice = ReturnType<typeof useStageChoice>;

/** The type, one of the built-in ones or "Outro" with its name; choosing one
 *  ticks its usual stages again. */
export function TypeChoiceField({ choice }: { choice: StageChoice }) {
  const { t } = useTranslation();
  const { options, type, customType, setTypeKey, setTicked, setCustomType } = choice;
  return (
    <>
      <RadioGroup
        className={styles.types}
        value={type?.key ?? null}
        onChange={(key) => {
          setTypeKey(key);
          setTicked(null); // the new type's usual stages
        }}
        isRequired
      >
        <Label className={styles.label}>{t("newProject.type")}</Label>
        <div className={styles.typeOptions}>
          {(options?.types ?? [])
            .filter((option) => !option.hidden)
            .map((option) => (
            <Radio key={option.key} value={option.key} className={styles.choice}>
              {option.label}
            </Radio>
          ))}
        </div>
      </RadioGroup>
      {type?.key === OTHER_TYPE && (
        <TextField
          label={t("newProject.customType")}
          description={t("newProject.customTypeHint")}
          placeholder={t("newProject.customTypeExample")}
          value={customType}
          onChange={setCustomType}
          isRequired
          maxLength={LIMITS.customType}
          autoComplete="off"
          autoFocus
        />
      )}
    </>
  );
}

/** The type's stages, its usual ones ticked, and the office's own by name. */
export function StageChoiceFields({
  choice,
  labelHidden = false,
  countOnly = false,
}: {
  choice: StageChoice;
  labelHidden?: boolean; // the dialog's title already says it: for screen readers only
  countOnly?: boolean; // only "3 etapas marcadas.": the setup step explains the rest above
}) {
  const { t } = useTranslation();
  const { options, type, stages, own, setTicked, setOwn } = choice;
  const [newStage, setNewStage] = useState("");
  const [stageProblem, setStageProblem] = useState<string | null>(null);
  // Only the stages that suit the type, unless staff ask for every one.
  const [all, setAll] = useState(false);
  const every = options?.stages ?? [];
  const listed = all ? every : every.filter((stage) => type?.offered.includes(stage.key) || stages.includes(stage.key));
  const addOwn = () => {
    const title = newStage.trim();
    if (!title) return;
    const names = [...every.map((s) => s.title), ...own].map((n) => n.toLocaleLowerCase());
    if (names.includes(title.toLocaleLowerCase())) return setStageProblem(t("newProject.stageExists", { title }));
    setOwn([...own, title]);
    setNewStage("");
    setStageProblem(null);
  };
  return (
    <>
      <CheckboxGroup
        className={styles.stagesField}
        value={[...stages, ...own.map((title) => OWN + title)]}
        onChange={(values) => {
          setTicked(values.filter((value) => !value.startsWith(OWN)));
          setOwn(own.filter((title) => values.includes(OWN + title)));
        }}
      >
        <Label className={labelHidden ? uiStyles.visuallyHidden : styles.label}>{t("newProject.stages")}</Label>
        <Text slot="description" className={styles.note}>
          {stages.length + own.length
            ? t(countOnly ? "newProject.stagesCount" : "newProject.stagesHint", {
                count: stages.length + own.length,
              })
            : t("newProject.noStagesHint")}
        </Text>
        <div className={styles.stageOptions}>
          {listed.map((stage) => (
            <Checkbox key={stage.key} value={stage.key} className={styles.stageOption}>
              <span className={styles.box} aria-hidden="true" />
              {stage.title}
            </Checkbox>
          ))}
          {own.map((title) => (
            <Checkbox key={OWN + title} value={OWN + title} className={styles.stageOption}>
              <span className={styles.box} aria-hidden="true" />
              {title}
            </Checkbox>
          ))}
        </div>
        {listed.length < every.length || all ? (
          <button type="button" className={styles.moreStages} onClick={() => setAll(!all)}>
            {t(all ? "newProject.fewerStages" : "newProject.allStages")}
          </button>
        ) : null}
      </CheckboxGroup>
      {/* Another stage, named as the office calls it (Fabio, 29 Oct 2026). */}
      <div className={styles.ownStage}>
        <TextField
          label={t("newProject.ownStage")}
          value={newStage}
          onChange={(value) => {
            setNewStage(value);
            setStageProblem(null);
          }}
          onKeyDown={(event) => {
            if (event.key !== "Enter") return;
            event.preventDefault(); // adds the stage; the form isn't sent yet
            addOwn();
          }}
          maxLength={LIMITS.stageTitle}
          autoComplete="off"
        />
        <Button onPress={addOwn} isDisabled={!newStage.trim()}>
          {t("newProject.addStage")}
        </Button>
      </div>
      {stageProblem && (
        <p role="alert" className={styles.problem}>
          {stageProblem}
        </p>
      )}
    </>
  );
}
