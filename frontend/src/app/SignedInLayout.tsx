import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { api, call } from "../api/client";
import { LogoPng, useOffice } from "../office/office";
import { useMe, useSignedOut } from "../session/session";
import { ErrorNotice } from "../ui/ErrorNotice";
import { HeaderMenu } from "../ui/HeaderMenu";
import { OfficeBrand } from "../ui/OfficeBrand";
import { IconButton } from "../ui/IconButton";
import styles from "../pages/pages.module.css";
import { MobileMenu } from "./MobileMenu";

/** Every screen behind sign-in: the top bar, or a redirect to sign-in. */
export function SignedInLayout() {
  const { t } = useTranslation();
  const me = useMe();
  const office = useOffice(); // the logo, once uploaded (Configurações → Escritório)
  const location = useLocation();
  const signedOut = useSignedOut();
  const navigate = useNavigate();
  const signOut = useMutation({
    mutationFn: () => call(api.DELETE("/api/session")),
    onSuccess: () => {
      signedOut();
      navigate("/entrar", { replace: true });
    },
  });

  // The painel's tour, on demand only (plan section 16): from "?" and the menus. Loaded when asked for.
  const startTour = () => void import("./PainelTour").then(({ startPainelTour }) => startPainelTour({ t }));

  if (me.isPending) return <p className={styles.centered}>{t("app.loading")}</p>;
  if (me.error) return <main className={styles.centered}><ErrorNotice error={me.error} /></main>;
  if (!me.data) {
    const next = location.pathname + location.search;
    return <Navigate to={`/entrar?next=${encodeURIComponent(next)}`} replace />;
  }
  return (
    <>
      {/* Keyboard users: past the top bar in one step (WCAG 2.4.1). Shown on focus. */}
      <a className={styles.skipLink} href="#content">
        {t("nav.skipToContent")}
      </a>
      <header className={styles.topbar}>
        <div className={styles.topbarIn}>
          {/* The office's mark (its logo carries the name): always the way back to the projects. */}
          <Link className={styles.brand} to="/" title={t("page.backToPainel")}>
            <OfficeBrand name={me.data.tenant_name} logo={office.data?.logo_url} logoDark={office.data?.logo_dark_url} />
          </Link>
          <nav className={`${styles.nav} ${styles.navInMenu}`} aria-label={t("app.name")}>
            <NavLink to="/" end>
              {t("nav.projects")}
            </NavLink>
            <NavLink to="/configuracoes" data-tour="settings">
              {t("nav.settings")}
            </NavLink>
          </nav>
          <IconButton className={styles.help} label={t("painelTour.again")} onPress={startTour}>
            ?
          </IconButton>
          <div className={styles.barActions}>
            <HeaderMenu
              person={me.data}
              onSignOut={() => signOut.mutate()}
              signingOut={signOut.isPending}
              onTour={startTour}
            />
          </div>
          <MobileMenu
            name={me.data.name}
            onSignOut={() => signOut.mutate()}
            signingOut={signOut.isPending}
            signOutError={signOut.error}
            onTour={startTour}
          />
        </div>
      </header>
      <main id="content" tabIndex={-1} className={styles.main}>
        <ErrorNotice error={signOut.error} />
        <Outlet />
      </main>
      <LogoPng />
    </>
  );
}
