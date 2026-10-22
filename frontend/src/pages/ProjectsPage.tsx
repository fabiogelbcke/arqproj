import { useId, useMemo, useRef, useState } from "react";
import { Input, SearchField } from "react-aria-components";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";

import { DriveNotice } from "../drive/DriveNotice";
import { FirstSteps } from "../drive/FirstSteps";
import { NewProjectDialog } from "../projects/NewProjectDialog";
import { ProjectCard } from "../projects/ProjectCard";
import {
  SORTS,
  compareProjects,
  loadSort,
  matches,
  projectTypes,
  saveSort,
  sortFromValue,
  sortValue,
  useProjects,
  type ProjectSummary,
  type Sort,
} from "../projects/projects";
import styles from "../projects/projects.module.css";
import { useMe } from "../session/session";
import { Button } from "../ui/Button";
import { ChipGroup } from "../ui/ChipGroup";
import { ErrorNotice } from "../ui/ErrorNotice";
import { toast } from "../ui/Toast";
import pageStyles from "./pages.module.css";

const ALL_TYPES = "all";

// Completed projects shown before "Ver todos": two rows of four.
const COMPLETED_SHOWN = 8;

/** A group of cards under its bar: the name, then how many (painel redesign:
 *  "Em andamento" and "Concluídos" alike, both open). With `limit`, the first
 *  ones only, and "Ver todos (n)" for the rest. */
function Group({
  id,
  className,
  title,
  count,
  countLabel,
  projects,
  timeZone,
  limit,
}: {
  id: string;
  className: string | undefined;
  title: string;
  count: string;
  countLabel?: string;
  projects: ProjectSummary[];
  timeZone: string;
  limit?: number;
}) {
  const { t } = useTranslation();
  const [all, setAll] = useState(false);
  const listId = useId();
  const cut = limit !== undefined && projects.length > limit;
  const shown = cut && !all ? projects.slice(0, limit) : projects;
  return (
    <section className={`${styles.group} ${className ?? ""}`} aria-labelledby={id}>
      <div className={styles.groupHead}>
        <h2 id={id}>{title}</h2>
        <span className={styles.groupCount} aria-label={countLabel}>
          {count}
        </span>
      </div>
      <ul className={styles.rows} id={listId}>
        {shown.map((project) => (
          <ProjectCard key={project.id} project={project} timeZone={timeZone} />
        ))}
      </ul>
      {cut && (
        <Button
          size="small"
          shape="pill"
          className={styles.showAll}
          aria-controls={listId}
          aria-expanded={all}
          onPress={() => setAll(!all)}
        >
          {all ? t("projects.showFewer") : t("projects.showAll", { count: projects.length })}
        </Button>
      )}
    </section>
  );
}

/** Before the first project: faded cards where the projects will be, and the way
 *  to make one. The page's tools wait until there is something to search. */
function NoProjectsYet() {
  const { t } = useTranslation();
  return (
    <section className={styles.emptyState} aria-labelledby="projects-empty">
      <GhostCards />
      <div className={styles.emptyText}>
        <h2 id="projects-empty">{t("projects.emptyTitle")}</h2>
        <p>{t("projects.emptyBody")}</p>
        <NewProjectDialog
          trigger={{ label: t("projects.new"), className: styles.emptyAction ?? "" }}
          onCreated={(project) => toast(t("newProject.created", { name: project.name }))}
        />
      </div>
    </section>
  );
}

/** Faded cards in the list's shape: where projects will be, or are loading. */
function GhostCards() {
  return (
    <ul className={styles.ghosts} aria-hidden="true">
      {[0, 1, 2, 3].map((n) => (
        <li key={n} className={styles.ghost}>
          <i />
          <b />
          <b />
          <b />
        </li>
      ))}
    </ul>
  );
}

