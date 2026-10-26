import { Button, Dialog, DialogTrigger, Modal, ModalOverlay, Switch } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router";

import { EXAMPLE_SLUG } from "../client/example/address";
import { CloseButton } from "../ui/CloseButton";
import { ErrorNotice } from "../ui/ErrorNotice";
import { useTheme } from "../ui/theme";
import styles from "../pages/pages.module.css";

/** Phones: the top bar's ☰ opens a drawer from the right, full height: a
 *  greeting at the top, the painel's sections, then the theme switch, the
 *  painel's tour, the example project and Sair. */
export function MobileMenu({
  name,
  onSignOut,
  signingOut,
  signOutError,
  onTour,
}: {
  name: string; // the staff member's, as entered
  onSignOut: () => void;
  signingOut: boolean;
  signOutError: unknown; // shown here: the drawer covers the page's own notice
  onTour: () => void; // the painel's tour, once the drawer has gone
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
                <Button
                  className={styles.menuItem}
                  onPress={() => {
                    close();
                    onTour();
                  }}
                >
                  {t("painelTour.again")}
                </Button>
                <a className={styles.menuItem} href={`/${EXAMPLE_SLUG}`}>
                  {t("firstSteps.example")}
                </a>
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
