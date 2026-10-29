// A project's page while it is a proposal (A42): the proposal presented for the
// screen (the formal letter is its PDF), the office's contact as the next step,
// and nothing of the work, which hasn't started. Staff get a bar to change the
// proposal or mark it accepted.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api, call, type Schemas } from "../api/client";
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

type Proposal = Schemas["ProposalOut"];

function Paragraphs({ text }: { text: string }) {
  return (
    <>
      {text
        .split(/\n{2,}/)
        .map((block) => block.trim())
        .filter(Boolean)
        .map((block, i) => (
          <p key={i}>{block}</p>
        ))}
    </>
  );
}

/** The office's WhatsApp link: its WhatsApp number (a Brazilian one without the
 *  country code gets +55), else its phone when that is a Brazilian mobile. None
 *  for a landline, which may have no WhatsApp. */
export function whatsappLink(whatsapp: string, phone: string): string | null {
  const own = whatsapp.replace(/\D/g, "");
  if (own) return `https://wa.me/${own.length <= 11 && !whatsapp.trim().startsWith("+") ? `55${own}` : own}`;
  let digits = phone.replace(/\D/g, "");
  if (digits.length === 13 && digits.startsWith("55")) digits = digits.slice(2);
  return digits.length === 11 && digits[2] === "9" ? `https://wa.me/55${digits}` : null;
}

function Presentation({ proposal, office }: { proposal: Proposal; office: string }) {
  const { t } = useTranslation();
  const pdf = `${proposal.pdf_url}&download=true`;
  const whatsapp = whatsappLink(proposal.whatsapp, proposal.phone);
  const facts: Array<[string, string]> = [
    ...(proposal.fee ? [[t("proposal.page.fee"), proposal.fee] as [string, string]] : []),
    ...(proposal.payments.length
      ? [[t("proposal.page.payment"), t("proposal.page.paymentCount", { count: proposal.payments.length })] as [string, string]]
      : []),
    ...(proposal.services.length
      ? [[t("proposal.page.included"), t("proposal.page.servicesCount", { count: proposal.services.length })] as [string, string]]
      : []),
  ];
  return (
    <>
      <div className="proposal-opening">
        <div className="proposal-opening__text">
          <p className="proposal-date">{proposal.date_line}</p>
          <div className="proposal-intro">
            <p className="proposal-to">{t("proposal.pdf.greeting")}</p>
            <Paragraphs text={proposal.intro} />
          </div>
        </div>
        <aside className="proposal-opening__side">
          <dl className="details-list">
            {facts.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </aside>
      </div>

      {proposal.services.length > 0 && (
        <section className="proposal-section" aria-labelledby="proposal-services">
          <h2 id="proposal-services" className="proposal-section__title">
            {t("proposal.page.services")}
          </h2>
          <ol className="proposal-services">
            {proposal.services.map((service, i) => (
              <li key={i} className="proposal-service">
                <span className="proposal-service__n" aria-hidden="true">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3>{service.title}</h3>
                <Paragraphs text={service.description} />
              </li>
            ))}
          </ol>
          {proposal.not_included.length > 0 && (
            <div className="proposal-excluded">
              <h3>{t("proposal.page.notIncluded")}</h3>
              <ul>
                {proposal.not_included.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {(proposal.fee || proposal.payments.length > 0) && (
        <section className="proposal-section" aria-labelledby="proposal-fees">
          <h2 id="proposal-fees" className="proposal-section__title">
            {t("proposal.page.fees")}
          </h2>
          <div className="proposal-fees">
            {proposal.fee && (
              <div className="proposal-fee">
                <p className="proposal-fee__amount">{proposal.fee}</p>
                {proposal.fee_in_words && <p className="proposal-fee__words">({proposal.fee_in_words})</p>}
              </div>
            )}
            {proposal.payments.length > 0 && (
              <ol className="proposal-payments">
                {proposal.payments.map((payment, i) => (
                  <li key={i}>
                    <span className="proposal-payments__n">{t("proposal.page.instalment", { n: i + 1 })}</span>
                    <span className="proposal-payments__when">{payment.when}</span>
                    <strong>{payment.amount}</strong>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </section>
      )}

      {proposal.notes && (
        <section className="proposal-section proposal-notes" aria-labelledby="proposal-notes">
          <h2 id="proposal-notes" className="proposal-section__title">
            {t("proposal.page.notes")}
          </h2>
          <Paragraphs text={proposal.notes} />
        </section>
      )}

      <section className="proposal-next" aria-labelledby="proposal-next">
        <div className="proposal-next__text">
          <h2 id="proposal-next">{t("proposal.page.nextTitle")}</h2>
          <p>{t("proposal.page.nextText", { office })}</p>
          <dl className="proposal-next__who">
            {proposal.signatory && (
              <div>
                <dt>{t("proposal.page.signedBy")}</dt>
                <dd>{proposal.signatory}</dd>
              </div>
            )}
            {proposal.address && (
              <div>
                <dt>{t("proposal.page.address")}</dt>
                <dd>{proposal.address}</dd>
              </div>
            )}
          </dl>
        </div>
        <div className="proposal-next__actions">
          {whatsapp && (
            <a className="b b--primary" href={whatsapp} target="_blank" rel="noopener">
              {t("proposal.page.whatsapp")}
            </a>
          )}
          {proposal.phone && (
            <a className={whatsapp ? "b" : "b b--primary"} href={`tel:${proposal.phone.replace(/[^\d+]/g, "")}`}>
              {t("proposal.page.call")} · {proposal.phone}
            </a>
          )}
          {proposal.email && (
            <a className="b" href={`mailto:${proposal.email}`}>
              {t("proposal.page.email")}
            </a>
          )}
          <a className="b" href={pdf}>
            {t("proposal.page.download")}
          </a>
        </div>
      </section>
    </>
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
  return (
    <div className="client proposal-phase">
      <SiteHeader
        office={page.office}
        painel={!!page.staff}
        person={page.staff ? person : null}
        onSignOut={page.staff ? onSignOut : undefined}
      />
      <div className="cwrap">
        <div className="proposal-top">
          <header className="project-heading proposal-heading">
            <p className="project-kind">{t("proposal.page.kicker")}</p>
            <h1 className="project-title">{page.name}</h1>
            {proposal && <p className="proposal-for">{t("proposal.page.for", { name: proposal.client_name })}</p>}
          </header>
          {proposal && (
            <a className="b b--primary proposal-download" href={`${proposal.pdf_url}&download=true`}>
              <Icon name="download" />
              {t("proposal.page.download")}
            </a>
          )}
        </div>
        {proposal ? (
          <Presentation proposal={proposal} office={page.office.name} />
        ) : (
          <p className="proposal-none">{t("proposal.page.none")}</p>
        )}
        <SiteFooter office={page.office.name} className="client-footer" />
      </div>
      {proposal && !page.staff && (
        <a className="b b--primary proposal-download proposal-download--pinned" href={`${proposal.pdf_url}&download=true`}>
          <Icon name="download" />
          {t("proposal.page.download")}
        </a>
      )}
      {page.staff && <StaffBar page={page} ready={ready} onChanged={onChanged} />}
      <Toaster />
    </div>
  );
}
