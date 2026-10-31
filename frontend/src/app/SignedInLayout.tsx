import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { api, call } from "../api/client";
import { LogoPng, useOffice } from "../office/office";
import { ConfirmEmailPage } from "../pages/ConfirmEmailPage";
import { useMe, useSignedOut } from "../session/session";
import { ErrorNotice } from "../ui/ErrorNotice";
import { EXAMPLE_SLUG } from "../client/example/address";
import { HeaderMenu } from "../ui/HeaderMenu";
import { OfficeBrand } from "../ui/OfficeBrand";
import { SiteFooter } from "../ui/UnioMark";
import styles from "../pages/pages.module.css";
import { MobileMenu } from "./MobileMenu";

/** Every screen behind sign-in: the top bar, or a redirect to sign-in; until
 *  someone who joined by the shared link confirms their email, only that. */
export function SignedInLayout() {
  const me = useMe();
  if (me.data?.email_confirmed === false) return <ConfirmEmailPage me={me.data} />;
  return <Painel />;
}

function Painel() {
  const { t, i18n } = useTranslation();
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

  // The painel's tour, on demand only (plan section 16): from the account menu and the phone's drawer. Loaded when asked for.
  // Proposals have their own tab, where switched on (A40, A42).
  const proposals = me.data?.features.includes("proposals") ?? false;
  // An operator in a support session (A43): until when, in the viewer's own time.
  const support = me.data?.support_until
    ? new Date(me.data.support_until).toLocaleTimeString(i18n.language, { hour: "2-digit", minute: "2-digit" })
    : null;
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
            {proposals && <NavLink to="/propostas">{t("nav.proposals")}</NavLink>}
            <NavLink to="/configuracoes" data-tour="settings">
              {t("nav.settings")}
            </NavLink>
          </nav>
          <div className={styles.barActions}>
            <HeaderMenu
              person={me.data}
              // Suporte Unio's own details belong to no one (A43).
              onAccount={support ? undefined : () => void navigate("/conta")}
              onSignOut={() => signOut.mutate()}
              signingOut={signOut.isPending}
              onTour={startTour}
              example={`/${EXAMPLE_SLUG}`}
            />
          </div>
          <MobileMenu
            name={me.data.name}
            onSignOut={() => signOut.mutate()}
            signingOut={signOut.isPending}
            signOutError={signOut.error}
            onTour={startTour}
            account={!support}
          />
        </div>
      </header>
      {support && (
        <p className={styles.supportBanner} role="status">
          {t("support.banner", { time: support })}
          <button type="button" onClick={() => signOut.mutate()} disabled={signOut.isPending}>
            {t("support.leave")}
          </button>
        </p>
      )}
      <main id="content" tabIndex={-1} className={styles.main}>
        <ErrorNotice error={signOut.error} />
        <Outlet />
        <SiteFooter office={me.data.tenant_name} className={styles.footer} />
      </main>
      <LogoPng />
    </>
  );
}
