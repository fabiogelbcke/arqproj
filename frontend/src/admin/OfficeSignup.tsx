// "Crie o seu escritório" (/criar-escritorio on Unio's address): opened from a
// one-time link an operator sent. Its holder names the office and picks its
// address; the browser then goes on to the new address's owner signup, where
// the account is made. The start of a public signup page (without the link).
import { QueryClient, QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Form } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { api, call } from "../api/client";
import { LIMITS } from "../api/limits";
import { takeToken } from "../api/linkToken";
import { plain } from "../projects/projects";
import { Button } from "../ui/Button";
import { ErrorNotice, errorMessage } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { UnioMark } from "../ui/UnioMark";
import { subdomainOf } from "./Actions";
import styles from "./admin.module.css";

export const SIGNUP_PATH = "/criar-escritorio";
const ADDRESS_MAX = 40; // the server's too (backend/web/office_signup.py)

/** An address from the office's name: "Estúdio Ipê & Co." → "estudio-ipe-co". */
export function suggestedAddress(name: string): string {
  return plain(name)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, ADDRESS_MAX)
    .replace(/-+$/, "");
}

/** The address as it was typed, as the server will take it. */
const typedAddress = (value: string) => value.trim().toLowerCase();

/** Waits until typing pauses before asking whether an address is free. */
function usePaused(value: string, delay = 400) {
  const [paused, setPaused] = useState(value);
  useEffect(() => {
    const wait = setTimeout(() => setPaused(value), delay);
    return () => clearTimeout(wait);
  }, [value, delay]);
  return paused;
}

function SignupForm({ token, domain }: { token: string; domain: string }) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [edited, setEdited] = useState<string | null>(null);
  const address = edited ?? suggestedAddress(name);
  const asked = usePaused(typedAddress(address));
  const free = useQuery({
    queryKey: ["office-signup", "address", asked],
    queryFn: () => call(api.POST("/api/office-signup/check", { body: { token, address: asked } })),
    enabled: asked.length >= 3,
    retry: false,
  });
  const create = useMutation({
    mutationFn: () =>
      call(api.POST("/api/office-signup/create", { body: { token, name, address: typedAddress(address) } })),
    // On to the new address, to make the owner's account there.
    onSuccess: ({ owner_url }) => window.location.assign(owner_url),
  });
  const current = asked === typedAddress(address);
  const status =
    !current || asked.length < 3
      ? null
      : free.error
        ? { kind: "problem", text: errorMessage(free.error) }
        : free.data?.address_free === true
          ? { kind: "ok", text: t("signup.addressFree") }
          : free.data?.address_free === false
            ? { kind: "problem", text: t("errors.office_address_taken") }
            : null;
  return (
    <Form
      className={styles.signIn}
      onSubmit={(event) => {
        event.preventDefault();
        create.mutate();
      }}
    >
      <TextField
        label={t("signup.name")}
        description={t("signup.nameHint")}
        value={name}
        onChange={setName}
        maxLength={LIMITS.officeName}
        isRequired
        autoFocus
        autoComplete="organization"
      />
      <div className={styles.addressField}>
        <TextField
          label={t("signup.address")}
          description={t("signup.addressHint")}
          suffix={`.${domain}`}
          value={address}
          onChange={(value) => setEdited(subdomainOf(value, `.${domain}`))}
          maxLength={ADDRESS_MAX}
          isRequired
          autoComplete="off"
          spellCheck="false"
        />
        <p className={styles.addressStatus} aria-live="polite">
          {status && <span className={status.kind === "ok" ? styles.addressOk : styles.addressProblem}>{status.text}</span>}
        </p>
      </div>
      <ErrorNotice error={create.error} />
      <Button
        type="submit"
        variant="primary"
        isDisabled={create.isPending || create.isSuccess || !name.trim() || status?.kind === "problem"}
      >
        {t("signup.create")}
      </Button>
      <p className={styles.muted}>{t("signup.next")}</p>
    </Form>
  );
}

function OfficeSignup() {
  const { t } = useTranslation();
  const [token] = useState(takeToken);
  const link = useQuery({
    queryKey: ["office-signup", "link", token],
    queryFn: () => call(api.POST("/api/office-signup/check", { body: { token } })),
    enabled: token !== "",
    retry: false,
  });
  return (
    <main className={styles.centered}>
      <div className={styles.signIn}>
        <UnioMark className={styles.signInMark} />
        <h1>{t("signup.title")}</h1>
        {!token || link.error ? (
          <p role="alert" className={styles.problem}>
            {token ? errorMessage(link.error) : t("errors.signup_link_invalid")}
          </p>
        ) : link.data ? (
          <>
            <p className={styles.mutedText}>{t("signup.intro")}</p>
            <SignupForm token={token} domain={link.data.domain} />
          </>
        ) : (
          <p className={styles.muted}>{t("app.loading")}</p>
        )}
      </div>
    </main>
  );
}

export function OfficeSignupApp() {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } }));
  return (
    <QueryClientProvider client={client}>
      <OfficeSignup />
    </QueryClientProvider>
  );
}
