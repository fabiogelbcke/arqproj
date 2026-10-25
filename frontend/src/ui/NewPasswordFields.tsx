import { useTranslation } from "react-i18next";

import { TextField } from "./TextField";

export const MIN_PASSWORD_LENGTH = 8; // backend.identity.accounts; the server checks it too

/** A new password and its repetition, as chosen from an invite or reset link and
 *  when joining through the office's shared link. */
export function NewPasswordFields({ password, onChange }: { password: string; onChange: (value: string) => void }) {
  const { t } = useTranslation();
  return (
    <>
      <TextField
        name="password"
        type="password"
        autoComplete="new-password"
        isRequired
        minLength={MIN_PASSWORD_LENGTH}
        value={password}
        onChange={onChange}
        label={t("choosePassword.password")}
        description={t("choosePassword.passwordHint", { min: MIN_PASSWORD_LENGTH })}
      />
      <TextField
        name="confirm"
        type="password"
        autoComplete="new-password"
        isRequired
        validate={(value) => (value && value !== password ? t("choosePassword.mismatch") : null)}
        label={t("choosePassword.confirm")}
      />
    </>
  );
}
