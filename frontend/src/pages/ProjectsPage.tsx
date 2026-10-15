import { useTranslation } from "react-i18next";

import styles from "./pages.module.css";

export function ProjectsPage() {
  const { t } = useTranslation();
  return (
    <>
      <h1 className={styles.display}>{t("projects.title")}</h1>
      <section className={styles.empty} aria-labelledby="projects-empty">
        <h2 id="projects-empty">{t("projects.emptyTitle")}</h2>
        <p>{t("projects.emptyBody")}</p>
      </section>
    </>
  );
}
