// The client's project page, read-only (slice 2.3), after the fresh prototype's
// markup: its stylesheet (prototype.css) styles these same class names.
import { Suspense, lazy, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { flushSync } from "react-dom";

import { api, call, type Schemas } from "../api/client";
import { CompletionBar } from "../ui/CompletionBar";
import { HeaderMenu } from "../ui/HeaderMenu";
import { OfficeBrand } from "../ui/OfficeBrand";
import { PopoverDetails } from "../ui/PopoverDetails";
import { useDismiss } from "../ui/useDismiss";
import { Toaster, toast } from "../ui/Toast";
import { SiteFooter } from "../ui/UnioMark";
import { EditButton, openOnClick } from "./EditButton";
import { useBalancedColumns } from "./balance";
import { Subscribe } from "./Subscribe";
import { UpdatesBell } from "./Updates";
import type { StageEditParts } from "./StageEditing";
import {
  FilePreview,
  fileSize,
  FileToolbar,
  FileVersions,
  linkedFile,
  shownFiles,
  usePrefs,
  type FilePlace,
  type FileView,
} from "./FileTools";

// Staff editing code loads only once staff press "Editar" (A20): visitors never get it.
const DescriptionEditor = lazy(() => import("./Editors").then((m) => ({ default: m.DescriptionEditor })));
const NameEditor = lazy(() => import("./Editors").then((m) => ({ default: m.NameEditor })));
const DetailsEditor = lazy(() => import("./Editors").then((m) => ({ default: m.DetailsEditor })));
const MeetingEditor = lazy(() => import("./Editors").then((m) => ({ default: m.MeetingEditor })));
const RecipientsEditor = lazy(() => import("./Editors").then((m) => ({ default: m.RecipientsEditor })));
const AddStage = lazy(() => import("./StageEditing").then((m) => ({ default: m.AddStage })));
const StageProgress = lazy(() => import("./StageEditing").then((m) => ({ default: m.StageProgress })));
const CompleteProject = lazy(() => import("./StageEditing").then((m) => ({ default: m.CompleteProject })));
const ReorderStages = lazy(() => import("./StageEditing").then((m) => ({ default: m.ReorderStages })));
const StageEditForm = lazy(() => import("./StageEditing").then((m) => ({ default: m.StageEditForm })));
const StageDrop = lazy(() => import("./StageUploads").then((m) => ({ default: m.StageDrop })));
const FileMenu = lazy(() => import("./StageUploads").then((m) => ({ default: m.FileMenu })));
const CoverPicker = lazy(() => import("./CoverEditing").then((m) => ({ default: m.CoverPicker })));
// "Compartilhar arquivos" (A37), loaded when it opens.
const SharePanel = lazy(() => import("./SharePanel").then((m) => ({ default: m.SharePanel })));
import { day, detailValue, fileSource, googleCalendarLink, meetingWhen, paragraphs, type Page } from "./format";

const pad = (n: number) => String(n).padStart(2, "0");

type StageFiles = Schemas["StageFilesOut"];
type FileItem = Schemas["FileOut"];

/** Every stage's files, read live from the office's Drive (2.5). */
type FilesState = {
  stages: StageFiles[];
  reference: string | null;
  failed: boolean;
  updates: Schemas["UpdateOut"][]; // the latest changes (A28), files only while shown
};

function useStageFiles(slug: string, version: unknown): FilesState | null {
  const [state, setState] = useState<FilesState | null>(null); // null while loading
  useEffect(() => {
    call(api.GET("/api/pages/{slug}/files", { params: { path: { slug } } })).then(
      (found) =>
        setState({
          stages: found.stages,
          reference: found.reference ?? null,
          failed: false,
          updates: found.updates ?? [],
        }),
      // Couldn't be fetched at all: every stage says so, with the support code.
      (failure: { requestId?: string | null }) =>
        setState({ stages: [], reference: failure?.requestId ?? null, failed: true, updates: [] }),
    );
  }, [slug, version]);
  return state;
}

/** One stage's files (undefined while loading) and the support code, if any. */
function filesFor(state: FilesState | null, position: number) {
  if (state === null) return { files: undefined, reference: null };
  const files = state.failed
    ? { position, groups: [], unavailable: true }
    : state.stages.find((s) => s.position === position);
  return { files, reference: state.reference };
}

function FileCard({
  file,
  slug,
  timeZone,
  menu,
  onOpen,
}: {
  file: FileItem;
  slug: string;
  timeZone: string;
  menu?: ReactNode; // edit mode: the file's "⋯"
  onOpen: () => void; // its preview (FilePreview)
}) {
  // Versions come from the names in Drive (A25): the clean name, its version
  // apart, "Atualizado" for a few days after a new one.
  const { t, i18n } = useTranslation();
  const [versions, setVersions] = useState(false); // every version, in a modal
  // Only images and PDFs have previews (Drive's); other files show their type.
  const preview = fileSource.address(slug, file.key, "thumb");
  const [thumb, setThumb] = useState<"thumb" | "original" | "none">(
    file.kind === "other" ? "none" : preview ? "thumb" : file.kind === "image" ? "original" : "none",
  );
  const extension = file.name.includes(".") ? file.name.split(".").pop()!.toUpperCase() : "";
  // Drive's preview first; for an image without one (local folders), the image itself.
  const src = thumb === "thumb" ? preview : thumb === "original" ? fileSource.address(slug, file.key, "inline") : null;
  return (
    <div className="file" data-file={file.key}>
      <button className="file__open" type="button" onClick={onOpen} aria-label={t("page.openFile", { name: file.name })}>
        <span className="file__thumb">
          {src ? (
            <img
              src={src}
              alt=""
              loading="lazy"
              onError={() => setThumb(thumb === "thumb" && file.kind === "image" ? "original" : "none")}
            />
          ) : file.kind === "pdf" ? (
            <span className="sheetthumb" aria-hidden="true" />
          ) : (
            <span className="file__type">{extension}</span>
          )}
        </span>
        <span className="file__body">
          <span className="file__name" title={file.name}>
            {file.name}
          </span>
          <span className="file__meta">
            {/* Read out, and shown in the list view, where the badge isn't. */}
            {file.version != null && (
              <span className="file__version" aria-label={t("files.versionLabel", { version: file.version })}>
                {t("files.version", { version: file.version })}
              </span>
            )}
            {file.updated && <span className="file__updated">{t("files.updated")}</span>}
            {[fileSize(file.size, i18n.language), day(file.modified_at, i18n.language, timeZone)]
              .filter(Boolean)
              .join(", ")}
          </span>
          {/* Staff only: two files claim one version; the names decide, so one is renamed. */}
          {menu && file.clash && <span className="file__clash">{t("edit.versionClash")}</span>}
        </span>
      </button>
      {file.version != null && (
        <span className="vbadge" aria-hidden="true">
          {t("files.version", { version: file.version })}
        </span>
      )}
      {file.older.length > 0 && (
        <button
          className="older-button"
          type="button"
          aria-haspopup="dialog"
          onClick={() => setVersions(true)}
        >
          {t("files.versionCount", { count: file.older.length + 1 })}
        </button>
      )}
      {versions && <FileVersions file={file} slug={slug} timeZone={timeZone} onClose={() => setVersions(false)} />}
      {menu}
    </div>
  );
}

function StageFilesList({
  files,
  reference,
  slug,
  timeZone,
  fileMenu,
  view,
  onOpen,
  empty,
}: {
  files: StageFiles | undefined;
  reference: string | null;
  slug: string;
  timeZone: string;
  fileMenu?: (file: FileItem) => ReactNode;
  view: FileView;
  onOpen: (file: FileItem, folder: string | null) => void; // folder: its subfolder's name
  // No files yet: "done" (finished without any), "waiting" (they're still to
  // come), or null in edit mode, where the drop area below says it.
  empty: "done" | "waiting" | null;
}) {
  const { t } = useTranslation();
  if (!files) return null; // still loading
  if (files.unavailable)
    return (
      <p className="empty-stage">
        {t("page.filesUnavailable")}
        {reference && ` ${t("errors.reference", { id: reference })}`}
      </p>
    );
  if (!files.groups.length)
    return (
      empty && (
        <div className="stage-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
            <path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2v-10Z" />
          </svg>
          {empty === "done" ? (
            <p>
              <strong>{t("page.noFilesDone")}</strong>
            </p>
          ) : (
            <p>
              <strong>{t("page.noFilesTitle")}</strong>
              <span>{t("page.noFilesBody")}</span>
            </p>
          )}
        </div>
      )
    );
  return (
    <>
      {files.groups.map((group) => (
        <div key={group.folder ?? ""} className="file-group">
          {group.folder && <h3 className="file-group__title">{group.folder}</h3>}
          <div className="files" data-view={view}>
            {group.files.map((file) => (
              <FileCard
                key={file.key}
                file={file}
                slug={slug}
                timeZone={timeZone}
                menu={fileMenu?.(file)}
                onOpen={() => onOpen(file, group.folder ?? null)}
              />
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

/** The set with the row added, or taken out if it was there. */
function toggled(set: ReadonlySet<number>, index: number): ReadonlySet<number> {
  const next = new Set(set);
  if (!next.delete(index)) next.add(index);
  return next;
}

function countFiles(files: StageFiles | undefined): number {
  return files?.groups.reduce((sum, group) => sum + group.files.length, 0) ?? 0;
}

function useNarrow(): boolean {
  const query = "(max-width: 760px)";
  const [narrow, setNarrow] = useState(() => window.matchMedia?.(query).matches ?? false);
  useEffect(() => {
    const list = window.matchMedia?.(query);
    if (!list) return;
    const change = () => setNarrow(list.matches);
    list.addEventListener("change", change);
    return () => list.removeEventListener("change", change);
  }, []);
  return narrow;
}

/** Three joined dots: sharing. */
function ShareIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <circle cx="18" cy="5" r="2.5" />
      <circle cx="6" cy="12" r="2.5" />
      <circle cx="18" cy="19" r="2.5" />
      <path d="M8.2 10.8l7.6-4.4M8.2 13.2l7.6 4.4" />
    </svg>
  );
}

export function Icon({ name }: { name: "down" | "up" | "x" | "moon" | "sun" | "link" | "left" }) {
  const paths = {
    link: "M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1",
    left: "M15 6l-6 6 6 6",
    down: "M6 9l6 6 6-6",
    up: "M6 15l6-6 6 6",
    x: "M6 6l12 12M18 6L6 18",
    moon: "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z",
    sun: "M12 4V2M12 22v-2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8Z",
  };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}

/** The office's logo (it carries the name) or, without one, its name; on the
 *  right the page's tools and the site's header menu (ui/HeaderMenu): "Modo
 *  escuro" for anyone, and for staff who they are, the tour and Sair. */
export function SiteHeader({
  office,
  tools,
  painel = false,
  person,
  onTour,
  onSignOut,
}: {
  office: { name: string; logo_url?: string | null; logo_dark_url?: string | null };
  tools?: ReactNode; // e.g. the project's "Atualizações"
  painel?: boolean; // staff: the logo goes back to the painel
  person?: { name: string; email: string } | null; // staff signed in
  onTour?: () => void;
  onSignOut?: () => void;
}) {
  const { t } = useTranslation();
  const brand = <OfficeBrand name={office.name} logo={office.logo_url} logoDark={office.logo_dark_url} />;
  return (
    <div className="site">
      <div className="site__in">
        {painel ? (
          <a className="site__brand" href="/painel/" title={t("page.backToPainel")}>
            {brand}
          </a>
        ) : (
          <div className="site__brand">{brand}</div>
        )}
        <div className="client-header-tools">
          {tools}
          <HeaderMenu person={person} onTour={onTour} tourLabel={t("tour.again")} onSignOut={onSignOut} />
        </div>
      </div>
    </div>
  );
}

function Description({ text }: { text: string }) {
  return (
    <>
      {paragraphs(text).map((block, i) =>
        block.kind === "p" ? (
          <p key={i}>{block.text}</p>
        ) : (
          <ul key={i}>
            {block.items.map((item, j) => (
              <li key={j}>{item}</li>
            ))}
          </ul>
        ),
      )}
    </>
  );
}

/** Cliente, type, the project's details, and the last update. */
function Facts({ page }: { page: Page }) {
  const { t, i18n } = useTranslation();
  const rows: Array<[string, string]> = [
    [t("page.client"), page.client_name.toLocaleUpperCase(i18n.language)],
    ...page.details.map((d) => [d.label, detailValue(d, i18n.language)] as [string, string]),
    [t("page.lastUpdate"), day(page.last_update, i18n.language, page.timezone)],
  ];
  return (
    <>
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </>
  );
}

/** On phones: "Detalhes do projeto", opening to the details (the client first) and
 *  the description. The arrow keeps to the right edge, whatever the names' length. */
function MobileSummary({ page }: { page: Page }) {
  const { t } = useTranslation();
  return (
    <details className="facts-disclosure mobile-project-summary">
      <summary>
        <span className="facts-summary-label">{t("page.projectDetails")}</span>
        <span className="facts-summary-action" aria-hidden="true">
          <Icon name="down" />
        </span>
      </summary>
      <dl className="details-list">
        <Facts page={page} />
        {page.description && (
          <div className="mobile-project-description">
            <dt>{t("page.description")}</dt>
            <dd><Description text={page.description} /></dd>
          </div>
        )}
      </dl>
    </details>
  );
}

// Stages complete on their own, in any order (Fabio, 23 Oct 2026): each is done or open.
function stateOf(page: Page, index: number): "done" | "open" {
  return page.stages[index]!.completed ? "done" : "open";
}

/** The stage opened first: the first one still open, else the first. */
export function firstOpenStage(page: Page) {
  return Math.max(0, page.stages.findIndex((stage) => !stage.completed));
}

/** How many stages are completed, in words and as a thin bar: over the
 *  checklist on a computer, over the stages on a phone. */
function StageCompletion({ page }: { page: Page }) {
  const { t } = useTranslation();
  const done = page.stages.filter((stage) => stage.completed).length;
  const progress = t("page.stagesDone", { done, total: page.stages.length });
  return (
    <div className="stage-completion">
      <span aria-hidden="true">{progress}</span>
      <CompletionBar done={done} total={page.stages.length} label={progress} />
    </div>
  );
}

/** The stages under how many are completed: no numbers, and a bare check or a
 *  dot instead of tick boxes, so it reads as a set rather than a path or a
 *  checklist (Fabio, 23 Oct 2026). */
function Timeline({ page, onJump }: { page: Page; onJump: (index: number) => void }) {
  const { t } = useTranslation();
  const narrow = useNarrow();
  return (
    <>
      <div className="journey-intro">
        <div>
          {narrow ? (
            <span className="journey-kicker">{t("page.timeline").toLocaleUpperCase()}</span>
          ) : (
            <h2>{t("page.journeyTitle")}</h2>
          )}
        </div>
      </div>
      <StageCompletion page={page} />
      {/* Two columns, read down the first then the second. */}
      <ol
        className="stage-steps"
        aria-label={t("page.stages")}
        style={{ gridTemplateRows: `repeat(${Math.ceil(page.stages.length / 2)}, auto)` }}
      >
        {page.stages.map((stage, i) => {
          const state = stateOf(page, i);
          return (
            <li key={i} className={`stage-steps__item is-${state}`}>
              <button type="button" onClick={() => onJump(i)}>
                <span className="stage-mark" aria-hidden="true">
                  {state === "done" && (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                      <path d="M6 12.5l4 4 8-9" />
                    </svg>
                  )}
                </span>
                <b>{stage.title}</b>
                {state === "done" && <span className="sr">{t("page.stageDone")}</span>}
              </button>
            </li>
          );
        })}
      </ol>
    </>
  );
}

function MeetingCard({ page, slug, onEdit }: { page: Page; slug: string; onEdit?: () => void }) {
  const { t, i18n } = useTranslation();
  const narrow = useNarrow();
  const meeting = page.next_meeting;
  const when = meeting ? meetingWhen(meeting, i18n.language, page.timezone) : null;
  const title = meeting ? meeting.title || t("page.defaultMeetingTitle") : t("page.noMeetingTitle");
  const calendar = fileSource.calendar(slug);
  return (
    <section className="meeting" data-editable aria-label={t("page.nextMeeting")} {...openOnClick(onEdit)}>
      {onEdit && <EditButton label={meeting ? t("edit.meeting") : t("edit.schedule")} onClick={onEdit} />}
      <div>
        <h2>{narrow && meeting ? t("page.meetingScheduled") : t("page.nextMeeting")}</h2>
        <p className="meeting__title" title={title}>
          {title}
        </p>
        {when ? (
          <p className="meeting__meta meeting__when">
            <span>{when.day}</span>
            <span>{when.time}</span>
          </p>
        ) : (
          // Staff in edit mode: a button to schedule one (the card opens the editor too).
          <>
            {!onEdit && <p className="meeting__meta">{t("page.noMeeting")}</p>}
            {onEdit && (
              <button type="button" className="b b--small meeting__schedule" onClick={onEdit}>
                {t("edit.scheduleMeeting")}
              </button>
            )}
          </>
        )}
        {meeting?.location && (
          <p className="meeting__meta" title={meeting.location}>
            {meeting.location}
          </p>
        )}
      </div>
      {meeting && (
        <div className="meeting-actions">
          {meeting.link && (
            <a className="cbtn" href={meeting.link} target="_blank" rel="noopener noreferrer">
              {t("page.joinMeeting")}
            </a>
          )}
          <PopoverDetails className="calendar-options">
            <summary className="b b--small">{t("page.addToCalendar")}</summary>
            <div className="calendar-menu">
              <a
                href={googleCalendarLink(meeting, page.name, window.location.href)}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("page.googleCalendar")}
              </a>
              {calendar && (
                <a href={calendar} download="reuniao.ics">
                  {t("page.otherCalendar")}
                </a>
              )}
            </div>
          </PopoverDetails>
        </div>
      )}
    </section>
  );
}

function Stage({
  page,
  index,
  open,
  onToggle,
  files,
  reference,
  slug,
  editor,
  uploads,
  fileMenu,
  view = "grid",
  progress,
  hidden = false,
  total,
  onOpenFile,
  help,
  onHelp,
  onShare,
}: {
  page: Page;
  index: number;
  onShare?: () => void; // "Compartilhar arquivos" with this stage's files ticked
  open: boolean;
  onToggle: () => void;
  help: boolean; // its "Sobre esta etapa" is open (one stage's at a time)
  onHelp: (open: boolean) => void;
  files: StageFiles | undefined;
  reference: string | null;
  slug: string;
  // Edit mode: "Editar etapa" lays the stage out with its form's parts (StageEditParts).
  editor?: { editing: boolean; onEdit: () => void; form: (layout: (parts?: StageEditParts) => ReactNode) => ReactNode };
  uploads?: ReactNode; // edit mode: the drop area
  fileMenu?: (file: FileItem) => ReactNode;
  view?: FileView;
  progress?: ReactNode; // edit mode: "Marcar como concluída" or "Reabrir etapa"
  hidden?: boolean; // a search or filter found nothing here
  total?: number; // its files before any search or filter
  onOpenFile: (file: FileItem, folder: string | null) => void;
}) {
  const { t } = useTranslation();
  const narrow = useNarrow();
  const stage = page.stages[index]!;
  const state = stateOf(page, index);
  const helpRef = useRef<HTMLDivElement>(null);
  useDismiss(helpRef, help, () => onHelp(false));
  // "Sobre esta etapa", an (i) beside the title: desktop only for now; on a phone its "+" beside the
  // stage's arrow read as another way to open it (Fabio, 19 Oct 2026).
  const helpPanel = stage.about && (
    <div className="stage-help-pop" hidden={!help}>
      <button type="button" className="iconbtn stage-help-close" aria-label={t("page.closeAbout")} onClick={() => onHelp(false)}>
        <Icon name="x" />
      </button>
      <p>{stage.about}</p>
    </div>
  );
  const helpControl = stage.about && !narrow && (
    <div className="stage-help" ref={helpRef}>
      <button
        className="stage-help-toggle"
        type="button"
        aria-expanded={help}
        aria-label={t("page.aboutStageOf", { title: stage.title })}
        onClick={() => onHelp(!help)}
      >
        <span className="stage-help-mark" aria-hidden="true">
          i
        </span>
      </button>
      {helpPanel}
    </div>
  );
  // A closed stage opens on a click anywhere on it; an open one closes from its
  // number or head (a click among its files keeps it open). As its arrow does: the
  // arrow stays the control for keyboards and screen readers. Its own buttons,
  // links and forms keep their job. A stage being edited stays open.
  const headClick = (event: React.MouseEvent) => {
    const target = event.target as Element;
    if (editor?.editing) return;
    if (open && !target.closest(".stage__head, .stage__n")) return;
    if (target.closest("button, a, input, select, textarea, label, form, [role='group'], .stage-help")) return;
    if (window.getSelection?.()?.toString()) return; // selecting the title's text
    onToggle();
  };
  // The stage's markup; in "Editar etapa", its form's parts in their places.
  const layout = (parts?: StageEditParts) => (
    <>
      <span className="stage__n">{pad(index + 1)}</span>
      <div className="stage__head">
        <div className="stage__title">
          <div className="stage__name">
            <h2 id={`st-${index}`} tabIndex={-1} className={parts ? "sr" : undefined}>
              {stage.title}
            </h2>
            {/* On a phone, a closed stage hides its "Concluída": a check says it instead. */}
            {state === "done" && !parts && (
              <span className="stage__done-mark" role="img" aria-label={t("page.stageDoneMark")}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                  <path d="M6 12.5l4 4 8-9" />
                </svg>
              </span>
            )}
            {parts ? parts.name : helpControl}
          </div>
          <div className="client-stage-controls">
            {parts?.actions}
            {editor && !parts && (
              <button
                className="b b--small stage-edit-toggle"
                type="button"
                aria-label={t("edit.editStageOf", { title: stage.title })}
                onClick={editor.onEdit}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                  <path d="M4 20h4L19 9l-4-4L4 16v4Z M13.5 6.5l4 4" />
                </svg>
                <span>{t("edit.editStage")}</span>
              </button>
            )}
            {/* "Marcar como concluída" / "Reabrir etapa" beside "Editar etapa" (Fabio, 25 Oct 2026). */}
            {progress && !parts && progress}
            {onShare && !parts && !!(total ?? countFiles(files)) && (
              <button
                className="iconbtn stage-share"
                type="button"
                aria-label={t("share.openStage", { title: stage.title })}
                title={t("share.open")}
                onClick={onShare}
              >
                <ShareIcon />
              </button>
            )}
            {!parts && (
              <button
                className="iconbtn"
                type="button"
                aria-controls={`stage-body-${index}`}
                aria-expanded={open}
                aria-label={t(open ? "page.stageOpen" : "page.openStage", { title: stage.title })}
                onClick={onToggle}
              >
                <Icon name={open ? "up" : "down"} />
              </button>
            )}
          </div>
        </div>
        <p className="stage__meta">
          {state === "done" && <span className="pill pill--done">{t("page.stageDone")}</span>}
          {files && !files.unavailable && (
            <span>
              {(total ?? countFiles(files))
                ? t("page.fileCount", {
                    count: total ?? countFiles(files),
                    padded: pad(total ?? countFiles(files)),
                  })
                : t("page.noFilesShort")}
            </span>
          )}
        </p>
      </div>
      <div className="stage__body" id={`stage-body-${index}`} aria-hidden={!open} inert={!open}>
        <div className="stage__body-inner">
          {parts ? (
            parts.notes
          ) : stage.notes ? (
            <div className="notes" data-editable {...openOnClick(editor?.onEdit)}>
              {editor && <EditButton label={t("edit.notesShort")} onClick={editor.onEdit} />}
              <p>{stage.notes}</p>
            </div>
          ) : (
            editor && (
              <button className="ghostline addnote" type="button" onClick={editor.onEdit}>
                + {t("edit.addNote")}
              </button>
            )
          )}
          <StageFilesList
            files={files}
            reference={reference}
            slug={slug}
            timeZone={page.timezone}
            fileMenu={fileMenu}
            view={view}
            onOpen={onOpenFile}
            empty={editor ? null : state === "done" ? "done" : "waiting"}
          />
          {uploads}
          {parts?.remove}
        </div>
      </div>
    </>
  );
  return (
    <section
      className={`stage ${open ? "is-expanded " : ""}${editor?.editing ? "is-editing " : ""}stage--${state}`}
      id={`stage-${index}`}
      aria-labelledby={`st-${index}`}
      hidden={hidden}
      onClick={headClick}
    >
      {editor?.editing ? editor.form(layout) : layout()}
    </section>
  );
}

/** For the office's signed-in staff only (the prototype's dock): back to the
 *  painel, view or edit, and copy its link. Nothing about
 *  publishing: no drafts for now (A35). */
function StaffBar({
  page,
  ready,
  editing,
  onMode,
}: {
  page: Page;
  ready: boolean;
  editing: boolean;
  onMode: (editing: boolean) => void;
}) {
  const { t } = useTranslation();
  const staff = page.staff!;
  const archived = staff.status === "archived"; // viewable, not editable (section 22)
  return (
    <nav className="dock" aria-label={t("page.staffBar")}>
      <a className="b" href="/painel/" aria-label={t("page.backToPainel")}>
        <Icon name="left" />
        <span className="hide-sm">{t("page.backToPainel")}</span>
      </a>
      <span className="dock__sep" />
      <span className="dock__title">{page.name}</span>
      {/* The prototype's switch: the page as the client sees it, or with controls. */}
      <div className="seg" role="group" aria-label={t("edit.mode")} data-on={editing ? "edit" : "view"} data-tour="mode">
        <button type="button" aria-pressed={!editing} onClick={() => onMode(false)}>
          {t("edit.asClient")}
        </button>
        <button
          type="button"
          aria-pressed={editing}
          disabled={!ready || archived}
          title={archived ? t("edit.archivedNoEdit") : undefined}
          onClick={() => onMode(true)}
        >
          {t("edit.edit")}
        </button>
      </div>
      <button
        className="iconbtn"
        type="button"
        data-tour="link"
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
    </nav>
  );
}

/** The cover shrinks away as the page scrolls (prototype), unless motion is reduced. */
function useCoverWipe(ref: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const image = ref.current;
      if (!image || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
      const full = (image.clientWidth * 9) / 16;
      image.style.setProperty("--cover-image-height", `${full}px`);
      image.style.height = `${Math.max(0, full - window.scrollY)}px`;
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    update();
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      cancelAnimationFrame(frame);
    };
  }, [ref]);
}

/** The project's name, in capitals (painel redesign: no more "/casa jardim"). */
function Title({ name }: { name: string }) {
  return <h1 className="project-title">{name}</h1>;
}

let tourOffered = false;

export function ProjectPage({
  page,
  slug,
  ready = false,
  tourSeen = true,
  onChanged,
  onTour,
  person,
  onSignOut,
  sharing = true,
}: {
  page: Page;
  slug: string;
  sharing?: boolean; // "Compartilhar arquivos" (A37); not on the example project
  person?: { name: string; email: string } | null; // staff signed in
  onSignOut?: () => void;
  ready?: boolean; // the staff session's CSRF token is in hand
  tourSeen?: boolean; // false: this staff account hasn't had the tour yet
  onChanged?: () => void;
  onTour?: () => void; // the menu's tour runs this instead (the example project's)
}) {
  const { t } = useTranslation();
  const narrow = useNarrow();
  const cover = useRef<HTMLDivElement>(null);
  useCoverWipe(cover);
  const mainColumn = useRef<HTMLDivElement>(null);
  const sideColumn = useRef<HTMLDivElement>(null);
  const moved = useBalancedColumns(mainColumn, sideColumn);
  const stageFiles = useStageFiles(slug, page);
  const [editing, setEditing] = useState(false);
  // The guided tour (Tour.ts, loaded only for staff): once per account, then from the account menu
  // (not on an archived page, which can't be edited).
  const tour = (first: boolean) =>
    void import("./Tour").then(({ startTour }) =>
      startTour({ t, enterEdit: () => setEditing(true), markSeen: first }),
    );
  useEffect(() => {
    const archived = page.staff?.status === "archived";
    if (!page.staff || !ready || tourSeen || archived || tourOffered) return;
    tourOffered = true; // once per visit, even if the page mounts again
    tour(true);
  }, [ready, tourSeen, page.staff]); // once, when the session is ready
  const [openEditor, setOpenEditor] = useState<string | null>(null);
  const staff = page.staff;
  // Stage controls wait for the reloaded page after each change (a new row version).
  const [changedFrom, setChangedFrom] = useState<number | null>(null);
  const stagesLocked = staff != null && changedFrom === staff.row_version;
  const stagesChanged = () => {
    setChangedFrom(staff?.row_version ?? null);
    onChanged?.();
  };
  const canEdit = editing && !!staff;
  const done = (saved: boolean) => {
    setOpenEditor(null);
    if (saved) onChanged?.();
  };
  // The stage open (by row): the first one still open at first, and one at a time
  // (Fabio, 23 Oct 2026): opening another closes it. A search or filter still
  // opens every stage with a match, and a stage in "Editar etapa" stays open.
  const [openStages, setOpenStages] = useState<ReadonlySet<number>>(
    () => new Set([firstOpenStage(page)]),
  );
  const openStage = (index: number) => setOpenStages(new Set([index]));
  // One stage's "Sobre esta etapa" open at a time: two would overlap.
  const [openHelp, setOpenHelp] = useState<number | null>(null);
  // The stages in "Editar etapa" (by row); several can be at once.
  const [editingStages, setEditingStages] = useState<ReadonlySet<number>>(new Set());
  // After a reorder the open stages stay open wherever the new order puts them, and
  // the stages being edited, kept by row, close: another stage is on that row now.
  const reordered = (order: number[]) => {
    setOpenStages((open) => new Set([...open].map((i) => order.indexOf(i + 1)).filter((i) => i >= 0)));
    setEditingStages(new Set());
    setOpenHelp(null);
  };
  // The file tools (FileTools): search, type, order, view, and the file in preview.
  const [query, setQuery] = useState("");
  const [prefs, setPrefs] = usePrefs();
  const [preview, setPreview] = useState<{ file: FileItem; place: FilePlace } | null>(null);
  const filtering = query.trim() !== "" || prefs.type !== "all";
  // While filtering, every stage with a match opens; these are the ones closed since.
  const [closed, setClosed] = useState<ReadonlySet<number>>(new Set());
  useEffect(() => setClosed(new Set()), [query, prefs.type]);
  const shown = page.stages.map((stage, i) => {
    const files = filesFor(stageFiles, i + 1).files;
    return files ? shownFiles(files, stage.title, query, prefs) : { files: undefined, count: 0 };
  });
  const unreadable = (i: number) => Boolean(filesFor(stageFiles, i + 1).files?.unavailable);
  // The share panel: undefined while closed; null opened above the stages, or
  // the row of the stage it was opened from.
  const [shareFrom, setShareFrom] = useState<number | null | undefined>(undefined);
  const anyFiles = !!stageFiles && page.stages.some((_, i) => countFiles(filesFor(stageFiles, i + 1).files) > 0);
  const canShare = sharing && anyFiles;

  useEffect(() => {
    document.title = `${page.name} · ${page.office.name}`;
  }, [page.name, page.office.name]);

  const jump = (index: number) => {
    // A stage hidden by the search or the type filter must show before it is reached.
    flushSync(() => {
      if (filtering) {
        setQuery("");
        setPrefs({ type: "all" });
      }
      openStage(index);
    });
    const section = document.getElementById(`stage-${index}`);
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    section?.scrollIntoView({ behavior: reduce ? "instant" : "smooth", block: "start" });
    section?.querySelector("h2")?.focus({ preventScroll: true });
  };

  // A file's link (`?etapa=3&arquivo=Planta.pdf`, sent from its preview): once the
  // files are in, its stage opens, the page scrolls to it and its preview opens.
  // The address keeps the file until the preview closes. A file renamed, moved or
  // gone: the page as usual.
  const linked = useRef(linkedFile(window.location.search));
  useEffect(() => {
    const place = linked.current;
    if (!place || stageFiles === null) return;
    linked.current = null;
    // Drive allows two subfolders, or two files, of the same name: the first in the
    // page's order. A document goes by its clean name, so its link opens the
    // current version (A25).
    const file = filesFor(stageFiles, place.position)
      .files?.groups.filter((g) => (g.folder ?? null) === place.folder)
      .flatMap((g) => g.files)
      .find((candidate) => candidate.name === place.name);
    if (!file) return;
    openStage(place.position - 1);
    setPreview({ file, place });
    // Once the stage has opened, so the file is there to scroll to.
    requestAnimationFrame(() =>
      [...document.querySelectorAll<HTMLElement>("[data-file]")]
        .find((card) => card.dataset.file === file.key)
        ?.scrollIntoView?.({ block: "center" }),
    );
  }, [stageFiles]);
  const closePreview = () => {
    setPreview(null);
    if (linkedFile(window.location.search))
      window.history.replaceState(window.history.state, "", window.location.pathname + window.location.hash);
  };
  // The side column's cards under the details, which move under the stages, the
  // meeting first, when the side column would otherwise run much longer
  // (balance.ts); `data-movable` is the order they move in.
  const movable = [
    <div key="meeting" className="project-status__meeting" data-movable="0">
      {canEdit && openEditor === "meet" ? (
        <Suspense fallback={null}>
          <MeetingEditor page={page} staff={staff!} onDone={done} />
        </Suspense>
      ) : (
        <MeetingCard page={page} slug={slug} onEdit={canEdit ? () => setOpenEditor("meet") : undefined} />
      )}
    </div>,
    // Clients add themselves to the emails (A32); not in edit mode, not when done.
    ...(!canEdit && !page.completed
      ? [
          <div key="subscribe" data-movable="1">
            <Subscribe slug={slug} />
          </div>,
        ]
      : []),
  ];

  return (
    <div className={`client${canEdit ? " editing" : ""}`}>
      <SiteHeader
        office={page.office}
        painel={!!page.staff}
        person={page.staff ? person : null}
        onTour={page.staff && page.staff.status !== "archived" ? (onTour ?? (() => tour(false))) : undefined}
        onSignOut={page.staff ? onSignOut : undefined}
        tools={
          stageFiles && (
            <UpdatesBell
              page={page}
              slug={slug}
              updates={stageFiles.updates}
              onStage={jump}
            />
          )
        }
      />
      <div className="cwrap">
        {canEdit &&
          (openEditor === "emails" ? (
            <Suspense fallback={null}>
              <RecipientsEditor staff={staff!} onDone={done} />
            </Suspense>
          ) : (
            staff!.status === "active" &&
            // (A page from a server before this list came along says nothing.)
            staff!.recipients !== undefined &&
            !staff!.recipients.some((recipient) => recipient.subscribed) && (
              // Nobody gets this project's updates (A32): said first, with the way to fix it.
              <div className="client-email-notice" role="note">
                <p>
                  <strong>{t("edit.noClientEmail")}</strong> {t("edit.noClientEmailWhy")}
                </p>
                <button type="button" className="b b--small b--primary" onClick={() => setOpenEditor("emails")}>
                  {t("edit.addClientEmail")}
                </button>
              </div>
            )
          ))}
        <div className="project-opening">
          <header className="project-heading">
            {canEdit && openEditor === "name" ? (
              <Suspense fallback={null}>
                <NameEditor page={page} staff={staff!} onDone={done} />
              </Suspense>
            ) : (
              <div
                className="project-heading__title"
                data-editable
                {...openOnClick(canEdit ? () => setOpenEditor("name") : undefined)}
              >
                {canEdit && <EditButton label={t("edit.name")} onClick={() => setOpenEditor("name")} />}
                <Title name={page.name} />
              </div>
            )}
            {/* The kind of project, under its name (edited with the details). */}
            {page.project_type && <p className="project-kind">{page.project_type}</p>}
          </header>
          {narrow && <MobileSummary page={page} />}
          {page.cover_url && (
            <figure className="banner">
              <div className="banner__img" ref={cover}>
                <img src={page.cover_url} alt={t("page.cover", { name: page.name })} />
              </div>
              {canEdit && (
                <Suspense fallback={null}>
                  <CoverPicker page={page} onChanged={() => onChanged?.()} />
                </Suspense>
              )}
            </figure>
          )}
          {/* No cover yet: in edit mode, its place, to add one. */}
          {!page.cover_url && canEdit && (
            <Suspense fallback={null}>
              <CoverPicker page={page} onChanged={() => onChanged?.()} />
            </Suspense>
          )}
        </div>
        {/* Two columns that stack on their own: the description then the timeline,
            the details then the meeting. A short description lets the timeline rise;
            without a cover, both start under the title. Phones: one column. */}
        <div className="project-status project-layout">
          <div className="project-layout__main" ref={mainColumn}>
            {/* No description: nothing for the client (staff in edit mode can add one). */}
            {(page.description || canEdit) && (
              <div className={`project-layout__desc${narrow && !canEdit ? " mobile-view-hidden" : ""}`}>
                {canEdit && openEditor === "desc" ? (
                  <Suspense fallback={null}>
                    <DescriptionEditor page={page} staff={staff!} onDone={done} />
                  </Suspense>
                ) : (
                  <div className="desc" data-editable {...openOnClick(canEdit ? () => setOpenEditor("desc") : undefined)}>
                    {canEdit && <EditButton label={t("edit.description")} onClick={() => setOpenEditor("desc")} />}
                    {page.description ? (
                      <Description text={page.description} />
                    ) : (
                      canEdit && <p className="desc__empty">{t("edit.noDescription")}</p>
                    )}
                  </div>
                )}
              </div>
            )}
            {!narrow && page.stages.length > 0 && (
              <div className="project-status__timeline">
                <Timeline page={page} onJump={jump} />
              </div>
            )}
            {movable.slice(0, moved)}
          </div>
          <div className="project-layout__side" ref={sideColumn}>
            <div className={narrow && !canEdit ? "mobile-view-hidden" : undefined}>
              {canEdit && openEditor === "facts" ? (
                <Suspense fallback={null}>
                  <DetailsEditor page={page} staff={staff!} onDone={done} />
                </Suspense>
              ) : (
                <dl className="details-list" data-editable {...openOnClick(canEdit ? () => setOpenEditor("facts") : undefined)}>
                  {canEdit && <EditButton label={t("edit.details")} onClick={() => setOpenEditor("facts")} />}
                  <Facts page={page} />
                </dl>
              )}
            </div>
            {movable.slice(moved)}
          </div>
        </div>
        {/* With the stages, even before any files, so the page keeps its spacing. */}
        {page.stages.length > 0 && (
          <FileToolbar
            query={query}
            onQuery={setQuery}
            prefs={prefs}
            onPrefs={setPrefs}
            found={filtering ? shown.reduce((sum, stage) => sum + stage.count, 0) : null}
            narrow={narrow}
            share={
              canShare && (
                <button type="button" className="b b--small client-share" onClick={() => setShareFrom(null)}>
                  <ShareIcon />
                  <span>{t("share.open")}</span>
                </button>
              )
            }
          />
        )}
        {narrow && page.stages.length > 0 && (
          <>
            <h2 className="stage-timeline-heading">{t("page.timeline").toLocaleUpperCase()}</h2>
            <StageCompletion page={page} />
          </>
        )}
        {page.stages.map((_, i) => (
          <Stage
            key={i}
            page={page}
            index={i}
            // Searching or filtering opens every stage with a match and hides the rest,
            // except one whose files couldn't be read: it says so.
            open={
              filtering
                ? (shown[i]!.count > 0 || unreadable(i)) && !closed.has(i)
                : openStages.has(i) || (canEdit && editingStages.has(i))
            }
            hidden={filtering && shown[i]!.count === 0 && !unreadable(i)}
            help={openHelp === i}
            onHelp={(open) => setOpenHelp(open ? i : null)}
            onShare={canShare && !canEdit ? () => setShareFrom(i) : undefined}
            onToggle={() =>
              filtering
                ? setClosed((was) => toggled(was, i))
                : setOpenStages((was) => (was.has(i) ? new Set() : new Set([i])))
            }
            {...filesFor(stageFiles, i + 1)}
            files={shown[i]!.files}
            total={countFiles(filesFor(stageFiles, i + 1).files)}
            view={prefs.view}
            progress={
              canEdit ? (
                <Suspense fallback={null}>
                  <StageProgress page={page} staff={staff!} index={i} onChanged={stagesChanged} locked={stagesLocked} />
                </Suspense>
              ) : undefined
            }
            onOpenFile={(file, folder) => setPreview({ file, place: { position: i + 1, folder } })}
            slug={slug}
            uploads={
              canEdit ? (
                <Suspense fallback={null}>
                  <StageDrop
                    staff={staff!}
                    position={i + 1}
                    folder={`${pad(i + 1)} - ${page.stages[i]!.title}`}
                    onChanged={() => onChanged?.()}
                  />
                </Suspense>
              ) : undefined
            }
            fileMenu={
              canEdit
                ? (file) => (
                    <Suspense fallback={null}>
                      <FileMenu slug={slug} file={file} page={page} position={i + 1} onChanged={() => onChanged?.()} />
                    </Suspense>
                  )
                : undefined
            }
            editor={
              canEdit
                ? {
                    editing: editingStages.has(i),
                    onEdit: () => setEditingStages((was) => new Set(was).add(i)),
                    form: (layout) => (
                      // Until the form's code is in, the stage as it was.
                      <Suspense fallback={layout()}>
                        <StageEditForm
                          page={page}
                          staff={staff!}
                          index={i}
                          locked={stagesLocked}
                          onChanged={stagesChanged}
                          // A removed stage's row shows the next one: every edit closes.
                          onDone={(removed) => setEditingStages((was) => (removed ? new Set() : toggled(was, i)))}
                          layout={layout}
                        />
                      </Suspense>
                    ),
                  }
                : undefined
            }
          />
        ))}
        {canEdit && (
          <div className="stage-list-actions">
            <Suspense fallback={null}>
              <AddStage page={page} staff={staff!} onChanged={stagesChanged} locked={stagesLocked} />
              <ReorderStages page={page} staff={staff!} onChanged={stagesChanged} onReordered={reordered} locked={stagesLocked} />
              <CompleteProject page={page} staff={staff!} onChanged={stagesChanged} />
            </Suspense>
          </div>
        )}
        <SiteFooter office={page.office.name} className="client-footer" />
      </div>
      {page.staff && (
        <StaffBar
          page={page}
          ready={ready}
          editing={editing}
          onMode={(next) => {
            setEditing(next);
            setOpenEditor(null);
            setEditingStages(new Set());
          }}
        />
      )}
      {preview && <FilePreview {...preview} slug={slug} page={page} onClose={closePreview} />}
      {shareFrom !== undefined && (
        <Suspense fallback={null}>
          <SharePanel
            page={page}
            slug={slug}
            stages={stageFiles && !stageFiles.failed ? stageFiles.stages : null}
            from={shareFrom}
            staff={!!page.staff && ready}
            onClose={() => setShareFrom(undefined)}
          />
        </Suspense>
      )}
      <Toaster />
    </div>
  );
}

/** Not found, or protected: the office's header and a short message. */
export function PageMessage({ office, title, body }: { office: { name: string } | null; title: string; body: ReactNode }) {
  return (
    <div className="client">
      {office && <SiteHeader office={office} />}
      <div className="cwrap page-message">
        <h1>{title}</h1>
        <p>{body}</p>
      </div>
    </div>
  );
}
