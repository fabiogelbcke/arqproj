// A new project's setup on its page, one step at a time in a dialog, after the
// painel's "Novo projeto" asked only for the name, client, type and address
// (trial, Fabio, 1 Nov 2026): stages, description and details, cover photo, the
// client's emails. Each step saves on "Continuar" or is skipped; everything
// stays editable in edit mode afterwards.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, call } from "../api/client";
import { LIMITS } from "../api/limits";
import { type CreationOptions } from "../projects/projects";
import projectStyles from "../projects/projects.module.css";
import { SETUP_STEPS } from "../projects/setup";
import { SetupProgress } from "../projects/SetupProgress";
import { StageChoiceFields, stagesFromServices, useStageChoice } from "../projects/StageChoice";
import { Button } from "../ui/Button";
import { DialogFrame } from "../ui/DialogFrame";
import { EmailListField, addEmails } from "../ui/EmailListField";
import { ImageCropDialog } from "../ui/ImageCropDialog";
import { toast } from "../ui/Toast";
import { DetailRows, useDetailTypes, useSave, type DetailRow } from "./Editors";
import type { Page } from "./format";

type Staff = NonNullable<Page["staff"]>;

/** The step's buttons: "Pular" and "Continuar" (on the last step, "Concluir"). */
function Actions({
  busy,
  last,
  onSkip,
  saving,
}: {
  busy: boolean;
  last: boolean;
  onSkip: () => void;
  saving?: string; // what the button says while saving, if more than "Salvando…"
}) {
  const { t } = useTranslation();
  return (
    <div className={projectStyles.setupActions}>
      <Button onPress={onSkip} isDisabled={busy}>
        {t("setup.skip")}
      </Button>
      <Button type="submit" variant="primary" isDisabled={busy}>
        {busy ? (saving ?? t("setup.saving")) : t(last ? "setup.finish" : "setup.next")}
      </Button>
    </div>
  );
}

function Problem({ text }: { text: string | null }) {
  return text ? (
    <p role="alert" className={projectStyles.problem}>
      {text}
    </p>
  ) : null;
}

type StepProps = {
  page: Page;
  staff: Staff;
  // The project's row version as this dialog last saved it: the page behind
  // reloads after each step, maybe after the next one is sent.
  version: number;
  onSaved: (version: number) => void;
  onSkip: () => void;
  last: boolean;
};

function StagesStep({ page, staff, version, onSaved, onSkip, last }: StepProps) {
  const { t } = useTranslation();
  const [options, setOptions] = useState<CreationOptions>();
  const [loadFailed, setLoadFailed] = useState(false);
  useEffect(() => {
    call(api.GET("/api/project-types")).then(setOptions, () => setLoadFailed(true));
  }, []);
  // The type chosen at creation: its stages listed, its usual ones ticked.
  const choice = useStageChoice(options, page.project_type_key);
  // An accepted proposal: its services become the stages, one each (2 Nov 2026);
  // null while they load.
  const fromProposal = page.proposal_url != null;
  const [services, setServices] = useState<string[] | null>(fromProposal ? null : []);
  useEffect(() => {
    if (!fromProposal) return;
    call(api.GET("/api/projects/{project_id}/proposal", { params: { path: { project_id: staff.project_id } } })).then(
      (found) => setServices(found.start.services.map((service) => service.title)),
      () => setServices([]), // only suggestions: without them, the type's usual stages
    );
  }, [fromProposal, staff.project_id]);
  const { setTicked, setOwn } = choice;
  useEffect(() => {
    if (!options || !services?.length) return;
    const { builtin, own } = stagesFromServices(options.stages, services);
    setTicked(builtin);
    setOwn(own);
  }, [options, services, setTicked, setOwn]);
  // Stages already added: a retry after a failure part way adds only the rest.
  const added = useRef(new Set<string>());
  // "Criando etapas (2 de 7)…": each makes its folder in Drive, one at a time.
  const [making, setMaking] = useState<{ done: number; total: number } | null>(null);
  const saved = useRef(version);
  const save = useSave(() => onSaved(saved.current), { quiet: true });
  useEffect(() => {
    if (!save.busy) setMaking(null);
  }, [save.busy]);
  const path = { params: { path: { project_id: staff.project_id } } };
  return (
    <form
      className={projectStyles.form}
      onSubmit={(event) => {
        event.preventDefault();
        void save.run(async () => {
          // One at a time, in order: each makes its folder in the office's Drive.
          // A stage the project already has (a proposal from before 2 Nov 2026
          // got its stages at creation) is not added again.
          const has = new Set(page.stages.map((stage) => stage.title.toLocaleLowerCase()));
          const titleOf = (key: string) => options?.stages.find((stage) => stage.key === key)?.title ?? key;
          const wanted = [
            ...choice.stages.map((key) => ({ id: key, title: titleOf(key), body: { builtin_key: key } })),
            ...choice.own.map((title) => ({ id: `own:${title}`, title, body: { title } })),
          ].filter((stage) => !has.has(stage.title.toLocaleLowerCase()));
          for (const [done, stage] of wanted.entries()) {
            setMaking({ done: done + 1, total: wanted.length });
            if (added.current.has(stage.id)) continue;
            await call(
              api.POST("/api/projects/{project_id}/stages", {
                ...path,
                body: { row_version: saved.current, ...stage.body },
              }),
            );
            added.current.add(stage.id);
            saved.current += 1;
          }
        });
      }}
    >
      <p className={`${projectStyles.note} ${projectStyles.setupHint}`}>
        {t(fromProposal ? "setup.stagesHintProposal" : "setup.stagesHint")}
      </p>
      {options ? (
        <StageChoiceFields choice={choice} labelHidden countOnly />
      ) : (
        <p className={projectStyles.note}>{t(loadFailed ? "errors.unexpected" : "page.loading")}</p>
      )}
      <Problem text={save.problem} />
      <Actions
        busy={save.busy || !options || services === null}
        last={last}
        onSkip={onSkip}
        saving={making ? t("setup.makingStages", making) : undefined}
      />
    </form>
  );
}

