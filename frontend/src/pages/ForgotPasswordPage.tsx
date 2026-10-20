import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { api, call } from "../api/client";
import { useTenant } from "../session/session";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { EmailField } from "../ui/EmailField";
import { AuthBrand } from "./AuthBrand";
import styles from "./pages.module.css";

/** "Esqueceu a senha?": an email with a link to choose a new one. The answer never
 *  says whether the address has an account here. */
export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const tenant = useTenant();
  const [email, setEmail] = useState("");
  const ask = useMutation({
    mutationFn: (address: string) => call(api.POST("/api/password-reset", { body: { email: address } })),
  });
  const office = tenant.data?.name ?? "";
  return (
    <main className={styles.centered}>
      <div className={styles.card}>
        <AuthBrand />
        {ask.isSuccess ? (
          <div role="status">
            <h1 className={styles.title}>{t("forgot.sentTitle")}</h1>
            <p className={styles.lead}>{t("forgot.sent", { email: email.trim(), office })}</p>
          </div>
        ) : (
          <>
            <div>
              <h1 className={styles.title}>{t("forgot.title")}</h1>
              <p className={styles.lead}>{t("forgot.intro", { office })}</p>
            </div>
            <Form
              onSubmit={(event) => {
                event.preventDefault();
                ask.mutate(email);
              }}
            >
              <EmailField
                name="email"
                autoComplete="username"
                isRequired
                value={email}
                onChange={setEmail}
                label={t("signIn.email")}
              />
              <ErrorNotice error={ask.error} />
              <Button type="submit" variant="primary" isDisabled={ask.isPending}>
                {t("forgot.submit")}
              </Button>
            </Form>
          </>
        )}
        <Link className={styles.small} to="/entrar">
          {t("forgot.back")}
        </Link>
      </div>
    </main>
  );
}
