// The supplier's page (A37): the files someone shared by link, to download one by
// one. Branded with the office, at its address (`/share/{token}`); the link is the
// only key, so nothing here asks for a password or an account.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api, call, type Schemas } from "../api/client";
import { type Locale, useOfficeLocale } from "../i18n";
import { SiteFooter } from "../ui/UnioMark";
import { extension, fileSize } from "./FileTools";
import { day } from "./format";
import { PageMessage, SiteHeader } from "./ProjectPage";

type Shared = Schemas["SharedOut"];
type State = { kind: "loading" } | { kind: "shown"; shared: Shared } | { kind: "missing" | "failed"; error?: unknown };

export function SharePage({ token }: { token: string }) {
  const { t, i18n } = useTranslation();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [office, setOffice] = useState<Schemas["TenantOut"] | null>(null);
  useEffect(() => {
    call(api.GET("/api/tenant")).then(setOffice, () => setOffice(null));
    call(api.GET("/api/share/{token}", { params: { path: { token } } })).then(
      (shared) => setState({ kind: "shown", shared }),
      (error) => {
        const missing = error instanceof ApiError && error.code === "share_not_found";
        setState({ kind: missing ? "missing" : "failed", error });
      },
    );
  }, [token]);
  useOfficeLocale(((state.kind === "shown" && state.shared.locale) || office?.locale) as Locale | undefined);
  useEffect(() => {
    const name = state.kind === "shown" ? state.shared.office.name : office?.name;
    document.title = name ? `${t("share.pageTitle")} · ${name}` : t("share.pageTitle");
  }, [state, office, t]);

  if (state.kind === "loading") return <p className="sr">{t("share.loading")}</p>;
  if (state.kind === "missing")
    return <PageMessage office={office} title={t("share.unavailableTitle")} body={t("errors.share_not_found")} />;
  if (state.kind !== "shown") {
    const reference = state.error instanceof ApiError ? state.error.requestId : null;
    return (
      <PageMessage
        office={office}
        title={t("share.failedTitle")}
        body={
          <>
            {t("share.filesUnavailable")}
            {reference && (
              <>
                <br />
                {t("errors.reference", { id: reference })}
              </>
            )}
          </>
        }
      />
    );
  }
  const shared = state.shared;
  const date = (value: string) => day(value, i18n.language, shared.timezone);
  return (
    <div className="client share-page">
      <SiteHeader office={shared.office} />
      <div className="cwrap">
        <header className="share-page__head">
          <h1>{t("share.pageTitle")}</h1>
          <p>{t("share.sharedFrom", { project: shared.project, office: shared.office.name })}</p>
          {(shared.label || shared.expires_at) && (
            <p className="share-meta">
              {[
                shared.label && t("share.for", { label: shared.label }),
                shared.expires_at && t("share.availableUntil", { date: date(shared.expires_at) }),
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          )}
        </header>
        {shared.files.length ? (
          <ul className="share-page__files">
            {shared.files.map((file) => (
              <li key={file.key}>
                <span className="share-page__type" aria-hidden="true">
                  {extension(file.name).toUpperCase() || "—"}
                </span>
                <span className="share-page__name">
                  <strong>{file.name}</strong>
                  <small>
                    {[file.stage, fileSize(file.size, i18n.language), date(file.modified_at)].filter(Boolean).join(" · ")}
                  </small>
                </span>
                <a
                  className="b b--small"
                  href={`/api/share/${encodeURIComponent(token)}/files/${encodeURIComponent(file.key)}`}
                  aria-label={t("share.downloadFile", { name: file.name })}
                  download
                >
                  {t("share.download")}
                </a>
              </li>
            ))}
          </ul>
        ) : null}
        {shared.unavailable > 0 && (
          <p className="share-page__gone" role="note">
            {shared.files.length ? t("share.gone", { count: shared.unavailable }) : t("share.allGone")}
          </p>
        )}
        <SiteFooter office={shared.office.name} className="client-footer" />
      </div>
    </div>
  );
}
