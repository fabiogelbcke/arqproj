import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "./Button";
import { emailSuggestion, isEmail, splitEmails } from "./email";
import styles from "./ui.module.css";

/** Adds the addresses in `text` to `list`: each once, up to `max`. What can't be
 *  added comes back in `left`, to stay in the box: those that aren't addresses,
 *  and those past the maximum. A form saves only once nothing is left. */
export function addEmails(list: string[], text: string, max: number): { list: string[]; left: string[] } {
  const next = [...list];
  const left: string[] = [];
  for (const email of splitEmails(text)) {
    if (!isEmail(email) || (!next.includes(email) && next.length >= max)) left.push(email);
    else if (!next.includes(email)) next.push(email);
  }
  return { list: next, left };
}

type Props = {
  label: string;
  description?: string;
  emails: string[];
  onChange: (emails: string[]) => void;
  // What's typed and not added yet, held by the form so that saving can add it
  // too (it's easy to forget "Adicionar"): see addEmails.
  draft: string;
  onDraft: (draft: string) => void;
  max: number;
  // An address that can't be removed here, and why (the client unsubscribed).
  locked?: (email: string) => ReactNode | null;
  addLabel: string;
  newLabel: string;
  removeLabel: (email: string) => string;
};

/** Several email addresses, each a line that can be removed. Several can be typed
 *  or pasted at once (separated by commas, spaces or lines); Enter or a comma adds
 *  them. One that isn't an address stays in the box with a message, and a likely
 *  typo in a domain ("gmial.com") gets its fix offered, on the box and on a line. */
export function EmailListField({
  label,
  description,
  emails,
  onChange,
  draft,
  onDraft,
  max,
  locked,
  addLabel,
  newLabel,
  removeLabel,
}: Props) {
  const { t } = useTranslation();
  const id = useId();
  const add = (text = draft) => {
    const { list, left } = addEmails(emails, text, max);
    if (list.length !== emails.length) onChange(list);
    onDraft(left.join(", "));
  };
  const rejected = splitEmails(draft).filter((email) => !isEmail(email));
  // Full, with addresses still in the box: they'd be lost if the box went away.
  const tooMany = emails.length >= max && splitEmails(draft).some(isEmail);
  // A typed address waiting to be added: shown with its fix once it's complete.
  const typed = splitEmails(draft);
  const draftSuggestion = typed.length === 1 && isEmail(typed[0]!) ? emailSuggestion(typed[0]!) : null;
  const replace = (from: string, to: string) =>
    onChange(emails.includes(to) ? emails.filter((email) => email !== from) : emails.map((email) => (email === from ? to : email)));
  return (
    <fieldset className={styles.emailList}>
      <legend className={styles.label}>{label}</legend>
      {description && <p className={styles.hint}>{description}</p>}
      {emails.length > 0 && (
        <ul className={styles.emailListItems}>
          {emails.map((email) => {
            const note = locked?.(email);
            const fix = emailSuggestion(email);
            return (
              <li key={email} className={styles.emailListItem}>
                <span className={styles.emailListAddress}>
                  {email}
                  {fix && !note && (
                    <small className={styles.emailSuggestion}>
                      {t("emailField.didYouMean")}{" "}
                      <button type="button" onClick={() => replace(email, fix)}>
                        {fix}
                      </button>
                      ?
                    </small>
                  )}
                </span>
                {note ? (
                  <small className={styles.hint}>{note}</small>
                ) : (
                  <Button variant="ghost" size="small" aria-label={removeLabel(email)} onPress={() => onChange(emails.filter((other) => other !== email))}>
                    ×
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {(emails.length < max || draft.trim() !== "") && (
        <div className={styles.emailListAdd}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor={id}>
              {newLabel}
            </label>
            <input
              id={id}
              className={styles.input}
              type="text"
              inputMode="email"
              autoComplete="off"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              value={draft}
              aria-invalid={rejected.length > 0 || undefined}
              aria-describedby={rejected.length ? `${id}-error` : undefined}
              data-invalid={rejected.length > 0 || undefined}
              onChange={(event) => {
                const text = event.target.value;
                // A comma or semicolon ends an address: add what's before it.
                if (/[,;]\s*$/.test(text) && !/[,;]\s*$/.test(draft)) add(text);
                else onDraft(text);
              }}
              onPaste={(event) => {
                const pasted = event.clipboardData.getData("text");
                if (splitEmails(pasted).length > 1) {
                  event.preventDefault();
                  add(`${draft} ${pasted}`);
                }
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault(); // add it, don't send the form
                  add();
                }
              }}
            />
          </div>
          <Button onPress={() => add()} isDisabled={!draft.trim()}>
            {addLabel}
          </Button>
        </div>
      )}
      {rejected.length > 0 && (
        <p id={`${id}-error`} className={styles.fieldError} role="alert">
          {t("emailField.invalidSome", { count: rejected.length, emails: rejected.join(", ") })}
        </p>
      )}
      {tooMany && (
        <p className={styles.fieldError} role="alert">
          {t("emailField.tooMany", { max })}
        </p>
      )}
      {draftSuggestion && (
        <p className={styles.emailSuggestion} role="status">
          {t("emailField.didYouMean")}{" "}
          <button type="button" onClick={() => onDraft(draftSuggestion)}>
            {draftSuggestion}
          </button>
          ?
        </p>
      )}
    </fieldset>
  );
}
