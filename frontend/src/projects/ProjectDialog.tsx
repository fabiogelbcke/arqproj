import { useState } from "react";
import { Dialog, Form, Heading, Label, Modal, ModalOverlay, Radio, RadioGroup } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { ApiError } from "../api/client";
import { Button } from "../ui/Button";
import { CloseButton } from "../ui/CloseButton";
import { EmailListField, addEmails } from "../ui/EmailListField";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { toast } from "../ui/Toast";
import { useChangeProject, type ProjectSummary } from "./projects";
import styles from "./projects.module.css";

const NAME_MAX = 120;
const CLIENT_MAX = 30; // for now (Fabio, 18 Oct 2026); the API checks the same
const RECIPIENTS_MAX = 20; // the server checks it too

const sameList = (a: string[], b: string[]) => a.length === b.length && a.every((x, i) => x === b[i]);

/** The project's settings (A24), after the prototype's "Projeto" dialog, opened
 *  from the card's menu ("Configurações do projeto"): name, client, client link,
 *  access and the client's email addresses, saved together by Salvar. The photo
 *  and archiving are in the menu itself (ProjectMenu). */
export function ProjectDialog({ project, onClose }: { project: ProjectSummary; onClose: () => void }) {
  const { t } = useTranslation();
  const change = useChangeProject();
  const [name, setName] = useState(project.name);
  const [client, setClient] = useState(project.client_name);
  // What the server has, so a retry after a failure doesn't resend (and conflict
  // with) a change that already went through.
  const [saved, setSaved] = useState(project);
  const [slug, setSlug] = useState(project.slug);
  const [access, setAccess] = useState(project.access_mode);
  const [password, setPassword] = useState("");
  // The client's addresses for email updates (A32): the whole list is sent.
  const [recipients, setRecipients] = useState(() => project.recipients.map((r) => r.email));
  const [newRecipient, setNewRecipient] = useState("");
  const unsubscribed = new Set(saved.recipients.filter((r) => !r.subscribed).map((r) => r.email));
  const saving = change.isPending;

  const save = async () => {
    try {
      const linkChanged = slug !== saved.slug;
      const accessChanged = access !== saved.access_mode || (access === "password" && password !== "");
      // An address typed but not added yet counts too: easy to forget "Adicionar".
      // One that isn't an address stops the save; the field says which.
      const { list: wanted, left } = addEmails(recipients, newRecipient, RECIPIENTS_MAX);
      if (left.length) {
        setRecipients(wanted);
        setNewRecipient(left.join(", "));
        return;
      }
      const recipientsChanged = !sameList(
        wanted,
        saved.recipients.map((r) => r.email),
      );
      if (
        name !== saved.name ||
        client !== saved.client_name ||
        linkChanged ||
        accessChanged ||
        recipientsChanged
      ) {
        setSaved(
          await change.mutateAsync({
            id: project.id,
            row_version: saved.row_version,
            name,
            client_name: client,
            ...(linkChanged ? { slug } : {}),
            ...(accessChanged ? { access_mode: access, ...(password ? { password } : {}) } : {}),
            ...(recipientsChanged ? { recipients: wanted } : {}),
          }),
        );
        setPassword("");
        // Saved now: keep it listed, so a retry doesn't remove it.
        setRecipients(wanted);
        setNewRecipient("");
      }
      toast(t("projectSettings.saved"));
      onClose();
    } catch {
      // Shown below.
    }
  };

  const error = change.error;
  const nameTaken =
    error instanceof ApiError && error.conflictName
      ? error.code === "project_name_taken"
        ? t("newProject.nameTakenBy", { name: error.conflictName })
        : error.code === "slug_taken"
          ? t("newProject.slugTakenBy", { name: error.conflictName })
          : null
      : null;
  return (
    <ModalOverlay className={styles.overlay} isDismissable isOpen onOpenChange={(open) => !open && onClose()}>
      <Modal className={styles.modal}>
        <Dialog className={styles.dialog}>
          <Heading slot="title" className={styles.dialogTitle}>
            {t("projectSettings.title")}
          </Heading>
          <CloseButton onPress={onClose} />
          <Form
            className={styles.form}
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <div className={styles.row2}>
              <TextField
                label={t("projectSettings.name")}
                value={name}
                onChange={setName}
                isRequired
                maxLength={NAME_MAX}
                autoComplete="off"
              />
              <TextField
                label={t("projectSettings.client")}
                value={client}
                onChange={setClient}
                isRequired
                maxLength={CLIENT_MAX}
                autoComplete="off"
              />
            </div>


            <TextField
              label={t("projectSettings.link")}
              description={t("projectSettings.linkHint", { address: `${window.location.host}/${slug || "…"}` })}
              value={slug}
              onChange={(value) => setSlug(value.toLowerCase())}
              isRequired
              maxLength={80}
              autoComplete="off"
              spellCheck="false"
            />
            <RadioGroup
              className={styles.types}
              value={access}
              onChange={(value) => setAccess(value as typeof access)}
            >
              <Label className={styles.label}>{t("projectSettings.access")}</Label>
              <Radio value="public" className={styles.choice}>
                <b>{t("projectSettings.public")}</b>
                <small className={styles.choiceNote}>{t("projectSettings.publicHint")}</small>
              </Radio>
              <Radio value="password" className={styles.choice}>
                <b>{t("projectSettings.withPassword")}</b>
                <small className={styles.choiceNote}>{t("projectSettings.withPasswordHint")}</small>
              </Radio>
            </RadioGroup>
            {access === "password" && (
              <TextField
                label={t("projectSettings.password")}
                description={
                  saved.access_mode === "password"
                    ? t("projectSettings.passwordKeep")
                    : t("projectSettings.passwordNew")
                }
                type="password"
                value={password}
                onChange={setPassword}
                isRequired={saved.access_mode !== "password"}
                minLength={6}
                autoComplete="new-password"
              />
            )}

            <EmailListField
              label={t("projectSettings.recipients")}
              description={t("projectSettings.recipientsHint")}
              emails={recipients}
              onChange={setRecipients}
              draft={newRecipient}
              onDraft={setNewRecipient}
              max={RECIPIENTS_MAX}
              // The client's choice: staff can't undo it (A32).
              locked={(email) => (unsubscribed.has(email) ? t("projectSettings.unsubscribed") : null)}
              addLabel={t("projectSettings.addRecipient")}
              newLabel={t("projectSettings.newRecipient")}
              removeLabel={(email) => t("projectSettings.removeRecipient", { email })}
            />

            {nameTaken ? (
              <p role="alert" className={styles.problem}>
                {nameTaken}
              </p>
            ) : (
              <ErrorNotice error={error} values={{ min: 6 }} />
            )}
            <div className={styles.actions}>
              <Button onPress={onClose}>{t("projectSettings.cancel")}</Button>
              <Button type="submit" variant="primary" isDisabled={saving}>
                {saving ? t("projectSettings.saving") : t("projectSettings.save")}
              </Button>
            </div>
          </Form>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
