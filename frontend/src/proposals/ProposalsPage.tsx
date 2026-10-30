// The Propostas tab (A42): /painel/propostas. The projects page's toolbar (a
// search and "Nova proposta"), then the office's proposals in three groups: open
// ("Ativas"), accepted (projects now) and declined ("Recusadas", archived while
// a proposal), each a list with its total. A proposal opens on its page, as the
// client sees it; one never saved opens in the generator, to be written.
import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router";

import { NewProjectButton } from "../projects/NewProjectDialog";
import { plain } from "../projects/projects";
import { useMe } from "../session/session";
import { ActionMenu } from "../ui/ActionMenu";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { MoreIcon } from "../ui/MoreIcon";
import { SearchBox } from "../ui/SearchBox";
import { toast, toastError } from "../ui/Toast";
import { formatAmount, useDeclineProposal, useProposalList, type ProposalRow } from "./proposals";
import styles from "./proposals.module.css";

const GROUPS = [
  { state: "open", title: "proposal.list.open", total: "proposal.list.totalOpen" },
  { state: "accepted", title: "proposal.list.accepted", total: "proposal.list.totalAccepted" },
  { state: "declined", title: "proposal.list.declined", total: null },
] as const;

function matches(row: ProposalRow, query: string): boolean {
  const haystack = plain(`${row.name} ${row.client_name}`);
  return plain(query).trim().split(/\s+/).filter(Boolean).every((word) => haystack.includes(word));
}

export function ProposalsPage() {
  const { t, i18n } = useTranslation();
  const me = useMe();
  const list = useProposalList();
  // The search is in the address (?q=…), as on the projects page.
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const setQuery = (value: string) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set("q", value);
        else next.delete("q");
        return next;
      },
      { replace: true },
    );
  const searchBox = useRef<HTMLInputElement>(null);
  const rows = useMemo(() => (list.data ?? []).filter((row) => matches(row, query)), [list.data, query]);
  const filtering = query.trim() !== "";
  const none = list.data?.length === 0;
  return (
    <>
      <div className={styles.listHead}>
        <p className={styles.kicker}>
          {me.data?.tenant_name} / {t("proposal.list.kicker")}
        </p>
        <h1 className="sr-only">{t("proposal.list.title")}</h1>
        {/* The tools wait until there is something to search. */}
        {list.data && !none && (
          <div className={styles.tools}>
            <SearchBox
              className={styles.search}
              inputRef={searchBox}
              label={t("proposal.list.search")}
              placeholder={t("proposal.list.searchPlaceholder")}
              value={query}
              onChange={setQuery}
            />
            <NewProjectButton kind="proposal" size="small" label={t("projects.newProposal")} className={styles.newProposal} />
          </div>
        )}
      </div>
      <p className="sr-only" role="status">
        {list.data && filtering ? t("proposal.list.resultCount", { count: rows.length }) : ""}
      </p>
      {list.error ? (
        <ErrorNotice error={list.error} />
      ) : !list.data ? (
        <p className={styles.hint}>{t("app.loading")}</p>
      ) : none ? (
        <NoProposalsYet />
      ) : filtering && rows.length === 0 ? (
        <div className={styles.noResults}>
          <p className={styles.hint}>{t("proposal.list.noResults", { query })}</p>
          <Button
            size="small"
            onPress={() => {
              setQuery("");
              searchBox.current?.focus();
            }}
          >
            {t("projects.clearSearch")}
          </Button>
        </div>
      ) : (
        GROUPS.map((group) => {
          const shown = rows.filter((row) => row.state === group.state);
          // An empty group of accepted or declined ones says nothing; "Ativas" says so,
          // unless a search left it empty.
          if (!shown.length && (group.state !== "open" || filtering)) return null;
          const total = shown.reduce((sum, row) => sum + (row.fee ?? 0), 0);
          return (
            <section key={group.state} className={styles.group} aria-labelledby={`proposals-${group.state}`}>
              <div className={styles.groupHead}>
                <h2 id={`proposals-${group.state}`} className={styles.groupTitle}>
                  {t(group.title)} <span className={styles.groupCount}>{shown.length}</span>
                </h2>
                {group.total && total > 0 && (
                  <p className={styles.groupTotal}>
                    {t(group.total, { amount: `R$ ${formatAmount(total, i18n.language)}` })}
                  </p>
                )}
              </div>
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

/** Before the first proposal: faded rows where they will be, what a proposal
 *  is, and the way to make one. */
function NoProposalsYet() {
  const { t } = useTranslation();
  return (
    <section className={styles.empty} aria-labelledby="proposals-empty">
      <ul className={styles.ghosts} aria-hidden="true">
        {[0, 1, 2].map((n) => (
          <li key={n}>
            <b />
            <i />
            <b />
          </li>
        ))}
      </ul>
      <div className={styles.emptyText}>
        <h2 id="proposals-empty">{t("proposal.list.emptyTitle")}</h2>
        <p>{t("proposal.list.lead")}</p>
        <NewProjectButton kind="proposal" label={t("projects.newProposal")} />
      </div>
    </section>
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
    <li className={styles.row} data-state={row.state}>
      {/* Saved: its page, as the client sees it (or the project, once accepted).
          Never saved: the generator, to write it. The whole row is the link. */}
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
        {row.version ? (
          t("proposal.list.version", { version: row.version, date: when })
        ) : (
          <span className={styles.tag}>{t("proposal.list.notWritten")}</span>
        )}
      </span>
      <span className={styles.rowFee} data-empty={row.fee ? undefined : true}>
        {row.fee ? `R$ ${formatAmount(row.fee, i18n.language)}` : "—"}
      </span>
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
