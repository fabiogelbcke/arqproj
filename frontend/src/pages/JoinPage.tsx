import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { ApiError, api, call } from "../api/client";
import { takeToken } from "../api/linkToken";
import { LIMITS } from "../api/limits";
import { useSignedIn } from "../session/session";
import { Button } from "../ui/Button";
import { EmailField } from "../ui/EmailField";
import { ErrorNotice } from "../ui/ErrorNotice";
import { MIN_PASSWORD_LENGTH, NewPasswordFields } from "../ui/NewPasswordFields";
import { TextField } from "../ui/TextField";
import { AuthBrand } from "./AuthBrand";
import styles from "./pages.module.css";

/** A shared member link or one-time owner link (A36): a name, an email and a
 *  password, then signed in to confirm the email with the code sent to it
 *  (`ConfirmEmailPage`, which the painel shows until it's done). */
export function JoinPage() {
  const { t } = useTranslation();
  const [token] = useState(takeToken);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const signedIn = useSignedIn();
  const navigate = useNavigate();
  const link = useQuery({
    queryKey: ["join-link", token],
    queryFn: () => call(api.POST("/api/join/check", { body: { token } })),
    enabled: token !== "",
    retry: false,
  });
  const join = useMutation({
    mutationFn: () => call(api.POST("/api/join", { body: { token, name, email, password } })),
    onSuccess: (me) => {
      signedIn(me);
      navigate("/", { replace: true });
    },
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
        ) : (
          <>
            <div>
              <h1 className={styles.title}>
                {t(link.data?.role === "owner" ? "join.ownerTitle" : "join.title", { office: link.data?.office ?? "" })}
              </h1>
              <p className={styles.lead}>{t("join.intro")}</p>
            </div>
            <Form
              onSubmit={(event) => {
                event.preventDefault();
                join.mutate();
              }}
            >
              <TextField label={t("team.name")} value={name} onChange={setName} isRequired maxLength={LIMITS.staffName} autoComplete="name" />
              <EmailField label={t("team.email")} value={email} onChange={setEmail} isRequired autoComplete="username" />
              <NewPasswordFields password={password} onChange={setPassword} />
              <ErrorNotice error={link.error ?? join.error} values={{ min: MIN_PASSWORD_LENGTH }} />
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
