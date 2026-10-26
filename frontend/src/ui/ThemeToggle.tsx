import { Switch } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { useTheme } from "./theme";
import styles from "./ui.module.css";

/** "Modo escuro" with a switch, on its own in the header: for visitors who aren't
 *  signed in, a menu holding only this one choice would be a ☰ for nothing
 *  (Fabio, 26 Oct 2026). On phones the words give way to a moon. */
export function ThemeToggle() {
  const { t } = useTranslation();
  const [theme, setTheme] = useTheme();
  return (
    <Switch
      className={styles.themeToggle}
      isSelected={theme === "dark"}
      onChange={(dark) => setTheme(dark ? "dark" : "light")}
      aria-label={t("theme.dark")}
    >
      <svg className={styles.themeToggleMoon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" strokeLinejoin="round" />
      </svg>
      <span className={styles.themeToggleLabel}>{t("theme.dark")}</span>
      <span className={styles.menuSwitch} aria-hidden="true" />
    </Switch>
  );
}
