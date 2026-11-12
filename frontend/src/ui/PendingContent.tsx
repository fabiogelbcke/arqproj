import type { ReactNode } from "react";
import { ProgressBar } from "react-aria-components";
import { useTranslation } from "react-i18next";

import styles from "./ui.module.css";

/** A button's content while its action runs (a save, a removal): a spinner in
 *  the label's place. The label stays, unseen, as the button's name and width,
 *  so nothing moves. `Button pending` uses it; the client page's plain `.b`
 *  buttons wrap their label in it too. Uploads show a ProgressBar instead,
 *  which says how far they've got. */
export function PendingContent({ pending, children }: { pending: boolean; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <span className={styles.pendingContent}>
      <span className={pending ? styles.pendingLabel : undefined}>{children}</span>
      {pending && <ProgressBar isIndeterminate aria-label={t("app.working")} className={styles.spinner} />}
    </span>
  );
}
