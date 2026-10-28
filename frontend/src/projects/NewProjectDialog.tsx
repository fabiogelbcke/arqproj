import { useState } from "react";
import { Checkbox, CheckboxGroup, DialogTrigger, Form, Label, Radio, RadioGroup, Text } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { ApiError } from "../api/client";
import { LIMITS } from "../api/limits";
import { useConnectDrive, useDrive } from "../drive/drive";
import { useMe } from "../session/session";
import { Button } from "../ui/Button";
import { ActionMenu } from "../ui/ActionMenu";
import { DialogFrame } from "../ui/DialogFrame";
import { addEmails } from "../ui/EmailListField";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { toast } from "../ui/Toast";
import { suggestedSlug, useCreateProject, useCreationOptions } from "./projects";
import styles from "./projects.module.css";
import { RecipientsField } from "./RecipientsField";

/** A project, or one that starts as a proposal (A40): its page shows only the
 *  proposal until staff mark it accepted. Two ways in, one form. */
export type NewKind = "project" | "proposal";

function CreateForm({ kind, close }: { kind: NewKind; close: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const options = useCreationOptions();
  const create = useCreateProject();
  // One per dialog: a double click or a retry returns the project already made.
  const [creationKey] = useState(() => crypto.randomUUID());
  const [name, setName] = useState("");
  const [client, setClient] = useState("");
  // The client's addresses for updates (A32, asked here too since 20 Oct 2026).
  const [recipients, setRecipients] = useState<string[]>([]);
  const [newRecipient, setNewRecipient] = useState("");
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
        // One typed but not added counts too; one that can't be added stops it.
        const { list, left } = addEmails(recipients, newRecipient, LIMITS.recipients);
        setRecipients(list);
        setNewRecipient(left.join(", "));
        if (left.length) return;
        create.mutate(
          {
            name,
            client_name: client,
            project_type: type?.key ?? "",
            stages,
            slug,
            recipients: list,
            proposal: kind === "proposal",
            creation_key: creationKey,
          },
          {
            // A proposal's next step is writing it: straight to the proposal's page.
            onSuccess: (project) => {
              close();
              if (kind === "proposal") navigate(`/projetos/${project.id}/proposta`);
              else toast(t("newProject.created", { name: project.name }));
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
      <RecipientsField
        label={t("newProject.recipients")}
        description={t("newProject.recipientsHint")}
        emails={recipients}
        onChange={setRecipients}
        draft={newRecipient}
        onDraft={setNewRecipient}
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
        maxLength={LIMITS.slug}
        autoComplete="off"
        spellCheck="false"
      />
      <p className={styles.note}>{t(kind === "proposal" ? "newProject.proposalNote" : "newProject.publishNote")}</p>
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
          {create.isPending
            ? t("newProject.creating")
            : t(kind === "proposal" ? "newProject.createProposal" : "newProject.create")}
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
          <Button variant="primary" onPress={() => connect.mutate(false)} isDisabled={connect.isPending}>
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
  // New folders are made with the office's grant and shown through the reader.
  const storageReady =
    drive.data?.kind === "folder" ||
    (drive.data?.kind === "google" &&
      drive.data.writer_status === "connected" &&
      drive.data.reader_status === "ok");
  return (
    <DialogFrame title={t(kind === "proposal" ? "newProject.titleProposal" : "newProject.title")} onClose={onClose}>
      {(close) =>
        !drive.data ? (
          <ErrorNotice error={drive.error} />
        ) : storageReady ? (
          <CreateForm kind={kind} close={close} />
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

/** The toolbar's "Nova proposta" and "Novo projeto"; on phones, the floating +
 *  with a menu of the two. */
export function NewProjectButtons() {
  const { t } = useTranslation();
  const [open, setOpen] = useState<NewKind | null>(null);
  return (
    <div className={styles.newButtons} data-tour="new-project">
      <NewProjectButton
        kind="proposal"
        label={t("projects.newProposal")}
        variant="secondary"
        size="small"
        className={styles.newButton}
      />
      <NewProjectButton kind="project" label={t("projects.new")} size="small" className={styles.newButton} />
      <ActionMenu
        label={t("projects.newMenu")}
        className={styles.newFab}
        placement="top end"
        items={[
          { id: "project", label: t("projects.new") },
          { id: "proposal", label: t("projects.newProposal") },
        ]}
        onAction={(id) => setOpen(id as NewKind)}
      >
        <span aria-hidden="true">+</span>
      </ActionMenu>
      {open && <NewProjectDialog kind={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
