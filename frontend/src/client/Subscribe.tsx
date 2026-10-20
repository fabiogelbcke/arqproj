// "Receber as novidades por e-mail" on the client's page (A32, 20 Oct 2026): the
// address gets a link to confirm, and is listed only once confirmed.
import { useId, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api, call } from "../api/client";
import { emailSuggestion, isEmail, tidyEmail } from "../ui/email";

export function Subscribe({ slug }: { slug: string }) {
  const { t } = useTranslation();
  const id = useId();
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [problem, setProblem] = useState<string | null>(null);
  const tidy = tidyEmail(email);
  const suggestion = isEmail(tidy) ? emailSuggestion(tidy) : null;
  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (!isEmail(tidy)) return setProblem(t("emailField.invalid"));
    setProblem(null);
    setState("sending");
    try {
      await call(api.POST("/api/pages/{slug}/subscribe", { params: { path: { slug } }, body: { email: tidy } }));
      setState("sent");
    } catch (failure) {
      const code = failure instanceof ApiError ? failure.code : "unexpected";
      setProblem(
        code === "project_archived" ? t("subscribe.archived") : t(`errors.${code}`, { defaultValue: t("errors.unexpected") }),
      );
      setState("idle");
    }
  };
  if (state === "sent")
    return (
      <section className="client-subscribe" aria-labelledby={`${id}-title`}>
        <h2 id={`${id}-title`}>{t("subscribe.title")}</h2>
        <p role="status">{t("subscribe.sent", { email: tidy })}</p>
      </section>
    );
  return (
    <section className="client-subscribe" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>{t("subscribe.title")}</h2>
      <p>{t("subscribe.intro")}</p>
      <form onSubmit={send} noValidate>
        <label className="sr" htmlFor={id}>
          {t("subscribe.email")}
        </label>
        <input
          id={id}
          type="text"
          inputMode="email"
          autoComplete="email"
          autoCapitalize="none"
          spellCheck={false}
          placeholder={t("subscribe.placeholder")}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={problem ? true : undefined}
          aria-describedby={problem ? `${id}-problem` : undefined}
        />
        <button className="b b--small b--primary" type="submit" disabled={state === "sending" || !tidy}>
          {t("subscribe.submit")}
        </button>
      </form>
      {suggestion && (
        <p className="client-subscribe__hint">
          {t("emailField.didYouMean")}{" "}
          <button type="button" onClick={() => setEmail(suggestion)}>
            {suggestion}
          </button>
          ?
        </p>
      )}
      {problem && (
        <p id={`${id}-problem`} className="client-subscribe__problem" role="alert">
          {problem}
        </p>
      )}
    </section>
  );
}
