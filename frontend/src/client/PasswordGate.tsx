import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api, call } from "../api/client";
import { PasswordField } from "../ui/PasswordField";
import { SiteHeader } from "./ProjectPage";
import { PendingContent } from "../ui/PendingContent";

/** A protected page: the client types the password once per device (A06). With
 *  `unlock`, a shared link's own password (A37), in the link's words. */
export function PasswordGate({
  office,
  slug,
  onUnlocked,
  unlock,
}: {
  office: { name: string } | null;
  slug: string;
  onUnlocked: () => void;
  unlock?: { title: string; body: string; send: (password: string) => Promise<unknown> };
}) {
  const { t, i18n } = useTranslation();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  return (
    <div className="client">
      {office && <SiteHeader office={office} />}
      <div className="cwrap page-message">
        <h1>{unlock?.title ?? t("page.lockedTitle")}</h1>
        <p>{unlock?.body ?? t("page.lockedBody")}</p>
        <form
          className="password-gate"
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy(true);
            setProblem(null);
            try {
              await (unlock
                ? unlock.send(password)
                : call(api.POST("/api/pages/{slug}/unlock", { params: { path: { slug } }, body: { password } })));
              onUnlocked();
            } catch (failure) {
              const error = failure instanceof ApiError ? failure : new ApiError("unexpected");
              const message = i18n.exists(`errors.${error.code}`) ? t(`errors.${error.code}`) : t("errors.unexpected");
              const known = ["wrong_page_password", "wrong_share_password", "too_many_attempts"].includes(error.code);
              setProblem(known || !error.requestId ? message : `${message} ${t("errors.reference", { id: error.requestId })}`);
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className="password-gate__row">
            {/* The eye and the Caps Lock mark: a password sent by message is
                easy to mistype, and the client can't ask anyone right then. */}
            <PasswordField
              label={t("page.password")}
              autoComplete="current-password"
              value={password}
              onChange={setPassword}
              isRequired
              autoFocus
            />
            <button className="b b--primary" type="submit" disabled={busy || !password} aria-busy={busy || undefined}>
              <PendingContent pending={busy}>{t("page.enter")}</PendingContent>
            </button>
          </div>
          {problem && (
            <p role="alert" className="password-gate__problem">
              {problem}
            </p>
          )}
        </form>
      </div>
    </div>
  );
}
