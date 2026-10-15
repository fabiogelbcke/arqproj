import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { api, call } from "../api/client";
import { useMe, useSignedOut } from "../session/session";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { ThemeToggle } from "../ui/ThemeToggle";
import styles from "../pages/pages.module.css";

/** Every screen behind sign-in: the top bar, or a redirect to sign-in. */
export function SignedInLayout() {
  const { t } = useTranslation();
  const me = useMe();
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
          <span className={styles.brand}>{me.data.tenant_name}</span>
          <nav className={styles.nav} aria-label={t("app.name")}>
            <NavLink to="/" end>
              {t("nav.projects")}
            </NavLink>
          </nav>
          <span className={styles.spacer} />
          <span className={styles.who}>{t("nav.signedInAs", { name: me.data.name })}</span>
          <ThemeToggle />
          <Button variant="ghost" onPress={() => signOut.mutate()} isDisabled={signOut.isPending}>
            {t("nav.signOut")}
          </Button>
        </div>
      </header>
      <main className={styles.main}>
        <ErrorNotice error={signOut.error} />
        <Outlet />
      </main>
    </>
  );
}
