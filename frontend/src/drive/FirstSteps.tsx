import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { useMe } from "../session/session";
import styles from "../pages/pages.module.css";
import { useOnboarding } from "./drive";

/** What a new office still has to do; gone once everything is done. */
export function FirstSteps() {
  const { t } = useTranslation();
  const onboarding = useOnboarding();
  const me = useMe();
  const steps = onboarding.data;
  if (!steps || (steps.storage_connected && steps.office_details && steps.has_project)) return null;
  const owner = me.data?.role === "owner";
  return (
    <section className={styles.steps} aria-labelledby="first-steps">
      <h2 id="first-steps">{t("firstSteps.title")}</h2>
      <ol>
        <li data-done={steps.storage_connected || undefined}>
          {steps.storage_connected || !owner ? (
            <span>{t("firstSteps.storage")}</span>
          ) : (
            <Link to="/configuracoes/drive">{t("firstSteps.storage")}</Link>
          )}
          {steps.storage_connected && <span className={styles.stepDone}>{t("firstSteps.done")}</span>}
        </li>
        <li data-done={steps.office_details || undefined}>
          {steps.office_details || !owner ? (
            <span>{t("firstSteps.office")}</span>
          ) : (
            <Link to="/configuracoes/escritorio">{t("firstSteps.office")}</Link>
          )}
          {steps.office_details && <span className={styles.stepDone}>{t("firstSteps.done")}</span>}
        </li>
        <li data-done={steps.has_project || undefined}>
          <span>{t("firstSteps.firstProject")}</span>
          <span className={styles.stepDone}>
            {steps.has_project ? t("firstSteps.done") : t("firstSteps.firstProjectSoon")}
          </span>
        </li>
      </ol>
      {!owner && <p className={styles.small}>{t("firstSteps.membersNote")}</p>}
    </section>
  );
}
