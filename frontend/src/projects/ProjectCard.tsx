import { useTranslation } from "react-i18next";

import { Cover } from "./Cover";
import { ProjectMenu } from "./ProjectMenu";
import { type ProjectSummary } from "./projects";
import styles from "./projects.module.css";

function Progress({ project }: { project: ProjectSummary }) {
  const { t } = useTranslation();
  const total = project.stage_count;
  const done = project.status === "completed";
  const current = done ? total : Math.min(project.current_position ?? 0, total);
  const caption = done ? t("projects.done") : total ? t("projects.stageCaption") : t("projects.stagesCaption");
  const title = done
    ? null
    : !total
      ? t("projects.noStages")
      : (project.current_stage_title ?? t("projects.notStarted"));
  return (
    <div className={styles.progress}>
      <div className={styles.progressHead}>
        <span>{caption}</span>
        {total > 0 && (
          <span className={styles.count} aria-label={t("projects.stage", { current, total })}>
            {current} / {total}
          </span>
        )}
      </div>
      {title && <p className={styles.stageTitle}>{title}</p>}
      {total > 0 && (
        <div className={styles.bar} style={{ "--n": total } as React.CSSProperties} aria-hidden="true">
          {Array.from({ length: total }, (_, i) => (
            <i key={i} data-state={done || i + 1 < current ? "done" : i + 1 === current ? "current" : undefined} />
          ))}
        </div>
      )}
    </div>
  );
}

/** A project in the list. Times are the office's, wherever the viewer is. */
export function ProjectCard({ project, timeZone }: { project: ProjectSummary; timeZone: string }) {
  const { t, i18n } = useTranslation();
  // Numeric dates, as in the prototype: 15/10/2026 and 17/10/2026, 16:00.
  const day = new Intl.DateTimeFormat(i18n.language, { timeZone, day: "2-digit", month: "2-digit", year: "numeric" });
  const meeting = new Intl.DateTimeFormat(i18n.language, {
    timeZone,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  const updated = project.last_activity_at ?? project.created_at;
  return (
    <li className={styles.card} data-testid="project-card">
      <Cover project={project} className={styles.cardCover} />
      {project.status === "draft" && <span className={styles.draftTag}>{t("projectStatus.draft")}</span>}
      <ProjectMenu project={project} />
      <div className={styles.identity}>
        <h3 className={styles.name}>
          {/* The whole card opens the client's page (the pencil stays on top). */}
          <a className={styles.cardLink} href={`/${project.slug}`}>
            {project.name}
          </a>
        </h3>
        <p className={styles.client}>
          <span>{project.client_name}</span>
          <span>{project.project_type_label}</span>
        </p>
      </div>
      <Progress project={project} />
      <div className={styles.meta}>
        <small>{t("projects.nextMeeting")}</small>
        {project.next_meeting ? (
          <span title={project.next_meeting.title}>{meeting.format(new Date(project.next_meeting.starts_at))}</span>
        ) : (
          <span className={styles.muted}>{t("projects.noMeeting")}</span>
        )}
      </div>
      <p className={styles.updated}>
        <small>{t("projects.updated")}</small> {day.format(new Date(updated))}
      </p>
    </li>
  );
}
