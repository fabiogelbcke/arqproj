import { useLayoutEffect, useRef, useState } from "react";
import { FieldError, Input, Label, Text, TextField as AriaTextField } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { emailSuggestion, isEmail, tidyEmail } from "./email";
import styles from "./ui.module.css";

type Props = {
  label: string;
  description?: string;
  name?: string; // for a form read with FormData
  value?: string; // controlled; otherwise it keeps its own
  onChange?: (value: string) => void;
  isRequired?: boolean;
  isReadOnly?: boolean;
  autoFocus?: boolean;
  autoComplete?: string; // "username" on sign-in screens, so password managers fill it
};

/** One email address. It tidies what's typed when the field is left (spaces,
 *  capitals), says right away when it isn't an address, and offers the likely
 *  intended one for a typo in the domain ("Você quis dizer ana@gmail.com?").
 *  A form can't be sent with an address that isn't one. */
export function EmailField({ label, description, name, value, onChange, isRequired, isReadOnly, autoFocus, autoComplete = "email" }: Props) {
  const { t } = useTranslation();
  const [own, setOwn] = useState("");
  const current = value ?? own;
  const set = (next: string) => (onChange ? onChange(next) : setOwn(next));
  // Checked once the field is left, not at each letter typed.
  const [left, setLeft] = useState(false);
  const email = tidyEmail(current);
  const bad = email !== "" && !isEmail(email);
  const suggestion = left && isEmail(email) ? emailSuggestion(email) : null;
  // The browser's own check, so a form isn't sent with a bad address even when
  // Enter sends it before the field is left; its "invalid" shows our message.
  const input = useRef<HTMLInputElement>(null);
  useLayoutEffect(() => input.current?.setCustomValidity(bad ? t("emailField.invalid") : ""));
  return (
    <div className={styles.emailField}>
      <AriaTextField
        className={styles.field}
        name={name}
        value={current}
        onChange={(next) => {
          set(next);
          if (left && isEmail(tidyEmail(next))) setLeft(false); // fixed: no message while typing
        }}
        onBlur={() => {
          setLeft(true);
          if (current !== email) set(email);
        }}
        isRequired={isRequired}
        isReadOnly={isReadOnly}
        autoFocus={autoFocus}
        // Text with an email keyboard: the browser's own email check would show its
        // own message, in the browser's language, instead of ours.
        type="text"
        inputMode="email"
        autoComplete={autoComplete}
        spellCheck="false"
        // Shown once the field is left or the form sent, gone as soon as it's fixed.
        // "aria": the library leaves the browser's check to the effect above.
        validationBehavior="aria"
        isInvalid={left && bad}
      >
        <Label className={styles.label}>{label}</Label>
        <Input
          ref={input}
          className={styles.input}
          autoCapitalize="none"
          autoCorrect="off"
          onInvalid={(event) => {
            event.preventDefault(); // our message, not the browser's bubble
            setLeft(true);
          }}
        />
        {description && (
          <Text slot="description" className={styles.hint}>
            {description}
          </Text>
        )}
        <FieldError className={styles.fieldError}>{t("emailField.invalid")}</FieldError>
      </AriaTextField>
      {suggestion && !isReadOnly && (
        <p className={styles.emailSuggestion} role="status">
          {t("emailField.didYouMean")}{" "}
          <button type="button" onClick={() => set(suggestion)}>
            {suggestion}
          </button>
          ?
        </p>
      )}
    </div>
  );
}
