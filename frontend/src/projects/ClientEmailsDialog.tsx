import { useState } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { LIMITS } from "../api/limits";
import { Button } from "../ui/Button";
import { DialogFrame } from "../ui/DialogFrame";
import { addEmails } from "../ui/EmailListField";
import { ErrorNotice } from "../ui/ErrorNotice";
import { toast } from "../ui/Toast";
import { useChangeProject, type ProjectSummary } from "./projects";
import styles from "./projects.module.css";
import { RecipientsField } from "./RecipientsField";

/** The card's "Sem e-mail do cliente → Adicionar" (A32): only the client's
 *  addresses, so adding one is quick. The other settings stay in the Projeto
 *  dialog (ProjectDialog), which edits the same list. */
export function ClientEmailsDialog({ project, onClose }: { project: ProjectSummary; onClose: () => void }) {
  const { t } = useTranslation();
  const change = useChangeProject();
  const [recipients, setRecipients] = useState(() => project.recipients.map((r) => r.email));
  const [draft, setDraft] = useState("");
  const unsubscribed = new Set(project.recipients.filter((r) => !r.subscribed).map((r) => r.email));

  const save = () => {
    // An address typed but not added yet counts too; one that isn't an address
    // stops the save, and the field says which.
    const { list, left } = addEmails(recipients, draft, LIMITS.recipients);
    setRecipients(list);
    setDraft(left.join(", "));
    if (left.length) return;
    change.mutate(
      { id: project.id, row_version: project.row_version, recipients: list },
      {
        onSuccess: () => {
          toast(t("clientEmails.saved"));
          onClose();
        },
      },
    );
  };

  return (
    <DialogFrame title={t("clientEmails.title")} onClose={onClose}>
      <Form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          save();
        }}
      >
        <p className={styles.note}>{t("clientEmails.intro", { name: project.name })}</p>
        <RecipientsField
          label={t("projectSettings.recipients")}
          emails={recipients}
          onChange={setRecipients}
          draft={draft}
          onDraft={setDraft}
          unsubscribed={unsubscribed}
          autoFocus
          labelHidden
        />
        <ErrorNotice error={change.error} />
        <div className={styles.actions}>
          <Button onPress={onClose}>{t("projectSettings.cancel")}</Button>
          <Button type="submit" variant="primary" isDisabled={change.isPending}>
            {change.isPending ? t("projectSettings.saving") : t("projectSettings.save")}
          </Button>
        </div>
      </Form>
    </DialogFrame>
  );
}
