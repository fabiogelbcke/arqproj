import { useTranslation } from "react-i18next";

import { DriveNotice } from "../drive/DriveNotice";
import { FirstSteps } from "../drive/FirstSteps";

import styles from "./pages.module.css";

export function ProjectsPage() {
  const { t } = useTranslation();
  return (
    <>
      <h1 className={styles.display}>{t("projects.title")}</h1>
      <DriveNotice />
      <FirstSteps />
      <section className={styles.empty} aria-labelledby="projects-empty">
        <h2 id="projects-empty">{t("projects.emptyTitle")}</h2>
        <p>{t("projects.emptyBody")}</p>
      </section>
    </>
  );
}
