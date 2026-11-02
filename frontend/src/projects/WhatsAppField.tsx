import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { LIMITS } from "../api/limits";
import type { components } from "../api/schema";
import { Button } from "../ui/Button";
import { formatPhone, parsePhone } from "../ui/phone";
import styles from "../ui/ui.module.css";

type State = components["schemas"]["WhatsAppState"];

const STATE_LABEL: Record<State, string> = {
  invited: "projectSettings.whatsappInvited",
  subscribed: "projectSettings.whatsappSubscribed",
  declined: "projectSettings.whatsappDeclined",
  stopped: "projectSettings.whatsappStopped",
  unreachable: "projectSettings.whatsappUnreachable",
};

/** Adds the number typed in `draft` to `list`: once, up to the maximum. What
 *  isn't a mobile number stays in the box (`left`); a form saves only once
 *  nothing is left. */
export function addPhone(list: string[], draft: string): { list: string[]; left: string } {
  if (!draft.trim()) return { list, left: "" };
  const phone = parsePhone(draft);
  if (!phone || (!list.includes(phone) && list.length >= LIMITS.recipients)) return { list, left: draft };
  return { list: list.includes(phone) ? list : [...list, phone], left: "" };
}

/** The client's WhatsApp numbers (A44), each with where it stands. Staff add one
 *  and the client is asked; one that answered "Não quero" stays listed, without a
 *  remove button, so it is never asked again. */
export function WhatsAppField({
  phones,
  onChange,
  draft,
  onDraft,
  states,
  checked,
}: {
  phones: string[]; // international digits
  onChange: (phones: string[]) => void;
  draft: string;
  onDraft: (draft: string) => void;
  states: Map<string, State>; // as saved; a number added since has none yet
  checked?: boolean; // the form's save found the box isn't a number: say so
}) {
  const { t } = useTranslation();
  const id = useId();
  // Said once an add (or the form's save) found what's typed isn't a number, not
  // while it is still being typed.
  const [tried, setTried] = useState(false);
  const add = () => {
    const { list, left } = addPhone(phones, draft);
    if (list !== phones) onChange(list);
    onDraft(left);
    setTried(left !== "");
  };
  const invalid = (tried || checked) && draft.trim() !== "" && parsePhone(draft) === null;
  return (
    <fieldset className={styles.emailList}>
      <legend className={styles.label}>{t("projectSettings.whatsapp")}</legend>
      <p className={styles.hint}>{t("projectSettings.whatsappHint")}</p>
      {phones.length > 0 && (
        <ul className={styles.emailListItems}>
          {phones.map((phone) => {
            const state = states.get(phone);
            return (
              <li key={phone} className={styles.emailListItem}>
                <span className={styles.emailListAddress}>
                  {formatPhone(phone)}
                  {state && <small className={styles.hint}>{t(STATE_LABEL[state])}</small>}
                </span>
                {state !== "declined" && (
                  <Button
                    variant="ghost"
                    size="small"
                    aria-label={t("projectSettings.removeWhatsapp", { phone: formatPhone(phone) })}
                    onPress={() => onChange(phones.filter((other) => other !== phone))}
                  >
                    ×
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {(phones.length < LIMITS.recipients || draft.trim() !== "") && (
        <div className={styles.emailListAdd}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor={id}>
              {t("projectSettings.newWhatsapp")}
            </label>
            <input
              id={id}
              className={styles.input}
              type="tel"
              inputMode="tel"
              autoComplete="off"
              maxLength={LIMITS.phone}
              placeholder={t("subscribe.whatsappPlaceholder")}
              value={draft}
              aria-invalid={invalid || undefined}
              aria-describedby={invalid ? `${id}-error` : undefined}
              data-invalid={invalid || undefined}
              onChange={(event) => {
                setTried(false);
                onDraft(event.target.value);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault(); // add it, don't send the form
                  add();
                }
              }}
            />
          </div>
          <Button onPress={add} isDisabled={!draft.trim()}>
            {t("projectSettings.addWhatsapp")}
          </Button>
        </div>
      )}
      {invalid && (
        <p id={`${id}-error`} className={styles.fieldError} role="alert">
          {t("projectSettings.whatsappInvalid")}
        </p>
      )}
    </fieldset>
  );
}
