import { Button, Dialog, DialogTrigger, Modal, ModalOverlay, Switch } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router";

import { CloseButton } from "../ui/CloseButton";
import { ErrorNotice } from "../ui/ErrorNotice";
import { useTheme } from "../ui/ThemeToggle";
import styles from "../pages/pages.module.css";

/** Phones: the top bar's ☰ opens a drawer from the right, full height: a
 *  greeting at the top, the painel's sections, then the theme switch and Sair. */
export function MobileMenu({
  name,
  onSignOut,
  signingOut,
  signOutError,
}: {
  name: string; // the staff member's, as entered
  onSignOut: () => void;
  signingOut: boolean;
  signOutError: unknown; // shown here: the drawer covers the page's own notice
}) {
  const { t } = useTranslation();
  const [theme, setTheme] = useTheme();
  return (
    <DialogTrigger>
      <Button className={styles.menuButton} aria-label={t("nav.menu")}>
        <span aria-hidden="true" className={styles.burger} />
      </Button>
      <ModalOverlay className={styles.drawerOverlay} isDismissable>
        <Modal className={styles.drawer}>
          <Dialog className={styles.menuPanel} aria-label={t("nav.menu")}>
            {({ close }) => (
              <>
                <div className={styles.drawerHead}>
                  <span className={styles.drawerGreeting}>{t("nav.hello", { name: name.trim().split(/\s+/)[0] })}</span>
                  <CloseButton onPress={close} />
                </div>
                <nav className={styles.menuNav} aria-labelledby="menu-sections">
                  <h2 id="menu-sections" className={styles.menuLabel}>
                    {t("nav.sections")}
                  </h2>
                  <NavLink to="/" end onClick={close}>
                    {t("nav.projects")}
                  </NavLink>
                  <NavLink to="/configuracoes" onClick={close}>
                    {t("nav.settings")}
                  </NavLink>
                </nav>
                <Switch className={styles.switch} isSelected={theme === "dark"} onChange={(dark) => setTheme(dark ? "dark" : "light")}>
                  {t("theme.dark")}
                  <span className={styles.switchTrack} aria-hidden="true">
                    <span className={styles.switchThumb} />
                  </span>
                </Switch>
                <Button className={styles.menuItem} onPress={onSignOut} isDisabled={signingOut}>
                  {t("nav.signOut")}
                </Button>
                <ErrorNotice error={signOutError} />
              </>
            )}
          </Dialog>
        </Modal>
      </ModalOverlay>
    </DialogTrigger>
  );
}