export function ProjectsPage() {
  const { t, i18n } = useTranslation();
  const projects = useProjects();
  const me = useMe();
  const timeZone = me.data?.tenant_timezone ?? "America/Sao_Paulo";
  // The search and the type are in the address (?q=…&type=…): back from a
  // project, a reload or a shared link keeps them. Typing replaces the entry
  // rather than adding one per letter.
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const chosenType = params.get("type") ?? ALL_TYPES;
  const setParam = (name: string, value: string, empty: string) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value === empty) next.delete(name);
        else next.set(name, value);
        return next;
      },
      { replace: true },
    );
  const setQuery = (value: string) => setParam("q", value, "");
  const setType = (value: string) => setParam("type", value, ALL_TYPES);
  const searchBox = useRef<HTMLInputElement>(null);
  // Phones: one group at a time, chosen with two tabs (desktop shows both).
  const [phoneGroup, setPhoneGroup] = useState<"active" | "completed">("active");
  const [sort, setSort] = useState<Sort>(loadSort);
  const sortId = useId();

  const changeSort = (next: Sort) => {
    setSort(next);
    saveSort(next);
  };
  // A chip for each type the office has projects of; with one type, no chips.
  // Built-in types have a short name for it ("Interiores"); others, their own.
  const types = useMemo(
    () =>
      projectTypes(projects.data ?? [], i18n.language, (key, label) =>
        t(`projectTypeShort.${key}`, { defaultValue: label }),
      ),
    [projects.data, i18n.language, t],
  );
  // The chosen type's last project archived: every project again.
  const type = types.some((option) => option.id === chosenType) ? chosenType : ALL_TYPES;
  const shown = useMemo(
    () =>
      (projects.data ?? [])
        .filter((project) => matches(project, query) && (type === ALL_TYPES || project.project_type === type))
        .sort(compareProjects(sort, i18n.language)),
    [projects.data, query, type, sort, i18n.language],
  );
  // No drafts for now (A35); one left in the database is listed with the live ones.
  const active = shown.filter((p) => p.status === "active" || p.status === "draft");
  const completed = shown.filter((p) => p.status === "completed");
  const hasAny = (projects.data?.length ?? 0) > 0;
  const filtering = query.trim() !== "" || type !== ALL_TYPES;

  return (
    <>
      <div className={styles.head}>
        {/* The breadcrumb says where you are; the title is for screen readers. */}
        <p className={styles.kicker}>
          {me.data?.tenant_name} / {t("projects.kicker")}
        </p>
        <h1 className="sr-only">{t("projects.title")}</h1>
        {hasAny && (
          <>
            <div className={styles.groupTabs} role="group" aria-label={t("projects.groups")}>
              <button type="button" aria-pressed={phoneGroup === "active"} onClick={() => setPhoneGroup("active")}>
                {t("projects.groupActive")} {active.length > 0 && <span>{active.length}</span>}
              </button>
              <button type="button" aria-pressed={phoneGroup === "completed"} onClick={() => setPhoneGroup("completed")}>
                {t("projects.groupCompleted")} {completed.length > 0 && <span>{completed.length}</span>}
              </button>
            </div>
            <div className={styles.tools}>
              {/* Phones: a floating pill at the bottom, beside the + (iOS Contacts). */}
              <SearchField className={styles.search} value={query} onChange={setQuery} aria-label={t("projects.search")}>
                <span className={styles.searchIcon} aria-hidden="true" />
                <Input ref={searchBox} className={styles.searchInput} placeholder={t("projects.searchPlaceholder")} />
              </SearchField>
              <div className={styles.sort}>
                <label htmlFor={sortId}>{t("projects.sortBy")}</label>
                {/* The order and its direction in one choice: "Nome: A–Z". */}
                <select
                  id={sortId}
                  className={styles.select}
                  value={sortValue(sort)}
                  onChange={(event) => changeSort(sortFromValue(event.target.value))}
                >
                  {SORTS.map((option) => (
                    <option key={sortValue(option)} value={sortValue(option)}>
                      {t(`projects.sort.${option.key}_${option.direction}`)}
                    </option>
                  ))}
                </select>
              </div>
              <NewProjectDialog onCreated={(project) => toast(t("newProject.created", { name: project.name }))} />
            </div>
            {types.length > 1 && (
              <ChipGroup
                className={styles.typeChips}
                label={t("projects.types")}
                chips={[{ id: ALL_TYPES, label: t("projects.allTypes") }, ...types]}
                value={type}
                onChange={setType}
              />
            )}
          </>
        )}
      </div>
      <DriveNotice />
      <FirstSteps />
      {/* Screen readers hear how many a search or a chip leaves (WCAG 4.1.3). */}
      <p className="sr-only" role="status">
        {projects.data && filtering ? t("projects.resultCount", { count: shown.length }) : ""}
      </p>
      {projects.error ? (
        <ErrorNotice error={projects.error} />
      ) : !projects.data ? (
        <div className={styles.loading} aria-busy="true">
          <p className="sr-only">{t("app.loading")}</p>
          <GhostCards />
        </div>
      ) : !hasAny ? (
        <NoProjectsYet />
      ) : shown.length === 0 ? (
        <div className={styles.noResults}>
          <p className={pageStyles.lead}>
            {query.trim() ? t("projects.noResults", { query }) : t("projects.noTypeResults")}
          </p>
          {query.trim() && (
            <Button
              size="small"
              shape="pill"
              onPress={() => {
                setQuery("");
                searchBox.current?.focus(); // the button goes with the message
              }}
            >
              {t("projects.clearSearch")}
            </Button>
          )}
        </div>
      ) : (
        <div className={styles.groups} data-phone-group={phoneGroup}>
          {active.length > 0 ? (
            <Group
              id="group-active"
              className={styles.activeGroup}
              title={t("projects.groupActive")}
              count={t("projects.groupCount", { shown: active.length, total: shown.length })}
              countLabel={t("projects.groupCountLabel", { shown: active.length, total: shown.length })}
              projects={active}
              timeZone={timeZone}
            />
          ) : (
            <p className={`${pageStyles.lead} ${styles.phoneEmpty}`} data-group="active">
              {t("projects.noneActive")}
            </p>
          )}
          {completed.length > 0 ? (
            <Group
              id="group-completed"
              className={styles.completedGroup}
              title={t("projects.groupCompleted")}
              count={String(completed.length)}
              projects={completed}
              timeZone={timeZone}
              // While searching, every match shows: a hidden one would look missing.
              limit={query.trim() ? undefined : COMPLETED_SHOWN}
            />
          ) : (
            <p className={`${pageStyles.lead} ${styles.phoneEmpty}`} data-group="completed">
              {t("projects.noneCompleted")}
            </p>
          )}
        </div>
      )}
    </>
  );
}
