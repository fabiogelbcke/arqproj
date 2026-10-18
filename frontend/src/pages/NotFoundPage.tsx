import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import styles from "./pages.module.css";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <>
      <h1 className={`${styles.display} ${styles.displayMedium}`}>{t("notFound.title")}</h1>
      <Link to="/">{t("notFound.back")}</Link>
    </>
  );
}
