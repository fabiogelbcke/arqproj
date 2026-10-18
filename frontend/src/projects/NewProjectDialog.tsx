import { useState } from "react";
import {
  Checkbox,
  CheckboxGroup,
  Dialog,
  DialogTrigger,
  Form,
  Heading,
  Label,
  Modal,
  ModalOverlay,
  Radio,
  RadioGroup,
  Text,
} from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import { useDrive } from "../drive/drive";
import { useMe } from "../session/session";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { suggestedSlug, useCreateProject, useCreationOptions, type ProjectSummary } from "./projects";
import styles from "./projects.module.css";

const CLIENT_MAX = 48;
const NAME_MAX = 120;

function CreateForm({ close, onCreated }: { close: () => void; onCreated: (p: ProjectSummary) => void }) {
  const { t } = useTranslation();
  const options = useCreationOptions();
  const create = useCreateProject();
  // One per dialog: a double click or a retry returns the project already made.
  const [creationKey] = useState(() => crypto.randomUUID());
  const [name, setName] = useState("");
  const [client, setClient] = useState("");
  const [typeKey, setTypeKey] = useState<string | null>(null);
  // null: the chosen type's usual stages; a list once staff tick or untick one.
  const [ticked, setTicked] = useState<string[] | null>(null);
  const types = options.data?.types ?? [];
  const type = types.find((option) => option.key === typeKey) ?? types[0];
  const stages = ticked ?? type?.stages ?? [];
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
          { name, client_name: client, project_type: type?.key ?? "", stages, slug, creation_key: creationKey },
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
          {types.map((option) => (
            <Radio key={option.key} value={option.key} className={styles.choice}>
              {option.label}
            </Radio>
          ))}
        </div>
      </RadioGroup>
      <CheckboxGroup className={styles.stagesField} value={stages} onChange={setTicked}>
        <Label className={styles.label}>{t("newProject.stages")}</Label>
        <Text slot="description" className={styles.note}>
          {stages.length
            ? t("newProject.stagesHint", { count: stages.length })
            : t("newProject.noStagesHint")}
        </Text>
        <div className={styles.stageOptions}>
          {(options.data?.stages ?? []).map((stage) => (
            <Checkbox key={stage.key} value={stage.key} className={styles.stageOption}>
              <span className={styles.box} aria-hidden="true" />
              {stage.title}
            </Checkbox>
          ))}
        </div>
      </CheckboxGroup>
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
      <p className={styles.note}>{t("newProject.publishNote")}</p>
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
      <div className={styles.actions}>
        <Button onPress={close}>{t("newProject.cancel")}</Button>
        <Button type="submit" variant="primary" isDisabled={create.isPending || !options.data}>
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
      <Button variant="primary" className={styles.newButton}>
        <span aria-hidden="true">+</span>
        <span className={styles.newLabel}>{t("projects.new")}</span>
      </Button>
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
