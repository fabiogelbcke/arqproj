import i18next from "i18next";
import { useTranslation } from "react-i18next";

import { ApiError } from "../api/client";
import styles from "./ui.module.css";

const asApiError = (error: unknown) => (error instanceof ApiError ? error : new ApiError("unexpected"));

/** A failed request's message in the user's language (never the server's own text). */
function messageOf(error: ApiError, values?: Record<string, unknown>): string {
  const key = `errors.${error.code}`;
  return i18next.exists(key) ? i18next.t(key, values) : i18next.t("errors.unexpected");
}

/** The message and the support reference on one line, for a toast or a row. */
export function errorMessage(failure: unknown, values?: Record<string, unknown>): string {
  const error = asApiError(failure);
  const message = messageOf(error, values);
  return error.requestId ? `${message} ${i18next.t("errors.reference", { id: error.requestId })}` : message;
}

/** A failed request, in the user's language, with the support reference. */
export function ErrorNotice({ error, values }: { error: unknown; values?: Record<string, unknown> }) {
  const { t } = useTranslation(); // re-renders when the language changes
  if (!error) return null;
  const apiError = asApiError(error);
  return (
    <div role="alert" className={styles.notice}>
      <p>{messageOf(apiError, values)}</p>
      {apiError.requestId && <p className={styles.reference}>{t("errors.reference", { id: apiError.requestId })}</p>}
    </div>
  );
}
