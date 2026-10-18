import {
  Button,
  Dialog,
  DialogTrigger,
  Modal,
  ModalOverlay,
  Switch,
} from "react-aria-components";
import { useTranslation } from "react-i18next";

import { CloseButton } from "../ui/CloseButton";
import { useTheme } from "../ui/ThemeToggle";
import styles from "../pages/pages.module.css";

/** Phones: the top bar's ☰ opens a drawer from the right, full height: a
 *  greeting at the top, then the theme switch and Sair. (The sections are tabs
 *  under the bar; account settings may join this later.) */
export function MobileMenu({
  name,
  onSignOut,
  signingOut,
}: {
  name: string; // the staff member's, as entered
  onSignOut: () => void;
  signingOut: boolean;
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
                  <span className={styles.drawerGreeting}>
                    {t("nav.hello", { name: name.trim().split(/\s+/)[0] })}
                  </span>
                  <CloseButton onPress={close} />
                </div>
                <Switch
                  className={styles.switch}
                  isSelected={theme === "dark"}
                  onChange={(dark) => setTheme(dark ? "dark" : "light")}
                >
                  {t("theme.dark")}
                  <span className={styles.switchTrack} aria-hidden="true">
                    <span className={styles.switchThumb} />
                  </span>
                </Switch>
                <Button
                  className={styles.menuItem}
                  onPress={onSignOut}
                  isDisabled={signingOut}
                >
                  {t("nav.signOut")}
                </Button>
              </>
            )}
          </Dialog>
        </Modal>
      </ModalOverlay>
    </DialogTrigger>
  );
}
