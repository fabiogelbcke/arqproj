// The Portfólio tab: /painel/portfolio, behind the `portfolio` feature (A40).
// Whether the office's address shows the portfolio, its opening text, and the
// works in order; each opens in its editor (PortfolioEntryPage). A work starts
// from one of the office's projects or from nothing.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { plain, useProjects, type ProjectSummary } from "../projects/projects";
import { useMe } from "../session/session";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { DialogFrame } from "../ui/DialogFrame";
import { ErrorNotice } from "../ui/ErrorNotice";
import { IconButton } from "../ui/IconButton";
import { NameDialog } from "../ui/NameDialog";
import { Panel } from "../ui/Panel";
import { SearchBox } from "../ui/SearchBox";
import { TextAreaField } from "../ui/TextField";
import { toast, toastError } from "../ui/Toast";
import { ToggleSwitch } from "../ui/ToggleSwitch";
import {
  LIMITS,
  moved,
  useAddEntry,
  useOrderEntries,
  usePortfolio,
  useRemoveEntry,
  useSavePortfolio,
  type Entry,
  type Portfolio,
} from "./portfolio";
import styles from "./portfolio.module.css";

/** The office's address as visitors type it: this page's own host. */
export const officeAddress = () => window.location.host;

export function PortfolioPage() {
  const { t } = useTranslation();
  const me = useMe();
  const portfolio = usePortfolio();
  return (
    <div className={styles.page}>
      <div className={styles.head}>
        <p className={styles.kicker}>
          {me.data?.tenant_name} / {t("portfolio.kicker")}
        </p>
        <h1 className={styles.title}>{t("portfolio.title")}</h1>
        <p className={styles.lead}>{t("portfolio.lead", { address: officeAddress() })}</p>
      </div>
      {portfolio.error ? (
        <ErrorNotice error={portfolio.error} />
      ) : !portfolio.data ? (
        <p className={styles.hint}>{t("app.loading")}</p>
      ) : (
        <>
          <Publishing portfolio={portfolio.data} />
          <Works portfolio={portfolio.data} />
        </>
      )}
    </div>
  );
}

function Publishing({ portfolio }: { portfolio: Portfolio }) {
  const { t } = useTranslation();
  const save = useSavePortfolio();
  const [intro, setIntro] = useState(portfolio.intro);
  const shown = portfolio.entries.some((entry) => entry.photos.length > 0);
  const change = (body: { published?: boolean; intro?: string }, done: string) =>
    save.mutate(body, { onSuccess: () => toast(done), onError: (failure) => toastError(failure) });
  return (
    <Panel className={styles.section} aria-labelledby="portfolio-publishing">
      <h2 id="portfolio-publishing" className="sr-only">
        {t("portfolio.publishing")}
      </h2>
      <ToggleSwitch
        label={t("portfolio.publish")}
        isSelected={portfolio.published}
        isDisabled={save.isPending}
        onChange={(on) => change({ published: on }, t(on ? "portfolio.publishedDone" : "portfolio.unpublishedDone"))}
      >
        <span className={styles.switchLabel}>{t("portfolio.publish")}</span>
      </ToggleSwitch>
      <p className={styles.hint}>
        {t(portfolio.published ? "portfolio.publishedHint" : "portfolio.unpublishedHint", { address: officeAddress() })}{" "}
        <a href={portfolio.published ? "/" : "/?previa=1"} target="_blank" rel="noreferrer">
          {t(portfolio.published ? "portfolio.view" : "portfolio.preview")}
        </a>
      </p>
      {portfolio.published && !shown && <p className={styles.warning}>{t("portfolio.nothingShown")}</p>}
      <TextAreaField
        label={t("portfolio.intro")}
        description={t("portfolio.introHint")}
        placeholder={t("portfolio.introPlaceholder")}
        value={intro}
        onChange={setIntro}
        maxLength={LIMITS.intro}
        rows={3}
      />
      <Button
        size="small"
        className={styles.save}
        isDisabled={save.isPending || intro.trim() === portfolio.intro}
        onPress={() => change({ intro }, t("portfolio.saved"))}
      >
        {t("portfolio.save")}
      </Button>
    </Panel>
  );
}

function Works({ portfolio }: { portfolio: Portfolio }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const add = useAddEntry();
  const order = useOrderEntries();
  const [adding, setAdding] = useState<"project" | "new" | null>(null);
  const full = portfolio.entries.length >= LIMITS.entries;
  // A new work opens in its editor, to choose its photos.
  const created = (before: Portfolio, after: Portfolio) => {
    const known = new Set(before.entries.map((entry) => entry.id));
    const entry = after.entries.find((item) => !known.has(item.id));
    setAdding(null);
    if (entry) navigate(`/portfolio/${entry.id}${adding === "project" ? "?fotos=projeto" : ""}`);
  };
  const create = (body: { title: string; project_id?: string }) =>
    add.mutate(
      { place: "", description: "", ...body },
      { onSuccess: (after) => created(portfolio, after), onError: (failure) => toastError(failure) },
    );
  return (
    <section className={styles.section} aria-labelledby="portfolio-works">
      <div className={styles.sectionHead}>
        <h2 id="portfolio-works">
          {t("portfolio.works")} <span className={styles.count}>{portfolio.entries.length}</span>
        </h2>
        <div className={styles.actions}>
          <Button size="small" variant="primary" isDisabled={full} onPress={() => setAdding("project")}>
            {t("portfolio.addFromProject")}
          </Button>
          <Button size="small" isDisabled={full} onPress={() => setAdding("new")}>
            {t("portfolio.addNew")}
          </Button>
        </div>
      </div>
      {portfolio.entries.length === 0 ? (
        <p className={styles.empty}>{t("portfolio.noWorks")}</p>
      ) : (
        <ol className={styles.works}>
          {portfolio.entries.map((entry, index) => (
            <Work
              key={entry.id}
              entry={entry}
              first={index === 0}
              last={index === portfolio.entries.length - 1}
              busy={order.isPending}
              onMove={(step) =>
                order.mutate(moved(portfolio.entries, index, step), { onError: (failure) => toastError(failure) })
              }
            />
          ))}
        </ol>
      )}
      {adding === "project" && (
        <ProjectChoice
          taken={new Set(portfolio.entries.map((entry) => entry.project_id).filter(Boolean) as string[])}
          busy={add.isPending}
          onChoose={(project) => create({ title: project.name.slice(0, LIMITS.title), project_id: project.id })}
          onClose={() => setAdding(null)}
        />
      )}
      {adding === "new" && (
        <NameDialog
          title={t("portfolio.newTitle")}
          label={t("portfolio.titleLabel")}
          initial=""
          confirm={t("portfolio.create")}
          maxLength={LIMITS.title}
          busy={add.isPending}
          onConfirm={(title) => create({ title })}
          onCancel={() => setAdding(null)}
        />
      )}
    </section>
  );
}

