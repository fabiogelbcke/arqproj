import { useTranslation } from "react-i18next";

import unio from "../assets/unio.png";
import unioDark from "../assets/unio-dark.png";
import { useTenant } from "../session/session";
import { OfficeLogo } from "../ui/OfficeLogo";
import styles from "./pages.module.css";

/** Above the sign-in and password screens: Unio × the office being entered, so
 *  people see whose panel this is (its logo, or its name without one). */
export function AuthBrand() {
  const { t } = useTranslation();
  const tenant = useTenant();
  const office = tenant.data;
  return (
    <div className={styles.authBrand}>
      <span className={styles.unio}>
        <img className={styles.unioLight} src={unio} alt="Unio" />
        <img className={styles.unioDark} src={unioDark} alt="Unio" />
      </span>
      {office && (
        <>
          <span className={styles.authJoin} aria-label={t("signIn.with")}>
            ×
          </span>
          {office.logo_url ? (
            <OfficeLogo light={office.logo_url} dark={office.logo_dark_url} alt={office.name} />
          ) : (
            // Its name instead, about as tall as Unio's: smaller as it gets longer,
            // at most two lines (office names have at most 28 characters).
            <span className={styles.authOffice} data-length={nameLength(office.name)}>
              {office.name}
            </span>
          )}
        </>
      )}
    </div>
  );
}

function nameLength(name: string): "short" | "long" | "longer" {
  const length = name.trim().length;
  return length <= 12 ? "short" : length <= 20 ? "long" : "longer";
}
