import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import styles from "../pages/pages.module.css";
import { useDrive } from "./drive";

/** Office-wide: Drive not connected yet, or the connection expired. */
export function DriveNotice() {
  const { t } = useTranslation();
  const drive = useDrive();
  const status = drive.data;
  if (!status || status.kind === "folder") return null;
  const expired = status.kind === "google" && status.writer_status === "expired";
  const missing = status.kind === null || status.writer_status === "none";
  if (!expired && !missing) return null;
  return (
    <div className={styles.notice} role="status">
      <p>{t(expired ? "drive.noticeExpired" : "drive.noticeNone")}</p>
      <Link className={styles.noticeAction} to="/configuracoes/drive">
        {t(expired ? "drive.reconnect" : "drive.connect")}
      </Link>
    </div>
  );
}
