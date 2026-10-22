import { useTranslation } from "react-i18next";

import { LIMITS } from "../api/limits";
import { EmailListField } from "../ui/EmailListField";

/** The client's addresses for email updates (A32), wherever they are edited:
 *  creation, the project's settings and the card's "Sem e-mail do cliente". */
export function RecipientsField({
  label,
  description,
  emails,
  onChange,
  draft,
  onDraft,
  unsubscribed,
  autoFocus,
  labelHidden,
}: {
  label: string;
  description?: string;
  emails: string[];
  onChange: (emails: string[]) => void;
  draft: string;
  onDraft: (draft: string) => void;
  unsubscribed?: Set<string>; // the client's choice: staff can't undo it (A32)
  autoFocus?: boolean;
  labelHidden?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <EmailListField
      label={label}
      description={description}
      emails={emails}
      onChange={onChange}
      draft={draft}
      onDraft={onDraft}
      max={LIMITS.recipients}
      locked={(email) => (unsubscribed?.has(email) ? t("projectSettings.unsubscribed") : null)}
      addLabel={t("projectSettings.addRecipient")}
      newLabel={t("projectSettings.newRecipient")}
      removeLabel={(email) => t("projectSettings.removeRecipient", { email })}
      autoFocus={autoFocus}
      labelHidden={labelHidden}
    />
  );
}
