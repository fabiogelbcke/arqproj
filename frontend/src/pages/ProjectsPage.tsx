import { useId, useMemo, useState } from "react";
import { Input, SearchField } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { DriveNotice } from "../drive/DriveNotice";
import { FirstSteps } from "../drive/FirstSteps";
import { NewProjectDialog } from "../projects/NewProjectDialog";
import { ProjectCard } from "../projects/ProjectCard";
import {
  SORT_KEYS,
  compareProjects,
  defaultDirection,
  loadSort,
  matches,
  saveSort,
  useProjects,
  type ProjectSummary,
  type Sort,
  type SortKey,
} from "../projects/projects";
import styles from "../projects/projects.module.css";
import { useMe } from "../session/session";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import pageStyles from "./pages.module.css";

function Group({
  id,
  title,
  count,
  countLabel,
  projects,
  timeZone,
}: {
  id: string;
  title: string;
  count: string;
  countLabel?: string;
  projects: ProjectSummary[];
  timeZone: string;
}) {
  return (
    <section className={styles.group} aria-labelledby={id}>
      <div className={styles.groupHead}>
        <h2 id={id}>{title}</h2>
        <span className={styles.groupCount} aria-label={countLabel}>
          {count}
        </span>
      </div>
      <ul className={styles.rows}>
        {projects.map((project) => (
          <ProjectCard key={project.id} project={project} timeZone={timeZone} />
        ))}
      </ul>
    </section>
  );
}

/** Completed projects, folded away until asked for. */
function CompletedGroup({ projects, timeZone }: { projects: ProjectSummary[]; timeZone: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const listId = useId();
  return (
    <section className={styles.group}>
      <div className={styles.groupHead}>
        <h2>
          <button
            type="button"
            className={styles.more}
            aria-expanded={open}
            aria-controls={listId}
            onClick={() => setOpen(!open)}
          >
            <span aria-hidden="true" className={styles.chevron} />
            {t("projects.groupCompleted")}
          </button>
        </h2>
        <span className={styles.groupCount}>{projects.length}</span>
      </div>
      <ul className={styles.rows} id={listId} hidden={!open}>
        {projects.map((project) => (
          <ProjectCard key={project.id} project={project} timeZone={timeZone} />
        ))}
      </ul>
    </section>
  );
}

export function ProjectsPage() {
  const { t, i18n } = useTranslation();
  const projects = useProjects();
  const me = useMe();
  const timeZone = me.data?.tenant_timezone ?? "America/Sao_Paulo";
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>(loadSort);
  const [created, setCreated] = useState<string | null>(null);
  const sortId = useId();

  const changeSort = (next: Sort) => {
    setSort(next);
    saveSort(next);
  };
  const shown = useMemo(
    () =>
      (projects.data ?? [])
        .filter((project) => matches(project, query))
        .sort(compareProjects(sort, i18n.language)),
    [projects.data, query, sort, i18n.language],
  );
  const active = shown.filter((p) => p.status === "active");
  const drafts = shown.filter((p) => p.status === "draft");
  const completed = shown.filter((p) => p.status === "completed");
  const hasAny = (projects.data?.length ?? 0) > 0;

  return (
    <>
      <div className={styles.head}>
        <h1 className={pageStyles.display}>{t("projects.title")}</h1>
        <div className={styles.tools}>
          {hasAny && (
            <>
              <SearchField className={styles.search} value={query} onChange={setQuery} aria-label={t("projects.search")}>
                <Input className={styles.searchInput} placeholder={t("projects.searchPlaceholder")} />
              </SearchField>
              <div className={styles.sort}>
                <label htmlFor={sortId}>{t("projects.sortBy")}</label>
                <select
                  id={sortId}
                  className={styles.select}
                  value={sort.key}
                  onChange={(event) => {
                    const key = event.target.value as SortKey;
                    changeSort({ key, direction: defaultDirection(key) });
                  }}
                >
                  {SORT_KEYS.map((key) => (
                    <option key={key} value={key}>
                      {t(`projects.sort.${key}`)}
                    </option>
                  ))}
                </select>
                <Button
                  variant="ghost"
                  aria-label={t(sort.direction === "asc" ? "projects.ascending" : "projects.descending")}
                  onPress={() => changeSort({ ...sort, direction: sort.direction === "asc" ? "desc" : "asc" })}
                >
                  <span aria-hidden="true">{sort.direction === "asc" ? "↑" : "↓"}</span>
                </Button>
              </div>
            </>
          )}
          <NewProjectDialog onCreated={(project) => setCreated(project.name)} />
        </div>
      </div>
      <DriveNotice />
      <FirstSteps />
      {created && <p role="status">{t("newProject.created", { name: created })}</p>}
      {projects.error ? (
        <ErrorNotice error={projects.error} />
      ) : !projects.data ? (
        <p className={pageStyles.lead}>{t("app.loading")}</p>
      ) : !hasAny ? (
        <section className={pageStyles.empty} aria-labelledby="projects-empty">
          <h2 id="projects-empty">{t("projects.emptyTitle")}</h2>
          <p>{t("projects.emptyBody")}</p>
        </section>
      ) : shown.length === 0 ? (
        <p className={pageStyles.lead}>{t("projects.noResults", { query })}</p>
      ) : (
        <>
          {active.length > 0 && (
            <Group
              id="group-active"
              title={t("projects.groupActive")}
              count={t("projects.groupCount", { shown: active.length, total: shown.length })}
              countLabel={t("projects.groupCountLabel", { shown: active.length, total: shown.length })}
              projects={active}
              timeZone={timeZone}
            />
          )}
          {drafts.length > 0 && (
            <Group
              id="group-drafts"
              title={t("projects.groupDrafts")}
              count={String(drafts.length)}
              projects={drafts}
              timeZone={timeZone}
            />
          )}
          {completed.length > 0 && <CompletedGroup projects={completed} timeZone={timeZone} />}
        </>
      )}
    </>
  );
}
