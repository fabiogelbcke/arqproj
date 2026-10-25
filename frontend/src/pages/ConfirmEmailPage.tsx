import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { ApiError, api, call, type Me } from "../api/client";
import { ME, useSignedIn, useSignedOut } from "../session/session";
import { Button } from "../ui/Button";
import { EmailField } from "../ui/EmailField";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { AuthBrand } from "./AuthBrand";
import { takeToken } from "./ChoosePasswordPage";
import styles from "./pages.module.css";

/** Shown instead of the painel to someone who joined through the office's shared
 *  link (A36) until they confirm their email: the code sent to it, a new code, a
 *  mistyped address corrected, or signing out. */
export function ConfirmEmailPage({ me }: { me: Me }) {
  const { t } = useTranslation();
  const signedIn = useSignedIn();
  const signedOut = useSignedOut();
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [correcting, setCorrecting] = useState(false);
  const [newEmail, setNewEmail] = useState(me.email);
  const [resent, setResent] = useState(false);

  const confirm = useMutation({
    mutationFn: () => call(api.POST("/api/me/email-code", { body: { code } })),
    onSuccess: (confirmed) => signedIn(confirmed),
  });
  const resend = useMutation({
    mutationFn: () => call(api.POST("/api/me/email-code/resend")),
    onMutate: () => setResent(false),
    onSuccess: () => {
      setResent(true);
      confirm.reset();
    },
  });
  const correct = useMutation({
    mutationFn: () => call(api.PUT("/api/me/email", { body: { email: newEmail } })),
    onSuccess: (corrected) => {
      signedIn(corrected);
      setCorrecting(false);
      setResent(true);
      setCode("");
      confirm.reset();
    },
  });
  const signOut = useMutation({
    mutationFn: () => call(api.DELETE("/api/session")),
    onSuccess: () => {
      signedOut();
      navigate("/entrar", { replace: true });
    },
  });

  return (
    <main className={styles.centered}>
      <div className={styles.card}>
        <AuthBrand />
        <div>
          <h1 className={styles.title}>{t("confirmEmail.title")}</h1>
          <p className={styles.lead}>{t("confirmEmail.intro", { email: me.email })}</p>
        </div>
        {correcting ? (
          <Form
            onSubmit={(event) => {
              event.preventDefault();
              correct.mutate();
            }}
          >
            <EmailField label={t("confirmEmail.newEmail")} value={newEmail} onChange={setNewEmail} isRequired autoComplete="username" />
            <ErrorNotice error={correct.error} />
            <div className={styles.confirmActions}>
              <Button type="submit" variant="primary" isDisabled={correct.isPending}>
                {t("confirmEmail.saveEmail")}
              </Button>
              <Button variant="ghost" onPress={() => setCorrecting(false)}>
                {t("confirmEmail.cancel")}
              </Button>
            </div>
          </Form>
        ) : (
          <Form
            onSubmit={(event) => {
              event.preventDefault();
              confirm.mutate();
            }}
          >
            <TextField
              name="code"
              label={t("confirmEmail.code")}
              value={code}
              onChange={(value) => setCode(value.replace(/\D/g, "").slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              isRequired
              minLength={6}
            />
            <ErrorNotice error={confirm.error} />
            {resent && !resend.error && <p role="status" className={styles.small}>{t("confirmEmail.resent", { email: me.email })}</p>}
            <ErrorNotice error={resend.error} />
            <Button type="submit" variant="primary" isDisabled={confirm.isPending}>
              {t("confirmEmail.submit")}
            </Button>
            <div className={styles.confirmActions}>
              <Button variant="ghost" onPress={() => resend.mutate()} isDisabled={resend.isPending}>
                {t("confirmEmail.resend")}
              </Button>
              <Button
                variant="ghost"
                onPress={() => {
                  setNewEmail(me.email);
                  correct.reset();
                  setCorrecting(true);
                }}
              >
                {t("confirmEmail.correct")}
              </Button>
            </div>
          </Form>
        )}
        <ErrorNotice error={signOut.error} />
        <Button variant="ghost" size="small" className={styles.signOutLink} onPress={() => signOut.mutate()} isDisabled={signOut.isPending}>
          {t("confirmEmail.signOut")}
        </Button>
      </div>
    </main>
  );
}

/** The email's link (`/confirmar-email#token=…`), often opened on a phone: it
 *  confirms the address, then leads to the painel (signed in there or not). */
export function ConfirmLinkPage() {
  const { t } = useTranslation();
  const [token] = useState(takeToken);
  const client = useQueryClient();
  const [state, setState] = useState<"idle" | "done" | "invalid">(token ? "idle" : "invalid");
  const confirm = useMutation({
    mutationFn: () => call(api.POST("/api/email-confirmation", { body: { token } })),
    onSuccess: () => {
      setState("done");
      void client.invalidateQueries({ queryKey: ME }); // signed in here: the painel opens
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "link_invalid") setState("invalid");
    },
  });
  return (
    <main className={styles.centered}>
      <div className={styles.card}>
        <AuthBrand />
        {state === "done" ? (
          <div role="status">
            <h1 className={styles.title}>{t("confirmEmail.doneTitle")}</h1>
            <p className={styles.lead}>{t("confirmEmail.doneBody")}</p>
          </div>
        ) : state === "invalid" ? (
          <div>
            <h1 className={styles.title}>{t("confirmEmail.invalidTitle")}</h1>
            <p className={styles.lead}>{t("confirmEmail.invalidBody")}</p>
          </div>
        ) : (
          <>
            <div>
              <h1 className={styles.title}>{t("confirmEmail.title")}</h1>
              <p className={styles.lead}>{t("confirmEmail.linkIntro")}</p>
            </div>
            <ErrorNotice error={confirm.error} />
            {/* A button, not on load: mail scanners open links to check them. */}
            <Button variant="primary" onPress={() => confirm.mutate()} isDisabled={confirm.isPending}>
              {t("confirmEmail.linkSubmit")}
            </Button>
          </>
        )}
        <Link className={styles.small} to="/">
          {t("confirmEmail.toPainel")}
        </Link>
      </div>
    </main>
  );
}