function DetailsStep({ page, staff, version, onSaved, onSkip, last }: StepProps) {
  const { t } = useTranslation();
  const types = useDetailTypes();
  const [first] = useState(() => page.details.map((d) => ({ key: d.key, value: String(d.value) })));
  const [text, setText] = useState(page.description);
  const [rows, setRows] = useState<DetailRow[]>(first);
  const save = useSave(() => onSaved(version + 1), { quiet: true });
  return (
    <form
      className={projectStyles.form}
      onSubmit={(event) => {
        event.preventDefault();
        // Nothing typed: on to the next step, nothing saved.
        if (text === page.description && JSON.stringify(rows) === JSON.stringify(first)) return onSkip();
        void save.run(() =>
          call(
            api.PATCH("/api/projects/{project_id}/content", {
              params: { path: { project_id: staff.project_id } },
              body: {
                row_version: version,
                description: text,
                details: rows.filter((row) => row.value.trim() !== ""),
              },
            }),
          ),
        );
      }}
    >
      <div className="field">
        <label htmlFor="setup-description">{t("edit.description")}</label>
        <textarea
          className="textarea"
          id="setup-description"
          rows={5}
          maxLength={LIMITS.description}
          value={text}
          onChange={(e) => setText(e.target.value)}
          autoFocus
        />
        <p className="hint">{t("edit.descriptionHint")}</p>
      </div>
      <div className="field">
        <span className={projectStyles.label}>{t("edit.details")}</span>
        <DetailRows page={page} types={types} rows={rows} onChange={setRows} />
      </div>
      <Problem text={save.problem} />
      <Actions busy={save.busy} last={last} onSkip={onSkip} />
    </form>
  );
}

const PHOTOS = "image/jpeg,image/png,image/webp";

