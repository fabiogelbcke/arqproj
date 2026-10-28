import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api, call, setCsrfToken, type Schemas } from "../api/client";
import { type Locale, useOfficeLocale } from "../i18n";
import { startAnalytics } from "../posthog";
import type { Page } from "./format";
import { PasswordGate } from "./PasswordGate";
import { signOut } from "./signOut";
import { PageMessage, ProjectPage } from "./ProjectPage";
import { ProposalPhase } from "./ProposalPhase";

type State =
  | { kind: "loading" }
  | { kind: "page"; page: Page }
  | { kind: "missing" | "locked" | "unavailable" | "failed"; error?: unknown };

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
  // The staff bar's actions wait for the session's CSRF token.
  const [signedIn, setSignedIn] = useState(false);
  // Staff who haven't seen the project page's tour yet (per account).
  const [tourSeen, setTourSeen] = useState(true);
  // Who is signed in, for the header menu (their initial, name and Sair).
  const [person, setPerson] = useState<{ name: string; email: string } | null>(null);

  useEffect(() => {
    // The office (name, language) is public, so even "not found" is in its language.
    call(api.GET("/api/tenant")).then(setOffice, () => setOffice(null));
    // Signed-in staff: their CSRF token, for publishing from the staff bar.
    call(api.GET("/api/me")).then(
      (me) => {
        setCsrfToken(me.csrf_token);
        void startAnalytics(me);
        setSignedIn(true);
        setTourSeen(me.page_tour_seen);
        setPerson({ name: me.name, email: me.email });
      },
      () => undefined,
    );
    call(api.GET("/api/pages/{slug}", { params: { path: { slug } } })).then(
      (page) => setState({ kind: "page", page }),
      (error) => {
        const code = error instanceof ApiError ? error.code : null;
        const kind =
          code === "page_not_found"
            ? "missing"
            : code === "page_locked"
              ? "locked"
              : code === "page_unavailable"
                ? "unavailable"
                : "failed";
        setState({ kind, error });
      },
    );
  }, [slug, version]);
  useOfficeLocale(((state.kind === "page" && state.page.locale) || office?.locale) as Locale | undefined);

  if (state.kind === "loading") return <p className="sr">{t("page.loading")}</p>;
  // A proposal (A40): only the proposal, until staff mark it accepted.
  if (state.kind === "page" && state.page.in_proposal)
    return (
      <ProposalPhase
        page={state.page}
        ready={signedIn}
        person={person}
        onSignOut={signOut}
        onChanged={() => setVersion((v) => v + 1)}
      />
    );
  if (state.kind === "page")
    return (
      <ProjectPage
        page={state.page}
        slug={slug}
        ready={signedIn}
        tourSeen={tourSeen}
        person={person}
        // Sair: the session ends and the page shows as clients see it.
        onSignOut={signOut}
        onChanged={() => setVersion((v) => v + 1)}
      />
    );
  if (state.kind === "locked")
    return <PasswordGate office={office} slug={slug} onUnlocked={() => setVersion((v) => v + 1)} />;
  if (state.kind === "missing")
    return <PageMessage office={office} title={t("page.notFoundTitle")} body={t("page.notFoundBody")} />;
  // The office disconnected its Drive: staff are told how to bring the pages back.
  if (state.kind === "unavailable")
    return (
      <PageMessage
        office={office}
        title={t("page.unavailableTitle")}
        body={
          person ? (
            <>
              {t("page.unavailableStaff")} <a href="/painel/configuracoes/drive">{t("drive.reconnect")}</a>
            </>
          ) : (
            t("page.unavailableBody")
          )
        }
      />
    );
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
