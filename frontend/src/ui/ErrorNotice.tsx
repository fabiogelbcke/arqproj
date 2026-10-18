import { useTranslation } from "react-i18next";

import { ApiError } from "../api/client";
import styles from "./ui.module.css";

/** A failed request, in the user's language, with the support reference. */
export function ErrorNotice({ error, values }: { error: unknown; values?: Record<string, unknown> }) {
  const { t, i18n } = useTranslation();
  if (!error) return null;
  const apiError = error instanceof ApiError ? error : new ApiError("unexpected");
  const key = `errors.${apiError.code}`;
  return (
    <div role="alert" className={styles.notice}>
      <p>{i18n.exists(key) ? t(key, values) : t("errors.unexpected")}</p>
      {apiError.requestId && <p className={styles.reference}>{t("errors.reference", { id: apiError.requestId })}</p>}
    </div>
  );
}
