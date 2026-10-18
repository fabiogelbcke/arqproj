import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { ApiError, api, call } from "../api/client";
import { useSignedIn } from "../session/session";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { AuthBrand } from "./AuthBrand";
import styles from "./pages.module.css";

export const MIN_PASSWORD_LENGTH = 8; // backend.identity.accounts; the server checks it too

/** The link's token is in the fragment (#token=…), which browsers never send to
 * servers. Read it once, then take it out of the address bar and history. */
function takeToken(): string {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
  if (token) window.history.replaceState(window.history.state, "", window.location.pathname);
  return token;
}

export function ChoosePasswordPage() {
  const { t } = useTranslation();
  const [token] = useState(takeToken);
  const [password, setPassword] = useState("");
  const signedIn = useSignedIn();
  const navigate = useNavigate();
  const link = useQuery({
    queryKey: ["password-link", token],
    queryFn: () => call(api.POST("/api/password-link", { body: { token } })),
    enabled: token !== "",
    retry: false,
  });
  const choose = useMutation({
    mutationFn: (newPassword: string) => call(api.POST("/api/password", { body: { token, password: newPassword } })),
    onSuccess: (me) => {
      signedIn(me);
      navigate("/", { replace: true });
    },
  });

  const invalid =
    token === "" ||
    (link.error instanceof ApiError && link.error.code === "link_invalid") ||
    (choose.error instanceof ApiError && choose.error.code === "link_invalid");
  if (invalid) {
    return (
      <main className={styles.centered}>
        <div className={styles.card}>
          <AuthBrand />
          <h1 className={styles.title}>{t("choosePassword.invalidTitle")}</h1>
          <p className={styles.lead}>{t("choosePassword.invalidBody")}</p>
          <Link to="/esqueci-a-senha">{t("choosePassword.askAgain")}</Link>
          <Link className={styles.small} to="/entrar">
            {t("choosePassword.toSignIn")}
          </Link>
        </div>
      </main>
    );
  }
  if (!link.data) {
    return (
      <main className={styles.centered}>
        {link.error ? <ErrorNotice error={link.error} /> : <p className={styles.lead}>{t("app.loading")}</p>}
      </main>
    );
  }
  return (
    <main className={styles.centered}>
      <div className={styles.card}>
        <AuthBrand />
        <div>
          <h1 className={styles.title}>
            {t(link.data.kind === "invite" ? "choosePassword.titleInvite" : "choosePassword.titleReset")}
          </h1>
          <p className={styles.lead}>
            {t("choosePassword.greeting", { name: link.data.name, email: link.data.email })}
          </p>
        </div>
        <Form
          onSubmit={(event) => {
            event.preventDefault();
            choose.mutate(password);
          }}
        >
          <TextField
            name="password"
            type="password"
            autoComplete="new-password"
            isRequired
            minLength={MIN_PASSWORD_LENGTH}
            value={password}
            onChange={setPassword}
            label={t("choosePassword.password")}
            description={t("choosePassword.passwordHint", { min: MIN_PASSWORD_LENGTH })}
          />
          <TextField
            name="confirm"
            type="password"
            autoComplete="new-password"
            isRequired
            validate={(value) => (value && value !== password ? t("choosePassword.mismatch") : null)}
            label={t("choosePassword.confirm")}
          />
          <ErrorNotice error={choose.error} values={{ min: MIN_PASSWORD_LENGTH }} />
          <Button type="submit" variant="primary" isDisabled={choose.isPending}>
            {t("choosePassword.submit")}
          </Button>
        </Form>
      </div>
    </main>
  );
}
