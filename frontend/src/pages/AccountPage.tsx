import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { DialogTrigger, Form } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { ApiError, api, call } from "../api/client";
import { LIMITS } from "../api/limits";
import { ME, useMe, useSignedIn } from "../session/session";
import { Button } from "../ui/Button";
import dialogs from "../projects/projects.module.css";
import { DialogFrame } from "../ui/DialogFrame";
import { EmailField } from "../ui/EmailField";
import { ErrorNotice } from "../ui/ErrorNotice";
import { NewPasswordFields } from "../ui/NewPasswordFields";
import { Panel } from "../ui/Panel";
import { PasswordField } from "../ui/PasswordField";
import { TextField } from "../ui/TextField";
import { toast } from "../ui/Toast";
import styles from "./pages.module.css";

/** "Minha conta" (/painel/conta): the signed-in person's own name, email and
 *  password, from the account menu and the phone drawer. */
export function AccountPage() {
  const { t } = useTranslation();
  const me = useMe();
  if (!me.data) return null; // the layout waits for the session
  return (
    <>
      <h1 className={styles.pageTitle}>{t("account.title")}</h1>
      <Panel className={styles.settingsPanel} aria-labelledby="account-name">
        <h2 id="account-name">{t("account.nameTitle")}</h2>
        <NameForm current={me.data.name} email={me.data.email} />
      </Panel>
      <Panel className={styles.settingsPanel} aria-labelledby="account-password">
        <h2 id="account-password">{t("account.passwordTitle")}</h2>
        <PasswordForm />
      </Panel>
    </>
  );
}

function NameForm({ current, email }: { current: string; email: string }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [name, setName] = useState<string | null>(null); // null: untouched
  const save = useMutation({
    mutationFn: (value: string) => call(api.PATCH("/api/me", { body: { name: value } })),
    onSuccess: () => {
      setName(null);
      void client.invalidateQueries({ queryKey: ME });
      toast(t("account.nameSaved"));
    },
  });
  const value = name ?? current;
  return (
    <Form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(value);
      }}
    >
      <TextField
        label={t("account.name")}
        description={t("account.nameHint")}
        value={value}
        onChange={setName}
        maxLength={LIMITS.staffName}
        isRequired
        autoComplete="name"
      />
      <div className={styles.accountEmail}>
        <TextField label={t("account.email")} description={t("account.emailHint")} value={email} isReadOnly />
        <ChangeEmail />
      </div>
      <ErrorNotice error={save.error} />
      <div className={styles.actions}>
        <Button type="submit" variant="primary" isDisabled={save.isPending || name === null || !value.trim()}>
          {t("account.save")}
        </Button>
      </div>
    </Form>
  );
}

function PasswordForm() {
  const { t } = useTranslation();
  const signedIn = useSignedIn();
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [round, setRound] = useState(0); // a new form after a change: empty fields
  const change = useMutation({
    mutationFn: () => call(api.POST("/api/me/password", { body: { current, password } })),
    onSuccess: (me) => {
      signedIn(me); // a new session for this device: its token
      setCurrent("");
      setPassword("");
      setRound((n) => n + 1);
      toast(t("account.passwordChanged"));
    },
  });
  return (
    <Form
      key={round}
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        change.mutate();
      }}
    >
      <PasswordField
        label={t("account.currentPassword")}
        value={current}
        onChange={setCurrent}
        isRequired
        autoComplete="current-password"
      />
      <NewPasswordFields password={password} onChange={setPassword} />
      <p className={styles.small}>{t("account.passwordNote")}</p>
      <ErrorNotice error={change.error} />
      <div className={styles.actions}>
        <Button type="submit" variant="primary" isDisabled={change.isPending}>
          {t("account.changePassword")}
        </Button>
      </div>
    </Form>
  );
}

/** "Alterar e-mail": the new address and the current password. The new address
 *  becomes the account's, unconfirmed: the painel then asks for the code sent to
 *  it (ConfirmEmailPage), and the old address is told. */
function ChangeEmail() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const signedIn = useSignedIn();
  const [email, setEmail] = useState("");
  const [current, setCurrent] = useState("");
  const change = useMutation({
    mutationFn: () => call(api.POST("/api/me/email/change", { body: { email, current } })),
    onSuccess: (me) => signedIn(me), // unconfirmed now: the layout shows the code screen
    // The address changed but the code didn't go: the code screen, to resend it there.
    onError: (failure) => {
      if (failure instanceof ApiError && failure.code === "email_not_sent")
        void client.invalidateQueries({ queryKey: ME });
    },
  });
  return (
    <DialogTrigger>
      <Button variant="ghost" size="small">
        {t("account.changeEmail")}
      </Button>
      <DialogFrame title={t("account.changeEmail")}>
        {(close) => (
          <Form
            className={styles.form}
            onSubmit={(event) => {
              event.preventDefault();
              change.mutate();
            }}
          >
            <p className={styles.small}>{t("account.changeEmailNote")}</p>
            <EmailField label={t("account.newEmail")} value={email} onChange={setEmail} isRequired autoFocus />
            <PasswordField
              label={t("account.currentPassword")}
              value={current}
              onChange={setCurrent}
              isRequired
              autoComplete="current-password"
            />
            <ErrorNotice error={change.error} />
            <div className={dialogs.actions}>
              <Button variant="ghost" onPress={close} isDisabled={change.isPending}>
                {t("account.cancel")}
              </Button>
              <Button type="submit" variant="primary" isDisabled={change.isPending}>
                {t("account.sendCode")}
              </Button>
            </div>
          </Form>
        )}
      </DialogFrame>
    </DialogTrigger>
  );
}
