// A proposal on screen (A42), laid out like its PDF: the generator's preview of
// the file. Its words are the PDF's (backend/i18n, `proposal.pdf`). The client
// page presents the same content its own way (client/ProposalPhase).
import { useTranslation } from "react-i18next";

import type { Schemas } from "../api/client";
import styles from "./letter.module.css";

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

export function ProposalLetter({
  proposal,
  office,
}: {
  proposal: Proposal;
  office: { name: string; logo_url?: string | null };
}) {
  const { t, i18n } = useTranslation();
  const upper = (text: string) => text.toLocaleUpperCase(i18n.language);
  const footer = [
    proposal.address,
    proposal.phone,
    proposal.email && t("proposal.pdf.email", { email: proposal.email }),
  ].filter(Boolean);
  return (
    <article className={styles.paper} lang={i18n.language}>
      <header className={styles.brand}>
        {office.logo_url ? <img src={office.logo_url} alt={office.name} /> : <span>{upper(office.name)}</span>}
      </header>
      <p>{proposal.date_line}</p>
      <p className={styles.recipient}>{upper(proposal.client_name)}</p>
      <p>{t("proposal.pdf.greeting")}</p>
      <Paragraphs text={proposal.intro} />

      {proposal.services.length > 0 && (
        <section>
          <h2>{t("proposal.pdf.services")}</h2>
          <ol className={styles.services}>
            {proposal.services.map((service, i) => (
              <li key={i}>
                <h3>
                  {i + 1}. {upper(service.title)}
                </h3>
                <Paragraphs text={service.description} />
              </li>
            ))}
          </ol>
        </section>
      )}

      {proposal.fee && (
        <section>
          <h2>{t("proposal.pdf.fees")}</h2>
          <p>{t("proposal.pdf.feesText", { amount: proposal.fee, words: proposal.fee_in_words })}</p>
        </section>
      )}

      {proposal.payments.length > 0 && (
        <section>
          <h2 className={styles.underlined}>{t("proposal.pdf.payment")}</h2>
          <ul className={styles.lines}>
            {proposal.payments.map((payment, i) => (
              <li key={i}>
                {payment.amount} {payment.when}
              </li>
            ))}
          </ul>
        </section>
      )}

      {proposal.not_included.length > 0 && (
        <section>
          <h2>{t("proposal.pdf.notIncluded")}</h2>
          <ul className={styles.lines}>
            {proposal.not_included.map((line, i) => (
              <li key={i}>{upper(line)}</li>
            ))}
          </ul>
        </section>
      )}

      {proposal.notes && (
        <section>
          <h2>{t("proposal.pdf.notes")}</h2>
          <Paragraphs text={proposal.notes} />
        </section>
      )}

      <p className={styles.closing}>{t("proposal.pdf.closing")}</p>
      <p>{t("proposal.pdf.acceptance")}</p>
      <div className={styles.signatures}>
        <p>{upper(proposal.client_name)}</p>
        <p>{upper(proposal.signatory)}</p>
      </div>
      {footer.length > 0 && <footer className={styles.footer}>{footer.join(" - ")}</footer>}
    </article>
  );
}
