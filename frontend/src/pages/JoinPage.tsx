import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { ApiError, api, call } from "../api/client";
import { Button } from "../ui/Button";
import { EmailField } from "../ui/EmailField";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { AuthBrand } from "./AuthBrand";
import { takeToken } from "./ChoosePasswordPage";
import styles from "./pages.module.css";

/** The office's shared link for joining its staff (A36): a name and an email, and
 *  the app emails a link to choose a password there, so the email is proven theirs. */
export function JoinPage() {
  const { t } = useTranslation();
  const [token] = useState(takeToken);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const link = useQuery({
    queryKey: ["join-link", token],
    queryFn: () => call(api.POST("/api/join/check", { body: { token } })),
    enabled: token !== "",
    retry: false,
  });
  const join = useMutation({
    mutationFn: () => call(api.POST("/api/join", { body: { token, name, email } })),
  });
  const invalid =
    token === "" ||
    (link.error instanceof ApiError && link.error.code === "join_link_invalid") ||
    (join.error instanceof ApiError && join.error.code === "join_link_invalid");
  return (
    <main className={styles.centered}>
      <div className={styles.card}>
        <AuthBrand />
        {invalid ? (
          <div>
            <h1 className={styles.title}>{t("join.invalidTitle")}</h1>
            <p className={styles.lead}>{t("join.invalidBody")}</p>
          </div>
        ) : join.isSuccess ? (
          <div role="status">
            <h1 className={styles.title}>{t("join.sentTitle")}</h1>
            <p className={styles.lead}>{t("join.sent", { email: email.trim() })}</p>
          </div>
        ) : (
          <>
            <div>
              <h1 className={styles.title}>{t("join.title", { office: link.data?.office ?? "" })}</h1>
              <p className={styles.lead}>{t("join.intro")}</p>
            </div>
            <Form
              onSubmit={(event) => {
                event.preventDefault();
                join.mutate();
              }}
            >
              <TextField label={t("team.name")} value={name} onChange={setName} isRequired maxLength={80} autoComplete="name" />
              <EmailField label={t("team.email")} value={email} onChange={setEmail} isRequired />
              <ErrorNotice error={link.error ?? join.error} />
              <Button type="submit" variant="primary" isDisabled={join.isPending || !link.data}>
                {t("join.submit")}
              </Button>
            </Form>
          </>
        )}
        <Link className={styles.small} to="/entrar">
          {t("join.haveAccount")}
        </Link>
      </div>
    </main>
  );
}
