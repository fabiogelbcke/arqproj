import { useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";

import { newVersionStore } from "../app/version";
import { Button } from "./Button";
import styles from "./ui.module.css";

export function UpdateBanner() {
  const { t } = useTranslation();
  const available = useSyncExternalStore(newVersionStore.subscribe, newVersionStore.snapshot);
  if (!available) return null;
  return (
    <div role="status" className={styles.banner}>
      <span>{t("update.available")}</span>
      <Button variant="primary" onPress={() => window.location.reload()}>
        {t("update.reload")}
      </Button>
    </div>
  );
}
