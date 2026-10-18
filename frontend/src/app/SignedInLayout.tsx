import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { api, call } from "../api/client";
import { LogoPng, useOffice } from "../office/office";
import { useMe, useSignedOut } from "../session/session";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { ThemeToggle } from "../ui/ThemeToggle";
import styles from "../pages/pages.module.css";

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

  if (me.isPending) return <p className={styles.centered}>{t("app.loading")}</p>;
  if (me.error) return <main className={styles.centered}><ErrorNotice error={me.error} /></main>;
  if (!me.data) {
    const next = location.pathname + location.search;
    return <Navigate to={`/entrar?next=${encodeURIComponent(next)}`} replace />;
  }
  return (
    <>
      <header className={styles.topbar}>
        <div className={styles.topbarIn}>
          {/* A logo usually carries the name already, so it replaces it. */}
          <span className={styles.brand}>
            {office.data?.logo_url ? (
              <img src={office.data.logo_url} alt={me.data.tenant_name} />
            ) : (
              me.data.tenant_name
            )}
          </span>
          <nav className={styles.nav} aria-label={t("app.name")}>
            <NavLink to="/" end>
              {t("nav.projects")}
            </NavLink>
            <NavLink to="/configuracoes">{t("nav.settings")}</NavLink>
          </nav>
          <span className={styles.spacer} />
          <span className={styles.who}>{t("nav.signedInAs", { name: me.data.name })}</span>
          <div className={styles.actions}>
            <ThemeToggle className={styles.theme} />
            <Button variant="ghost" onPress={() => signOut.mutate()} isDisabled={signOut.isPending}>
              {t("nav.signOut")}
            </Button>
          </div>
        </div>
      </header>
      <main className={styles.main}>
        <ErrorNotice error={signOut.error} />
        <Outlet />
      </main>
      <LogoPng />
    </>
  );
}
