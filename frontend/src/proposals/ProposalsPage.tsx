// The Propostas tab (A42): /painel/propostas. "Nova proposta", then the office's
// proposals in three groups: open ("Ativas"), accepted (projects now) and declined
// ("Recusadas", archived while a proposal). A proposal opens on its page, as the
// client sees it; one never saved opens in the generator, to be written.
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { NewProjectButton } from "../projects/NewProjectDialog";
import { useMe } from "../session/session";
import { ActionMenu } from "../ui/ActionMenu";
import { ErrorNotice } from "../ui/ErrorNotice";
import { MoreIcon } from "../ui/MoreIcon";
import { toast, toastError } from "../ui/Toast";
import { formatAmount, useDeclineProposal, useProposalList, type ProposalRow } from "./proposals";
import styles from "./proposals.module.css";

const GROUPS = [
  { state: "open", title: "proposal.list.open" },
  { state: "accepted", title: "proposal.list.accepted" },
  { state: "declined", title: "proposal.list.declined" },
] as const;

export function ProposalsPage() {
  const { t } = useTranslation();
  const me = useMe();
  const list = useProposalList();
  const rows = list.data ?? [];
  return (
    <>
      <div className={styles.listHead}>
        <p className={styles.kicker}>
          {me.data?.tenant_name} / {t("proposal.list.kicker")}
        </p>
        <h1 className="sr-only">{t("proposal.list.title")}</h1>
        <p className={styles.lead}>{t("proposal.list.lead")}</p>
        <NewProjectButton kind="proposal" label={t("projects.newProposal")} className={styles.newProposal} />
      </div>
      {list.error ? (
        <ErrorNotice error={list.error} />
      ) : !list.data ? (
        <p className={styles.lead}>{t("app.loading")}</p>
      ) : (
        GROUPS.map((group) => {
          const shown = rows.filter((row) => row.state === group.state);
          // An empty group of accepted or declined ones says nothing; "Ativas" says what to do.
          if (!shown.length && group.state !== "open") return null;
          return (
            <section key={group.state} className={styles.group} aria-labelledby={`proposals-${group.state}`}>
              <h2 id={`proposals-${group.state}`} className={styles.groupTitle}>
                {t(group.title)} <span className={styles.groupCount}>{shown.length}</span>
              </h2>
              {shown.length ? (
                <ul className={styles.rows}>
                  {shown.map((row) => (
                    <Row key={row.project_id} row={row} />
                  ))}
                </ul>
              ) : (
                <p className={styles.hint}>{t("proposal.list.noOpen")}</p>
              )}
            </section>
          );
        })
      )}
    </>
  );
}

function Row({ row }: { row: ProposalRow }) {
  const { t, i18n } = useTranslation();
  const me = useMe();
  const navigate = useNavigate();
  const decline = useDeclineProposal();
  const timeZone = me.data?.tenant_timezone ?? "America/Sao_Paulo";
  const writer = `/projetos/${row.project_id}/proposta`;
  const when = row.saved_at
    ? new Date(row.saved_at).toLocaleDateString(i18n.language, { timeZone })
    : null;
  const change = (declined: boolean) =>
    decline.mutate(
      { row, declined },
      {
        onSuccess: () => toast(t(declined ? "proposal.list.declinedDone" : "proposal.list.reopenedDone", { name: row.name })),
        onError: (failure) => toastError(failure),
      },
    );
  const items =
    row.state === "open"
      ? [
          { id: "edit", label: t("proposal.list.edit") },
          { id: "decline", label: t("proposal.list.decline") },
        ]
      : row.state === "declined"
        ? [{ id: "reopen", label: t("proposal.list.reopen") }]
        : [];
  const name = (
    <>
      <span className={styles.rowName}>{row.name}</span>
      <span className={styles.rowClient}>{row.client_name}</span>
    </>
  );
  return (
    <li className={styles.row}>
      {/* Saved: its page, as the client sees it (or the project, once accepted).
          Never saved: the generator, to write it. */}
      {row.version ? (
        <a className={styles.rowMain} href={`/${row.slug}`}>
          {name}
        </a>
      ) : (
        <Link className={styles.rowMain} to={writer}>
          {name}
        </Link>
      )}
      <span className={styles.rowMeta}>
        {row.version ? t("proposal.list.version", { version: row.version, date: when }) : t("proposal.list.notWritten")}
      </span>
      <span className={styles.rowFee}>{row.fee ? `R$ ${formatAmount(row.fee, i18n.language)}` : "—"}</span>
      {items.length > 0 ? (
        <ActionMenu
          label={t("proposal.list.actions", { name: row.name })}
          className={styles.rowMenu}
          items={items}
          onAction={(id) => {
            if (id === "edit") navigate(writer);
            else change(id === "decline");
          }}
        >
          <MoreIcon />
        </ActionMenu>
      ) : (
        <span className={styles.rowMenuSpace} aria-hidden="true" />
      )}
    </li>
  );
}
