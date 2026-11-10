import { useTranslation } from "react-i18next";

import { IconButton } from "./IconButton";
import styles from "./ui.module.css";

/** The × in a dialog's top corner. Escape and a click outside close it too. */
export function CloseButton({ onPress, isDisabled }: { onPress: () => void; isDisabled?: boolean }) {
  const { t } = useTranslation();
  return (
    <IconButton className={styles.close} label={t("app.close")} onPress={onPress} isDisabled={isDisabled}>
      <span aria-hidden="true">×</span>
    </IconButton>
  );
}
