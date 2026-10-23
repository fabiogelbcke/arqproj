import { useState } from "react";
import { useTranslation } from "react-i18next";

import { CompletionBar } from "../ui/CompletionBar";
import { relativeDay } from "../ui/dates";
import { Cover } from "./Cover";
import { ClientEmailsDialog } from "./ClientEmailsDialog";
import { ProjectMenu } from "./ProjectMenu";
import { type ProjectSummary } from "./projects";
import styles from "./projects.module.css";

/** How many of its stages are completed, in any order: in words, and a thin bar. */
function Progress({ project }: { project: ProjectSummary }) {
  const { t } = useTranslation();
  const total = project.stage_count;
  const done = project.completed_stage_count;
  // A completed project too: the card sits under "Concluídos" already.
  const caption = total ? t("projects.stagesDone", { done, total }) : t("projects.noStages");
  return (
    <div className={styles.progress}>
      <div className={styles.progressHead}>
        <span>{caption}</span>
      </div>
      {total > 0 && <CompletionBar done={done} total={total} label={t("projects.stagesDone", { done, total })} />}
    </div>
  );
}

/** A project in the list. Times are the office's, wherever the viewer is. */
export function ProjectCard({ project, timeZone }: { project: ProjectSummary; timeZone: string }) {
  const { t, i18n } = useTranslation();
  // Meetings as numeric dates, as in the prototype: 17/10/2026, 16:00. The last
  // update as people say it ("há 3 dias"), the exact moment on hover.
  const meeting = new Intl.DateTimeFormat(i18n.language, {
    timeZone,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  const updated = project.last_activity_at ?? project.created_at;
  // An active project whose updates reach nobody: no address, or only unsubscribed ones.
  const needsEmails = project.status === "active" && !project.recipients.some((recipient) => recipient.subscribed);
  const [addingEmails, setAddingEmails] = useState(false);
  return (
    <li className={styles.card} data-testid="project-card" data-tour="project-card">
      <Cover project={project} className={styles.cardCover} />
      {project.status === "draft" && <span className={styles.draftTag}>{t("projectStatus.draft")}</span>}
      <ProjectMenu project={project} />
      <div className={styles.identity}>
        <h3 className={styles.name}>
          {/* The whole card opens the client's page (the "⋯" stays on top). */}
          <a className={styles.cardLink} href={`/${project.slug}`}>
            {project.name}
          </a>
        </h3>
        <p className={styles.client}>
          <span>{project.client_name}</span>
          <span>{project.project_type_label}</span>
        </p>
        {needsEmails && (
          // Nobody gets this project's updates (A32): a dialog to add them, on top
          // of the card's link. In the name's row, so the card keeps its five rows.
          <button type="button" className={styles.noEmails} onClick={() => setAddingEmails(true)}>
            <span aria-hidden="true">!</span>
            {t("projects.noClientEmail")}
            <span className={styles.noEmailsAction}>{t("projects.addClientEmail")}</span>
          </button>
        )}
      </div>
      {addingEmails && <ClientEmailsDialog project={project} onClose={() => setAddingEmails(false)} />}
      <Progress project={project} />
      <div className={styles.meta}>
        <small>{t("projects.nextMeeting")}</small>
        {project.next_meeting ? (
          <span title={project.next_meeting.title}>{meeting.format(new Date(project.next_meeting.starts_at))}</span>
        ) : (
          <span className={styles.muted}>{t("projects.noMeeting")}</span>
        )}
      </div>
      <p className={styles.updated} title={meeting.format(new Date(updated))}>
        <small>{t("projects.updated")}</small> {relativeDay(updated, new Date(), i18n.language, timeZone)}
      </p>
    </li>
  );
}
