import { Button, Menu, MenuItem, MenuSection, MenuTrigger, Popover, Separator } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { Avatar } from "../ui/Avatar";
import { useTheme } from "../ui/theme";
import styles from "../ui/ui.module.css";
import pageStyles from "../pages/pages.module.css";

/** The top bar's round initial (desktop): who is signed in, the dark theme, the
 *  painel's tour and Sair (painel redesign, 22 Oct 2026). Phones have the ☰
 *  drawer instead. */
export function AccountMenu({
  name,
  email,
  onSignOut,
  signingOut,
  onTour,
}: {
  name: string;
  email: string;
  onSignOut: () => void;
  signingOut: boolean;
  onTour: () => void;
}) {
  const { t } = useTranslation();
  const [theme, setTheme] = useTheme();
  return (
    <MenuTrigger>
      <Button className={pageStyles.account} aria-label={t("nav.account")}>
        <Avatar name={name} />
      </Button>
      <Popover className={styles.menuPopover} placement="bottom end" offset={8}>
        <div className={styles.menuHeader}>
          <strong>{name}</strong>
          <span>{email}</span>
        </div>
        <Menu
          className={styles.menu}
          aria-label={t("nav.account")}
          disabledKeys={signingOut ? ["signOut"] : []}
          onAction={(key) => (key === "signOut" ? onSignOut() : key === "tour" ? onTour() : undefined)}
        >
          <MenuSection
            selectionMode="multiple"
            selectedKeys={theme === "dark" ? ["dark"] : []}
            onSelectionChange={(keys) => setTheme(keys !== "all" && keys.has("dark") ? "dark" : "light")}
          >
            <MenuItem id="dark" className={styles.menuItem} shouldCloseOnSelect={false}>
              {t("theme.dark")}
              <span className={styles.menuSwitch} aria-hidden="true" />
            </MenuItem>
          </MenuSection>
          <Separator className={styles.menuSeparator} />
          <MenuSection>
            <MenuItem id="tour" className={styles.menuItem}>
              {t("painelTour.again")}
            </MenuItem>
            <MenuItem id="signOut" className={styles.menuItem}>
              {t("nav.signOut")}
            </MenuItem>
          </MenuSection>
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}
