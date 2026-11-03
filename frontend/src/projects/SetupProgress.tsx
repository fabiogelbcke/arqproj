import { useTranslation } from "react-i18next";

import styles from "./projects.module.css";
import { SETUP_STEPS } from "./setup";

/** "Passo 2 de 3", with a bar of the steps done and the one under way; the
 *  dialog's title names the step. */
export function SetupProgress({ step }: { step: number }) {
  const { t } = useTranslation();
  const label = t("setup.progress", { n: step + 1, total: SETUP_STEPS.length });
  return (
    <div className={styles.setupProgress}>
      <div
        className={styles.setupBar}
        role="progressbar"
        aria-label={label}
        aria-valuemin={1}
        aria-valuemax={SETUP_STEPS.length}
        aria-valuenow={step + 1}
      >
        {SETUP_STEPS.map((name, i) => (
          <span key={name} data-state={i <= step ? "done" : "next"} />
        ))}
      </div>
      <p className={styles.note}>{label}</p>
    </div>
  );
}
