// A new proposal's first step, right after "Nova proposta" (2 Nov 2026): which of
// its type's stages it offers, the office's own by name. They become its services,
// one each, as its stages will be once it is accepted (A42).
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { LIMITS } from "../api/limits";
import { useCreationOptions } from "../projects/projects";
import projectStyles from "../projects/projects.module.css";
import { StageChoiceFields, useStageChoice } from "../projects/StageChoice";
import { Button } from "../ui/Button";
import { DialogFrame } from "../ui/DialogFrame";
import { ErrorNotice } from "../ui/ErrorNotice";
import type { Generator, Preset } from "./proposals";

/** The services for the stages chosen, in the stages' order, the office's own
 *  last: each in the office's words for a service of that name, else the
 *  stage's description in the type's words (an office's own stage, blank). */
export function servicesFor(
  data: Pick<Generator, "presets" | "stage_about">,
  stages: { key: string; title: string }[],
  chosen: string[],
  own: string[],
): Preset[] {
  const offered = (title: string) =>
    data.presets.find(
      (p) =>
        p.title.trim().toLocaleLowerCase() === title.trim().toLocaleLowerCase(),
    )?.description;
  const builtin = stages
    .filter((stage) => chosen.includes(stage.key))
    .map((stage) => ({
      title: stage.title,
      description: offered(stage.title) ?? data.stage_about[stage.key] ?? "",
    }));
  const named = own.map((title) => ({
    title,
    description: offered(title) ?? "",
  }));
  return [...builtin, ...named]
    .slice(0, LIMITS.proposalServices)
    .map((s) => ({
      title: s.title.slice(0, LIMITS.serviceTitle),
      description: s.description.slice(0, LIMITS.serviceDescription),
    }));
}

export function ServicesStep({
  data,
  onChosen,
  onClose,
}: {
  data: Generator;
  onChosen: (services: Preset[]) => void;
  onClose: () => void; // skipped or closed: the type's usual stages, as it opened
}) {
  const { t } = useTranslation();
  const options = useCreationOptions();
  const choice = useStageChoice(options.data, data.project_type);
  return (
    <DialogFrame
      title={t("proposal.services.title")}
      onClose={onClose}
      outsideCloses={false}
    >
      <Form
        className={projectStyles.form}
        onSubmit={(event) => {
          event.preventDefault();
          onChosen(
            servicesFor(
              data,
              options.data?.stages ?? [],
              choice.stages,
              choice.own,
            ),
          );
        }}
      >
        <p className={`${projectStyles.note} ${projectStyles.setupHint}`}>
          {t("proposal.services.hint")}
        </p>
        {options.data ? (
          <StageChoiceFields choice={choice} labelHidden countOnly />
        ) : options.error ? (
          <ErrorNotice error={options.error} />
        ) : (
          <p className={projectStyles.note}>{t("app.loading")}</p>
        )}
        <div className={projectStyles.setupActions}>
          <Button onPress={onClose}>{t("setup.skip")}</Button>
          <Button
            type="submit"
            variant="primary"
            isDisabled={
              !options.data || choice.stages.length + choice.own.length === 0
            }
          >
            {t("setup.next")}
          </Button>
        </div>
      </Form>
    </DialogFrame>
  );
}
