import { Button, Menu, MenuItem, MenuSection, MenuTrigger, Popover, Separator } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { Avatar } from "./Avatar";
import { useTheme } from "./theme";
import styles from "./ui.module.css";

/** The header's menu, the same on the painel and the project pages (Fabio, 22 Oct
 *  2026): who is signed in (their initial on the button), "Modo escuro", the
 *  page's tour, on the painel the example project (moved from the projects page,
 *  Fabio, 26 Oct 2026), and Sair. A client, signed out, gets the same menu with only
 *  "Modo escuro", behind a ☰. */
export function HeaderMenu({
  person,
  onTour,
  tourLabel,
  example,
  onSignOut,
  signingOut = false,
}: {
  person?: { name: string; email: string } | null;
  onTour?: () => void;
  example?: string; // the example project's address (the painel), beside its tour
  tourLabel?: string; // the page's own tour: "Ver o tour do painel" by default
  onSignOut?: () => void;
  signingOut?: boolean;
}) {
  const { t } = useTranslation();
  const [theme, setTheme] = useTheme();
  const label = person ? t("nav.account") : t("nav.menu");
  return (
    <MenuTrigger>
      <Button className={styles.headerMenuButton} aria-label={label}>
        {person ? <Avatar name={person.name} /> : <span className={styles.burger} aria-hidden="true" />}
      </Button>
      <Popover className={styles.menuPopover} placement="bottom end" offset={8}>
        {person && (
          <div className={styles.menuHeader}>
            <strong>{person.name}</strong>
            <span>{person.email}</span>
          </div>
        )}
        <Menu
          className={styles.menu}
          aria-label={label}
          disabledKeys={signingOut ? ["signOut"] : []}
          onAction={(key) => (key === "signOut" ? onSignOut?.() : key === "tour" ? onTour?.() : undefined)}
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
          {(onTour || example || onSignOut) && (
            <>
              <Separator className={styles.menuSeparator} />
              <MenuSection>
                {onTour ? (
                  <MenuItem id="tour" className={styles.menuItem}>
                    {tourLabel ?? t("painelTour.again")}
                  </MenuItem>
                ) : null}
                {example ? (
                  <MenuItem id="example" href={example} className={styles.menuItem}>
                    {t("firstSteps.example")}
                  </MenuItem>
                ) : null}
                {onSignOut ? (
                  <MenuItem id="signOut" className={styles.menuItem}>
                    {t("nav.signOut")}
                  </MenuItem>
                ) : null}
              </MenuSection>
            </>
          )}
        </Menu>
      </Popover>
    </MenuTrigger>
  );
}
