import { useState, type KeyboardEvent, type MouseEvent } from "react";
import { Button, FieldError, Input, Label, TextField as AriaTextField, type TextFieldProps } from "react-aria-components";
import { useTranslation } from "react-i18next";

import styles from "./ui.module.css";

type Props = Omit<TextFieldProps, "type"> & { label: string };

/** A labelled password input with an eye button that shows the password as typed,
 *  and a mark in its right edge while Caps Lock is on (said to screen readers too). */
export function PasswordField({ label, ...props }: Props) {
  const { t } = useTranslation();
  const [shown, setShown] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  // The browser only tells Caps Lock's state with a key or click event.
  const readCapsLock = (event: KeyboardEvent | MouseEvent) => setCapsLock(event.getModifierState("CapsLock"));
  return (
    <AriaTextField {...props} type={shown ? "text" : "password"} className={styles.field}>
      <Label className={styles.label}>{label}</Label>
      <div className={styles.password}>
        <Input
          className={styles.input}
          onKeyDown={readCapsLock}
          onKeyUp={readCapsLock}
          onClick={readCapsLock}
          onBlur={() => setCapsLock(false)}
        />
        <span className={styles.passwordTools}>
          {capsLock && (
            <span className={styles.capsLock} title={t("signIn.capsLock")} data-testid="caps-lock">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <path d="M12 4 4 12h4v4h8v-4h4L12 4ZM8 20h8" strokeLinejoin="round" />
              </svg>
            </span>
          )}
          <Button
            className={styles.reveal}
            aria-label={t(shown ? "signIn.hidePassword" : "signIn.showPassword")}
            aria-pressed={shown}
            onPress={() => setShown(!shown)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
              <circle cx="12" cy="12" r="3" />
              {shown && <path d="M4 4l16 16" />}
            </svg>
          </Button>
        </span>
      </div>
      <span className="sr-only" role="status">
        {capsLock ? t("signIn.capsLock") : ""}
      </span>
      <FieldError className={styles.fieldError} />
    </AriaTextField>
  );
}
