import { useTranslation } from "react-i18next";

import unio from "../assets/unio.png";
import unioDark from "../assets/unio-dark.png";
import styles from "./ui.module.css";

/** Unio's logo, dark letters or (dark theme) light ones; its height comes from
 *  where it sits (`className` sizes `img`). */
export function UnioMark({ className }: { className?: string }) {
  return (
    <span className={[styles.unioMark, className].filter(Boolean).join(" ")}>
      <img className={styles.unioLight} src={unio} alt="Unio" />
      <img className={styles.unioDark} src={unioDark} alt="Unio" />
    </span>
  );
}

/** At the foot of the painel and of a project's page, like Unio's landing page:
 *  its logo, line and legal pages on the left; the office's name on its own on
 *  the right, so the legal pages don't read as the office's (Fabio, 26 Oct 2026). */
export function SiteFooter({ office, className }: { office?: string; className?: string }) {
  const { t } = useTranslation();
  return (
    <footer className={[styles.siteFooter, className].filter(Boolean).join(" ")}>
      <div className={styles.siteFooterBrand}>
        <a href="https://myunio.app/">
          <UnioMark />
        </a>
        <p>{t("footer.tagline")}</p>
        <nav aria-label={t("footer.links")}>
          <a href="/privacidade">{t("footer.privacy")}</a>
          <a href="/termos">{t("footer.terms")}</a>
        </nav>
      </div>
      {office && <span className={styles.siteFooterOffice}>{office}</span>}
    </footer>
  );
}
