import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { api, call } from "../api/client";
import { LIMITS } from "../api/limits";
import { ME, useMe, useSignedIn } from "../session/session";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { NewPasswordFields } from "../ui/NewPasswordFields";
import { Panel } from "../ui/Panel";
import { PasswordField } from "../ui/PasswordField";
import { TextField } from "../ui/TextField";
import { toast } from "../ui/Toast";
import styles from "./pages.module.css";

/** "Minha conta" (/painel/conta): the signed-in person's own name and password,
 *  from the account menu and the phone drawer. Their email shows; changing it is
 *  later (it needs the new address confirmed). */
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
      <TextField label={t("account.email")} description={t("account.emailHint")} value={email} isReadOnly />
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
