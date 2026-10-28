// A project's page while it is a proposal (A40): the proposal itself, its PDF and
// the office's contact details, and nothing of the work, which hasn't started.
// Staff get a bar to change the proposal or mark it accepted.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api, call } from "../api/client";
import { ProposalLetter } from "../proposals/ProposalLetter";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { Toaster, toast, toastError } from "../ui/Toast";
import { SiteFooter } from "../ui/UnioMark";
import type { Page } from "./format";
import { Icon, SiteHeader } from "./ProjectPage";

function StaffBar({ page, ready, onChanged }: { page: Page; ready: boolean; onChanged?: () => void }) {
  const { t } = useTranslation();
  const staff = page.staff!;
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const open = staff.status === "proposal";
  const accept = async () => {
    setBusy(true);
    try {
      await call(
        api.POST("/api/projects/{project_id}/accept-proposal", {
          params: { path: { project_id: staff.project_id } },
          body: { row_version: staff.row_version },
        }),
      );
      setAsking(false);
      toast(t("proposal.accept.done"));
      onChanged?.();
    } catch (failure) {
      setAsking(false);
      toastError(failure);
    } finally {
      setBusy(false);
    }
  };
  return (
    <nav className="dock" aria-label={t("page.staffBar")}>
      <a className="b" href="/painel/" aria-label={t("page.backToPainel")}>
        <Icon name="left" />
        <span className="hide-sm">{t("page.backToPainel")}</span>
      </a>
      <span className="dock__sep" />
      <span className="dock__title">{page.name}</span>
      {open && (
        <a className="b b--small" href={`/painel/projetos/${staff.project_id}/proposta`}>
          {page.proposal ? t("proposal.page.edit") : t("proposal.page.create")}
        </a>
      )}
      {open && (
        <button type="button" className="b b--small b--primary" disabled={!ready} onClick={() => setAsking(true)}>
          {t("proposal.accept.action")}
        </button>
      )}
      <button
        className="iconbtn"
        type="button"
        aria-label={t("page.copyLink")}
        title={t("page.copyLink")}
        onClick={() => {
          const link = window.location.origin + window.location.pathname;
          navigator.clipboard?.writeText(link).then(
            () => toast(t("page.linkCopied")),
            () => toast(link),
          );
        }}
      >
        <Icon name="link" />
      </button>
      {asking && (
        <ConfirmDialog
          title={t("proposal.accept.ask")}
          text={t("proposal.accept.means")}
          confirm={t("proposal.accept.confirm")}
          busy={busy}
          onCancel={() => setAsking(false)}
          onConfirm={() => void accept()}
        />
      )}
    </nav>
  );
}

export function ProposalPhase({
  page,
  ready = false,
  person,
  onSignOut,
  onChanged,
}: {
  page: Page;
  ready?: boolean;
  person?: { name: string; email: string } | null;
  onSignOut?: () => void;
  onChanged?: () => void;
}) {
  const { t } = useTranslation();
  const proposal = page.proposal;
  const contact = proposal
    ? [
        proposal.address && <p key="address">{proposal.address}</p>,
        proposal.phone && (
          <p key="phone">
            <a href={`tel:${proposal.phone.replace(/[^\d+]/g, "")}`}>{proposal.phone}</a>
          </p>
        ),
        proposal.email && (
          <p key="email">
            <a href={`mailto:${proposal.email}`}>{proposal.email}</a>
          </p>
        ),
      ].filter(Boolean)
    : [];
  return (
    <div className="client proposal-phase">
      <SiteHeader
        office={page.office}
        painel={!!page.staff}
        person={page.staff ? person : null}
        onSignOut={page.staff ? onSignOut : undefined}
      />
      <div className="cwrap">
        <header className="project-heading proposal-heading">
          <p className="project-kind">{t("proposal.page.kicker")}</p>
          <h1 className="project-title">{page.name}</h1>
        </header>
        <div className="proposal-layout">
          <div className="proposal-layout__main">
            {proposal ? (
              <ProposalLetter proposal={proposal} office={page.office} />
            ) : (
              <p className="proposal-none">{t("proposal.page.none")}</p>
            )}
          </div>
          {proposal && (
            <aside className="proposal-layout__side">
              <a className="b b--primary" href={`${proposal.pdf_url}&download=true`}>
                {t("proposal.page.download")}
              </a>
              {contact.length > 0 && (
                <div className="proposal-contact">
                  <h2>{t("proposal.page.contact")}</h2>
                  <p>
                    <strong>{page.office.name}</strong>
                  </p>
                  {contact}
                </div>
              )}
            </aside>
          )}
        </div>
        <SiteFooter office={page.office.name} className="client-footer" />
      </div>
      {page.staff && <StaffBar page={page} ready={ready} onChanged={onChanged} />}
      <Toaster />
    </div>
  );
}