function CoverStep({ page, staff, version, onSaved, onSkip, last }: StepProps) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [cropping, setCropping] = useState<string | null>(null);
  // The photo just cropped, shown until the page behind has it.
  const [chosen, setChosen] = useState<{ file: File; url: string } | null>(null);
  useEffect(() => () => {
    if (chosen) URL.revokeObjectURL(chosen.url);
  }, [chosen]);
  // The cover doesn't change the row version.
  const save = useSave(() => onSaved(version), { quiet: true });
  const shown = chosen?.url ?? page.cover_url;
  return (
    <form
      className={projectStyles.form}
      onSubmit={(event) => {
        event.preventDefault();
        if (!chosen) return onSkip();
        void save.run(() =>
          call(
            api.PUT("/api/projects/{project_id}/cover", {
              params: { path: { project_id: staff.project_id } },
              // OpenAPI describes an uploaded file as a binary string; it is the File.
              body: { file: chosen.file as unknown as string },
              bodySerializer: (body) => {
                const form = new FormData();
                form.append("file", body.file as unknown as Blob, chosen.file.name);
                return form;
              },
            }),
          ),
        );
      }}
    >
      <p className={`${projectStyles.note} ${projectStyles.setupHint}`}>{t("setup.coverHint")}</p>
      {shown ? (
        <img className={projectStyles.setupCover} src={shown} alt="" />
      ) : (
        <button type="button" className={projectStyles.setupCoverEmpty} onClick={() => input.current?.click()}>
          <strong>{t("edit.addCover")}</strong>
          <span>{t("edit.addCoverHint")}</span>
        </button>
      )}
      {shown && (
        <Button onPress={() => input.current?.click()} isDisabled={save.busy}>
          {t("edit.changeCover")}
        </Button>
      )}
      <input
        ref={input}
        type="file"
        hidden
        accept={PHOTOS}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = ""; // the same photo can be chosen again
          if (file) setCropping(URL.createObjectURL(file));
        }}
      />
      {cropping && (
        <ImageCropDialog
          source={cropping}
          kind="cover"
          name="capa.jpg"
          onCancel={() => {
            URL.revokeObjectURL(cropping);
            setCropping(null);
          }}
          onCropped={(file) => {
            URL.revokeObjectURL(cropping);
            setCropping(null);
            setChosen({ file, url: URL.createObjectURL(file) });
          }}
        />
      )}
      <Problem text={save.problem} />
      <Actions busy={save.busy} last={last} onSkip={onSkip} />
    </form>
  );
}

function EmailsStep({ staff, version, onSaved, onSkip, last }: StepProps) {
  const { t } = useTranslation();
  const [emails, setEmails] = useState(() => staff.recipients.map((recipient) => recipient.email));
  const [draft, setDraft] = useState("");
  const saved = useRef(version);
  const save = useSave(() => onSaved(saved.current), { quiet: true });
  return (
    <form
      className={projectStyles.form}
      onSubmit={(event) => {
        event.preventDefault();
        // One typed but not added counts too; one that can't be added stops it.
        const { list, left } = addEmails(emails, draft, LIMITS.recipients);
        setEmails(list);
        setDraft(left.join(", "));
        if (left.length) return;
        if (list.join() === staff.recipients.map((recipient) => recipient.email).join()) return onSkip();
        void save.run(async () => {
          const project = await call(
            api.PATCH("/api/projects/{project_id}", {
              params: { path: { project_id: staff.project_id } },
              body: { row_version: version, recipients: list },
            }),
          );
          saved.current = project.row_version;
        });
      }}
    >
      <EmailListField
        label={t("projectSettings.recipients")}
        labelHidden // the step's title already says it
        description={t("newProject.recipientsHint")}
        emails={emails}
        onChange={setEmails}
        draft={draft}
        onDraft={setDraft}
        max={LIMITS.recipients}
        addLabel={t("projectSettings.addRecipient")}
        newLabel={t("projectSettings.newRecipient")}
        removeLabel={(email) => t("projectSettings.removeRecipient", { email })}
      />
      <Problem text={save.problem} />
      <Actions busy={save.busy} last={last} onSkip={onSkip} />
    </form>
  );
}

const STEPS = { stages: StagesStep, details: DetailsStep, cover: CoverStep, emails: EmailsStep } as const;

export function SetupSteps({
  page,
  onChanged,
  onClose,
}: {
  page: Page;
  onChanged: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const staff = page.staff!;
  const [step, setStep] = useState(0);
  const [version, setVersion] = useState(staff.row_version);
  const name = SETUP_STEPS[step]!;
  const Step = STEPS[name];
  const last = step === SETUP_STEPS.length - 1;
  const next = () => {
    if (!last) return setStep(step + 1);
    toast(t("setup.done"));
    onClose();
  };
  return (
    <DialogFrame title={t(`setup.title.${name}`)} onClose={onClose} outsideCloses={false}>
      <div className={projectStyles.form}>
        <SetupProgress step={step} />
        <Step
          key={name}
          page={page}
          staff={staff}
          version={version}
          last={last}
          onSkip={next}
          onSaved={(saved) => {
            setVersion(saved);
            onChanged(); // the page behind shows what was just saved
            next();
          }}
        />
      </div>
    </DialogFrame>
  );
}
