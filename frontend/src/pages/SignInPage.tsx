import { useMutation } from "@tanstack/react-query";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";

import { api, call } from "../api/client";
import { useMe, useSignedIn } from "../session/session";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { EmailField } from "../ui/EmailField";
import { PasswordField } from "../ui/PasswordField";
import { AuthBrand } from "./AuthBrand";
import styles from "./pages.module.css";

/** Only paths inside the painel, so a crafted link cannot send people elsewhere. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export function SignInPage() {
  const { t } = useTranslation();
  const me = useMe();
  const signedIn = useSignedIn();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const signIn = useMutation({
    mutationFn: (body: { email: string; password: string }) => call(api.POST("/api/session", { body })),
    onSuccess: (me) => {
      signedIn(me);
      navigate(next, { replace: true });
    },
  });

  // "Entrar com Google" (section 5): Google's address, then back to /painel/, or
  // here with why it didn't sign in (?google=…).
  const google = useMutation({
    mutationFn: () => call(api.POST("/api/auth/google/start")),
    onSuccess: ({ url }) => window.location.assign(url),
  });
  const googleProblem = params.get("google");

  if (me.data) return <Navigate to={next} replace />;
  return (
    <main className={styles.centered}>
      <div className={styles.card}>
        <AuthBrand />
        {/* The logos above say whose panel this is; the heading is for screen readers. */}
        <h1 className="sr-only">{t("signIn.title")}</h1>
        {googleProblem && (
          <div role="alert" className={styles.lead}>
            <p>{t(`signIn.googleProblem.${googleProblem}`, { defaultValue: t("signIn.googleProblem.falhou") })}</p>
            {params.get("ref") && <p className={styles.small}>{t("errors.reference", { id: params.get("ref") })}</p>}
          </div>
        )}
        <Button onPress={() => google.mutate()} isDisabled={google.isPending}>
          {t("signIn.google")}
        </Button>
        <ErrorNotice error={google.error} />
        <p className={styles.orLine}>{t("signIn.or")}</p>
        <Form
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            signIn.mutate({ email: String(form.get("email")), password: String(form.get("password")) });
          }}
        >
          <EmailField name="email" autoComplete="username" isRequired lookup label={t("signIn.email")} />
          <PasswordField name="password" autoComplete="current-password" isRequired label={t("signIn.password")} />
          <ErrorNotice error={signIn.error} />
          <Button type="submit" variant="primary" isDisabled={signIn.isPending}>
            {t("signIn.submit")}
          </Button>
        </Form>
        <Link className={styles.small} to="/esqueci-a-senha">
          {t("signIn.forgot")}
        </Link>
      </div>
    </main>
  );
}