export function describe(entry: Entry): string {
  return [entry.place, entry.year].filter(Boolean).join(" · ");
}

function Work({
  entry,
  first,
  last,
  busy,
  onMove,
}: {
  entry: Entry;
  first: boolean;
  last: boolean;
  busy: boolean;
  onMove: (step: number) => void;
}) {
  const { t } = useTranslation();
  const remove = useRemoveEntry();
  const [confirming, setConfirming] = useState(false);
  const cover = entry.photos[0];
  const meta = describe(entry);
  return (
    <li className={styles.work}>
      <Link className={styles.workMain} to={`/portfolio/${entry.id}`}>
        {cover ? (
          <img className={styles.thumb} src={`${cover.url}?size=card`} alt="" loading="lazy" />
        ) : (
          <span className={styles.thumb} aria-hidden="true" />
        )}
        <span className={styles.workText}>
          <span className={styles.workTitle}>{entry.title}</span>
          {meta && <span className={styles.workMeta}>{meta}</span>}
          <span className={entry.photos.length ? styles.workMeta : styles.warning}>
            {entry.photos.length
              ? t("portfolio.photoCount", { count: entry.photos.length })
              : t("portfolio.noPhotos")}
          </span>
        </span>
      </Link>
      <span className={styles.tools}>
        <IconButton label={t("portfolio.moveUp")} isDisabled={first || busy} onPress={() => onMove(-1)}>
          ↑
        </IconButton>
        <IconButton label={t("portfolio.moveDown")} isDisabled={last || busy} onPress={() => onMove(1)}>
          ↓
        </IconButton>
        <Button size="small" variant="ghost" onPress={() => setConfirming(true)}>
          {t("portfolio.remove")}
        </Button>
      </span>
      {confirming && (
        <ConfirmDialog
          title={t("portfolio.removeTitle")}
          text={t("portfolio.removeText", { title: entry.title })}
          confirm={t("portfolio.remove")}
          danger
          busy={remove.isPending}
          onConfirm={() =>
            remove.mutate(entry.id, {
              onSuccess: () => {
                setConfirming(false);
                toast(t("portfolio.removed", { title: entry.title }));
              },
              onError: (failure) => toastError(failure),
            })
          }
          onCancel={() => setConfirming(false)}
        />
      )}
    </li>
  );
}

/** The office's projects to draw a work from; those already in it say so. */
export function ProjectChoice({
  taken,
  busy,
  onChoose,
  onClose,
  title,
}: {
  taken: Set<string>;
  busy: boolean;
  onChoose: (project: ProjectSummary) => void;
  onClose: () => void;
  title?: string;
}) {
  const { t } = useTranslation();
  const projects = useProjects();
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const words = plain(query).trim().split(/\s+/).filter(Boolean);
    return (projects.data ?? []).filter((project) => {
      const haystack = plain(`${project.name} ${project.client_name}`);
      return words.every((word) => haystack.includes(word));
    });
  }, [projects.data, query]);
  return (
    <DialogFrame title={title ?? t("portfolio.chooseProject")} onClose={onClose}>
      <div className={styles.dialogBody}>
        <SearchBox
          label={t("portfolio.searchProjects")}
          placeholder={t("portfolio.searchPlaceholder")}
          value={query}
          onChange={setQuery}
        />
        {projects.error ? (
          <ErrorNotice error={projects.error} />
        ) : !projects.data ? (
          <p className={styles.hint}>{t("app.loading")}</p>
        ) : shown.length === 0 ? (
          <p className={styles.hint}>{t("portfolio.noProjects")}</p>
        ) : (
          <ul className={styles.choices}>
            {shown.map((project) => (
              <li key={project.id}>
                <button
                  type="button"
                  className={styles.choice}
                  disabled={busy}
                  onClick={() => onChoose(project)}
                >
                  {project.cover_url ? (
                    <img className={styles.choiceThumb} src={project.cover_url} alt="" loading="lazy" />
                  ) : (
                    <span className={styles.choiceThumb} aria-hidden="true" />
                  )}
                  <span className={styles.workText}>
                    <span className={styles.workTitle}>{project.name}</span>
                    <span className={styles.workMeta}>
                      {project.client_name}
                      {taken.has(project.id) ? ` · ${t("portfolio.alreadyIn")}` : ""}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </DialogFrame>
  );
}
