import { useTranslation } from "react-i18next";

import { Button } from "./Button";
import styles from "./ui.module.css";

/** The × in a dialog's top corner. Escape and a click outside close it too. */
export function CloseButton({ onPress }: { onPress: () => void }) {
  const { t } = useTranslation();
  return (
    <Button variant="ghost" className={styles.close} aria-label={t("app.close")} onPress={onPress}>
      <span aria-hidden="true">×</span>
    </Button>
  );
}
