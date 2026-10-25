import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import styles from "../pages/pages.module.css";
import { ErrorNotice } from "../ui/ErrorNotice";
import { useDrive } from "./drive";

/** Office-wide: the Drive connection expired, or its folder can't be read. (Not
 *  connected yet is the first of the painel's first steps; disconnected, the
 *  painel's empty state, not notices.) */
export function DriveNotice() {
  const { t } = useTranslation();
  const drive = useDrive();
  if (drive.error) return <ErrorNotice error={drive.error} />;
  const status = drive.data;
  if (!status || status.kind === "folder") return null;
  const expired = status.kind === "google" && status.writer_status === "expired";
  const missing = status.kind === null || status.writer_status === "none";
  const unreadable = status.kind === "google" && !missing && status.reader_status === "no_access";
  if (!expired && !unreadable) return null;
  const message = expired ? "drive.noticeExpired" : "drive.readerProblem";
  return (
    <div className={styles.notice} role="status">
      <p>{t(message)}</p>
      <Link className={styles.noticeAction} to="/configuracoes/drive">
        {t(expired ? "drive.reconnect" : "settings.drive")}
      </Link>
    </div>
  );
}
