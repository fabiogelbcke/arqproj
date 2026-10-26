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
import { EXAMPLE_SHARE, EXAMPLE_SHARE_KEY } from "./example/address";
import { PasswordGate } from "./PasswordGate";
import { PageMessage, SiteHeader } from "./ProjectPage";

type Shared = Schemas["SharedOut"];
type State =
  | { kind: "loading" }
  | { kind: "shown"; shared: Shared }
  | { kind: "missing" | "locked" | "failed"; error?: unknown };

export function SharePage({ token }: { token: string }) {
  const { t, i18n } = useTranslation();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [office, setOffice] = useState<Schemas["TenantOut"] | null>(null);
  const [version, setVersion] = useState(0); // bumped once the password is typed
  useEffect(() => {
    call(api.GET("/api/tenant")).then(setOffice, () => setOffice(null));
    // The example project's link (A37): what it picked, from this browser.
    if (token === EXAMPLE_SHARE) {
      setState({ kind: "shown", shared: exampleShared() });
      return;
    }
    call(api.GET("/api/share/{token}", { params: { path: { token } } })).then(
      (shared) => setState({ kind: "shown", shared }),
      (error) => {
        const code = error instanceof ApiError ? error.code : null;
        setState({ kind: code === "share_not_found" ? "missing" : code === "share_locked" ? "locked" : "failed", error });
      },
    );
  }, [token, version]);
  useOfficeLocale(((state.kind === "shown" && state.shared.locale) || office?.locale) as Locale | undefined);
  useEffect(() => {
    const name = state.kind === "shown" ? state.shared.office.name : office?.name;
    document.title = name ? `${t("share.pageTitle")} · ${name}` : t("share.pageTitle");
  }, [state, office, t]);

  if (state.kind === "loading") return <p className="sr">{t("share.loading")}</p>;
  if (state.kind === "locked")
    return (
      <PasswordGate
        office={office}
        slug=""
        onUnlocked={() => setVersion((v) => v + 1)}
        unlock={{
          title: t("share.lockedTitle"),
          body: t("share.lockedBody"),
          send: (password) => call(api.POST("/api/share/{token}/unlock", { params: { path: { token } }, body: { password } })),
        }}
      />
    );
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
  // The example's page has the office as the server tells it.
  const shared = state.shared.office.name || !office ? state.shared : { ...state.shared, office };
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
        {shared.files.length > 1 && token !== EXAMPLE_SHARE && (
          <a
            className="b b--primary share-page__all"
            href={`/api/share/${encodeURIComponent(token)}/zip`}
            download
          >
            {shared.zip_size != null
              ? t("share.downloadAllSize", { size: fileSize(shared.zip_size, i18n.language) })
              : t("share.downloadAll")}
          </a>
        )}
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
                  href={
                    exampleUrls.get(file.key) ??
                    `/api/share/${encodeURIComponent(token)}/files/${encodeURIComponent(file.key)}`
                  }
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

// The example project's files open from the page's own bundle, by their key here.
const exampleUrls = new Map<string, string>();

/** The example's supplier page: the files its "Gerar link" picked in this browser.
 *  A file uploaded into the example lived only on its page, so it's gone here. */
function exampleShared(): Shared {
  let kept: {
    project?: string;
    label?: string | null;
    expires_at?: string | null;
    files?: { name: string; kind: string; size: number | null; modified_at: string; stage: string; url: string }[];
  } = {};
  try {
    kept = JSON.parse(localStorage.getItem(EXAMPLE_SHARE_KEY) ?? "{}");
  } catch {
    // Storage off: an empty page.
  }
  const files = (kept.files ?? []).filter((file) => !file.url.startsWith("blob:"));
  files.forEach((file, i) => exampleUrls.set(`exemplo-${i}`, file.url));
  return {
    office: { name: "", logo_url: null, logo_dark_url: null },
    locale: "pt-BR",
    timezone: "America/Sao_Paulo",
    project: kept.project ?? "",
    label: kept.label ?? null,
    expires_at: kept.expires_at ?? null,
    files: files.map(({ url: _url, ...file }, i) => ({ ...file, key: `exemplo-${i}` })),
    unavailable: (kept.files?.length ?? 0) - files.length,
    zip_size: null,
  };
}
