import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { ApiError, api, call } from "../api/client";
import { takeToken } from "../api/linkToken";
import { useSignedIn } from "../session/session";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { MIN_PASSWORD_LENGTH, NewPasswordFields } from "../ui/NewPasswordFields";
import { AuthBrand } from "./AuthBrand";
import styles from "./pages.module.css";

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
          <NewPasswordFields password={password} onChange={setPassword} />
          <ErrorNotice error={choose.error} values={{ min: MIN_PASSWORD_LENGTH }} />
          <Button type="submit" variant="primary" isDisabled={choose.isPending}>
            {t("choosePassword.submit")}
          </Button>
        </Form>
      </div>
    </main>
  );
}
