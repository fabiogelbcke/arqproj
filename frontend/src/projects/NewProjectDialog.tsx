import { useState } from "react";
import {
  Dialog,
  DialogTrigger,
  Form,
  Heading,
  Label,
  Modal,
  ModalOverlay,
  Radio,
  RadioGroup,
} from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import { useDrive } from "../drive/drive";
import { useMe } from "../session/session";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { suggestedSlug, useCreateProject, useTemplates, type ProjectSummary } from "./projects";
import styles from "./projects.module.css";

const CLIENT_MAX = 48;
const NAME_MAX = 120;

function CreateForm({ close, onCreated }: { close: () => void; onCreated: (p: ProjectSummary) => void }) {
  const { t } = useTranslation();
  const templates = useTemplates();
  const create = useCreateProject();
  // One per dialog: a double click or a retry returns the project already made.
  const [creationKey] = useState(() => crypto.randomUUID());
  const [name, setName] = useState("");
  const [client, setClient] = useState("");
  const [template, setTemplate] = useState("standard");
  // Follows the name until the address is edited by hand.
  const [typedSlug, setTypedSlug] = useState<string | null>(null);
  const slug = typedSlug ?? suggestedSlug(name);
  const error = create.error;
  const takenBy = error instanceof ApiError && error.code === "slug_taken" ? error.conflictName : null;

  return (
    <Form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        create.mutate(
          { name, client_name: client, template, slug, creation_key: creationKey },
          {
            onSuccess: (project) => {
              onCreated(project);
              close();
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
        maxLength={NAME_MAX}
        autoFocus
        autoComplete="off"
      />
      <TextField
        label={t("newProject.client")}
        description={t("newProject.clientHint")}
        value={client}
        onChange={setClient}
        isRequired
        maxLength={CLIENT_MAX}
        autoComplete="off"
      />
      <RadioGroup className={styles.templates} value={template} onChange={setTemplate} isRequired>
        <Label className={styles.label}>{t("newProject.template")}</Label>
        {(templates.data ?? []).map((option) => (
          <Radio key={option.key} value={option.key} className={styles.template}>
            <b>{option.label}</b>
            <small>
              {option.stage_count
                ? t("newProject.stageCount", { count: option.stage_count })
                : t("newProject.noStagesHint")}
            </small>
          </Radio>
        ))}
      </RadioGroup>
      <TextField
        label={t("newProject.slug")}
        description={t("newProject.slugHint", { address: `${window.location.host}/${slug || "…"}` })}
        value={slug}
        onChange={(value) => setTypedSlug(value.toLowerCase())}
        isRequired
        maxLength={80}
        autoComplete="off"
        spellCheck="false"
      />
      <p className={styles.note}>{t("newProject.draftNote")}</p>
      {takenBy ? (
        <p role="alert" className={styles.problem}>
          {t("newProject.slugTakenBy", { name: takenBy })}
        </p>
      ) : (
        <ErrorNotice error={error} />
      )}
      <div className={styles.actions}>
        <Button onPress={close}>{t("newProject.cancel")}</Button>
        <Button type="submit" variant="primary" isDisabled={create.isPending}>
          {create.isPending ? t("newProject.creating") : t("newProject.create")}
        </Button>
      </div>
    </Form>
  );
}

function NeedsDrive({ close }: { close: () => void }) {
  const { t } = useTranslation();
  const me = useMe();
  return (
    <div className={styles.form}>
      <p>{t("projects.needsDrive")}</p>
      <div className={styles.actions}>
        <Button onPress={close}>{t("newProject.cancel")}</Button>
        {me.data?.role === "owner" && (
          <Link className={styles.linkButton} to="/configuracoes/drive" onClick={close}>
            {t("projects.needsDriveLink")}
          </Link>
        )}
      </div>
    </div>
  );
}

/** "Novo projeto": the button and its dialog. */
export function NewProjectDialog({ onCreated }: { onCreated: (p: ProjectSummary) => void }) {
  const { t } = useTranslation();
  const drive = useDrive();
  // New folders are made with the office's grant and shown through the reader.
  const storageReady =
    drive.data?.kind === "folder" ||
    (drive.data?.kind === "google" &&
      drive.data.writer_status === "connected" &&
      drive.data.reader_status === "ok");
  return (
    <DialogTrigger>
      <Button variant="primary">{t("projects.new")}</Button>
      <ModalOverlay className={styles.overlay} isDismissable>
        <Modal className={styles.modal}>
          <Dialog className={styles.dialog}>
            {({ close }) => (
              <>
                <Heading slot="title" className={styles.dialogTitle}>
                  {t("newProject.title")}
                </Heading>
                {!drive.data ? (
                  <ErrorNotice error={drive.error} />
                ) : storageReady ? (
                  <CreateForm close={close} onCreated={onCreated} />
                ) : (
                  <NeedsDrive close={close} />
                )}
              </>
            )}
          </Dialog>
        </Modal>
      </ModalOverlay>
    </DialogTrigger>
  );
}
