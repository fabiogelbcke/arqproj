import { useState, type KeyboardEvent, type MouseEvent } from "react";
import { Button, FieldError, Input, Label, Text, TextField as AriaTextField, type TextFieldProps } from "react-aria-components";
import { useTranslation } from "react-i18next";

import styles from "./ui.module.css";

// `description`: a hint under it; `errorMessage`: what to fix when `isInvalid`.
type Props = Omit<TextFieldProps, "type"> & { label: string; description?: string; errorMessage?: string };

/** Apple's systems show their own Caps Lock mark beside the cursor (macOS since
 *  Sonoma, iPadOS), so ours would be a second one; but on a Mac only Safari's
 *  fields get it: Chrome and Firefox draw their own and show none. iPhones and
 *  iPads (which say "Mac" too, with a touch screen) use Safari's engine in every
 *  browser. */
function systemShowsCapsLock() {
  if (/iPhone|iPad/.test(navigator.platform) || (/Mac/.test(navigator.platform) && navigator.maxTouchPoints > 1))
    return true;
  const ua = navigator.userAgent;
  return /Mac/.test(navigator.platform) && /Safari\//.test(ua) && !/Chrome|Chromium|Edg|OPR|Firefox/.test(ua);
}

/** A labelled password input with an eye button that shows the password as typed,
 *  and, unless the system shows its own, a mark in its right edge while Caps Lock is on
 *  (said to screen readers too). */
export function PasswordField({ label, description, errorMessage, ...props }: Props) {
  const { t } = useTranslation();
  const [shown, setShown] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  // The browser only tells Caps Lock's state with a key or click event.
  const readCapsLock = (event: KeyboardEvent | MouseEvent) =>
    setCapsLock(event.getModifierState("CapsLock") && !systemShowsCapsLock());
  return (
    <AriaTextField {...props} type={shown ? "text" : "password"} className={styles.field}>
      <Label className={styles.label}>{label}</Label>
      {/* Room in the input for the mark only while it shows, so the browser's own
          buttons there (Safari's passwords key) sit beside the eye. */}
      <div className={styles.password} data-caps-lock={capsLock || undefined}>
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
      {description && (
        <Text slot="description" className={styles.hint}>
          {description}
        </Text>
      )}
      <FieldError className={styles.fieldError}>{errorMessage}</FieldError>
    </AriaTextField>
  );
}
