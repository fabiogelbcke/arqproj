import { useState } from "react";
import { DialogTrigger, Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { ApiError } from "../api/client";
import { LIMITS } from "../api/limits";
import { useConnectDrive, useDrive } from "../drive/drive";
import { useMe } from "../session/session";
import { Button } from "../ui/Button";
import { DialogFrame } from "../ui/DialogFrame";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { suggestedSlug, useCreateProject, useCreationOptions } from "./projects";
import styles from "./projects.module.css";
import { SETUP_PARAM } from "./setup";
import { TypeChoiceField, useStageChoice } from "./StageChoice";

/** A project, or one that starts as a proposal (A42): its page shows only the
 *  proposal until staff mark it accepted. Two ways in, one form. */
export type NewKind = "project" | "proposal";

function CreateForm({
  kind,
  create,
  close,
}: {
  kind: NewKind;
  create: ReturnType<typeof useCreateProject>; // the dialog's, which stays open while it runs
  close: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const options = useCreationOptions();
  // One per dialog: a double click or a retry returns the project already made.
  const [creationKey] = useState(() => crypto.randomUUID());
  const [name, setName] = useState("");
  const [client, setClient] = useState("");
  // Only what it can't do without, and its type: the project's page then walks
  // staff through the rest, an accepted proposal's too (trial, Fabio, 1–2 Nov 2026).
  const proposal = kind === "proposal";
  const choice = useStageChoice(options.data);
  // Follows the name until the address is edited by hand.
  const [typedSlug, setTypedSlug] = useState<string | null>(null);
  const slug = typedSlug ?? suggestedSlug(name);
  const error = create.error;
  // A clash names the project that has the address or name (plan section 10).
  const clash =
    error instanceof ApiError && error.conflictName
      ? error.code === "slug_taken"
        ? t("newProject.slugTakenBy", { name: error.conflictName })
        : error.code === "project_name_taken"
          ? t("newProject.nameTakenBy", { name: error.conflictName })
          : null
      : null;

  return (
    <Form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        create.mutate(
          {
            name,
            client_name: client,
            // The stages come in its setup steps, from its type's (a proposal's, once accepted).
            project_type: choice.type?.key ?? "",
            custom_type: choice.typed,
            stages: [],
            custom_stages: [],
            recipients: [],
            slug,
            proposal,
            creation_key: creationKey,
          },
          {
            // Straight to what comes next: a proposal's generator, its services first; a
            // project's page (outside the painel), to set it up step by step.
            onSuccess: (project) => {
              close();
              if (proposal) navigate(`/projetos/${project.id}/proposta?${SETUP_PARAM}`);
              else window.location.assign(`/${project.slug}?${SETUP_PARAM}`);
            },
          },
        );
      }}
    >
      <TextField
        label={t("newProject.name")}
        value={name}
        onChange={setName}
        isRequired
        maxLength={LIMITS.projectName}
        autoFocus
        autoComplete="off"
      />
      <TextField
        label={t("newProject.client")}
        description={t("newProject.clientHint")}
        value={client}
        onChange={setClient}
        isRequired
        maxLength={LIMITS.clientName}
        autoComplete="off"
      />
      <TypeChoiceField choice={choice} />
      <TextField
        label={t("newProject.slug")}
        description={t("newProject.slugHint")}
        // The whole address, the office's part fixed (as "Novo escritório" shows its domain).
        prefix={`${window.location.host}/`}
        value={slug}
        onChange={(value) => setTypedSlug(value.toLowerCase())}
        isRequired
        maxLength={LIMITS.slug}
        autoComplete="off"
        spellCheck="false"
      />
      <p className={styles.note}>{t(proposal ? "newProject.proposalNote" : "newProject.publishNote")}</p>
      {clash ? (
        <p role="alert" className={styles.problem}>
          {clash}
        </p>
      ) : (
        <ErrorNotice error={error} />
      )}
      {options.error && (
        <div className={styles.actions}>
          <ErrorNotice error={options.error} />
          <Button onPress={() => void options.refetch()}>{t("newProject.retry")}</Button>
        </div>
      )}
      <div className={styles.setupActions}>
        <Button onPress={close} isDisabled={create.isPending}>
          {t("newProject.cancel")}
        </Button>
        <Button type="submit" variant="primary" isDisabled={!options.data} pending={create.isPending}>
          {t(proposal ? "newProject.createProposal" : "newProject.createAndContinue")}
        </Button>
      </div>
    </Form>
  );
}

/** No Drive yet: the owner connects it from here, straight to Google's consent;
 *  a member is told who can. */
function NeedsDrive({ close }: { close: () => void }) {
  const { t } = useTranslation();
  const me = useMe();
  const connect = useConnectDrive();
  const owner = me.data?.role === "owner";
  return (
    <div className={styles.form}>
      <p>{t(owner ? "projects.needsDrive" : "projects.needsDriveMember")}</p>
      <ErrorNotice error={connect.error} />
      <div className={styles.actions}>
        <Button onPress={close}>{t("newProject.cancel")}</Button>
        {owner && (
          <Button variant="primary" onPress={() => connect.mutate(false)} pending={connect.isPending}>
            {t("drive.connect")}
          </Button>
        )}
      </div>
    </div>
  );
}

/** The creation dialog: open while rendered with `onClose`, otherwise the dialog
 *  of the DialogTrigger around it. */
function NewProjectDialog({ kind, onClose }: { kind: NewKind; onClose?: () => void }) {
  const { t } = useTranslation();
  const drive = useDrive();
  // Here, not in the form: closing while the project is made would hide how it went.
  const create = useCreateProject();
  // New folders are made with the office's grant and shown through the reader.
  const storageReady =
    drive.data?.kind === "folder" ||
    (drive.data?.kind === "google" &&
      drive.data.writer_status === "connected" &&
      drive.data.reader_status === "ok");
  return (
    <DialogFrame
      title={t(kind === "proposal" ? "newProject.titleProposal" : "newProject.title")}
      onClose={onClose}
      busy={create.isPending}
    >
      {(close) =>
        !drive.data ? (
          <ErrorNotice error={drive.error} />
        ) : storageReady ? (
          <CreateForm kind={kind} create={create} close={close} />
        ) : (
          <NeedsDrive close={close} />
        )
      }
    </DialogFrame>
  );
}

/** A button that opens the creation dialog, e.g. the first steps' "Criar projeto". */
export function NewProjectButton({
  kind,
  label,
  className,
  variant = "primary",
  size,
}: {
  kind: NewKind;
  label: string;
  className?: string;
  variant?: "primary" | "secondary";
  size?: "small";
}) {
  return (
    <DialogTrigger>
      <Button variant={variant} size={size} className={className}>
        {label}
      </Button>
      <NewProjectDialog kind={kind} />
    </DialogTrigger>
  );
}

/** The toolbar's "Novo projeto"; on phones, the floating + (proposals start in
 *  their own tab, A42). */
export function NewProjectButtons() {
  const { t } = useTranslation();
  return (
    <DialogTrigger>
      <Button variant="primary" size="small" className={styles.newButton} data-tour="new-project">
        <span aria-hidden="true">+</span>
        <span className={styles.newLabel}>{t("projects.new")}</span>
      </Button>
      <NewProjectDialog kind="project" />
    </DialogTrigger>
  );
}
