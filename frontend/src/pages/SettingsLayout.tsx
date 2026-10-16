import { useTranslation } from "react-i18next";
import { NavLink, Outlet } from "react-router";

import styles from "./pages.module.css";

export function SettingsLayout() {
  const { t } = useTranslation();
  return (
    <>
      <h1 className={styles.display}>{t("settings.title")}</h1>
      <nav className={styles.subnav} aria-label={t("settings.title")}>
        <NavLink to="/configuracoes/escritorio">{t("settings.office")}</NavLink>
        <NavLink to="/configuracoes/drive">{t("settings.drive")}</NavLink>
      </nav>
      <Outlet />
    </>
  );
}
