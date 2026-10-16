import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api, call, setCsrfToken, type Schemas } from "../api/client";
import { type Locale, useOfficeLocale } from "../i18n";
import type { Page } from "./format";
import { PageMessage, ProjectPage } from "./ProjectPage";

type State =
  | { kind: "loading" }
  | { kind: "page"; page: Page }
  | { kind: "missing" | "locked" | "failed"; error?: unknown };

/** The address is the page: `/casa-jardim`. */
export function slugFromPath(path: string): string {
  return path.replace(/^\/+|\/+$/g, "").split("/")[0] ?? "";
}

export function ClientApp() {
  const { t } = useTranslation();
  const slug = slugFromPath(window.location.pathname);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [office, setOffice] = useState<Schemas["TenantOut"] | null>(null);

  const [version, setVersion] = useState(0); // bumped to load the page again

  useEffect(() => {
    // The office (name, language) is public, so even "not found" is in its language.
    call(api.GET("/api/tenant")).then(setOffice, () => setOffice(null));
    // Signed-in staff: their CSRF token, for publishing from the staff bar.
    call(api.GET("/api/me")).then((me) => setCsrfToken(me.csrf_token), () => undefined);
    call(api.GET("/api/pages/{slug}", { params: { path: { slug } } })).then(
      (page) => setState({ kind: "page", page }),
      (error) => {
        const code = error instanceof ApiError ? error.code : null;
        setState({ kind: code === "page_not_found" ? "missing" : code === "page_locked" ? "locked" : "failed", error });
      },
    );
  }, [slug, version]);
  useOfficeLocale(((state.kind === "page" && state.page.locale) || office?.locale) as Locale | undefined);

  if (state.kind === "loading") return <p className="sr">{t("page.loading")}</p>;
  if (state.kind === "page")
    return <ProjectPage page={state.page} slug={slug} onChanged={() => setVersion((v) => v + 1)} />;
  if (state.kind === "locked") return <PageMessage office={office} title={t("page.lockedTitle")} body={t("page.lockedBody")} />;
  if (state.kind === "missing")
    return <PageMessage office={office} title={t("page.notFoundTitle")} body={t("page.notFoundBody")} />;
  // Anything else: the shared wording, with the support code (AGENTS.md).
  const failure = state.error instanceof ApiError ? state.error : new ApiError("unexpected");
  return (
    <PageMessage
      office={office}
      title={t("errors.unexpected")}
      body={failure.requestId ? t("errors.reference", { id: failure.requestId }) : ""}
    />
  );
}
