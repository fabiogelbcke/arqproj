// The client's project page, read-only (slice 2.3), after the fresh prototype's
// markup: its stylesheet (prototype.css) styles these same class names.
import { Suspense, lazy, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { flushSync } from "react-dom";

import { api, call, type Schemas } from "../api/client";
import { OfficeLogo } from "../ui/OfficeLogo";
import { Toaster, toast, toastError } from "../ui/Toast";
import { EditButton } from "./EditButton";
import { splitTitle } from "./titleLead";
import { UpdatesBell } from "./Updates";
import { FilePreview, FileToolbar, linkedFile, shownFiles, usePrefs, type FilePlace, type FileView } from "./FileTools";

// Staff editing code loads only once staff press "Editar" (A20): visitors never get it.
const DescriptionEditor = lazy(() => import("./Editors").then((m) => ({ default: m.DescriptionEditor })));
const NameEditor = lazy(() => import("./Editors").then((m) => ({ default: m.NameEditor })));
const DetailsEditor = lazy(() => import("./Editors").then((m) => ({ default: m.DetailsEditor })));
const MeetingEditor = lazy(() => import("./Editors").then((m) => ({ default: m.MeetingEditor })));
const NotesEditor = lazy(() => import("./Editors").then((m) => ({ default: m.NotesEditor })));
const AddStage = lazy(() => import("./StageEditing").then((m) => ({ default: m.AddStage })));
const ProgressRail = lazy(() => import("./StageEditing").then((m) => ({ default: m.ProgressRail })));
const StageControls = lazy(() => import("./StageEditing").then((m) => ({ default: m.StageControls })));
const StageDrop = lazy(() => import("./StageUploads").then((m) => ({ default: m.StageDrop })));
const FileMenu = lazy(() => import("./StageUploads").then((m) => ({ default: m.FileMenu })));
const CoverPicker = lazy(() => import("./CoverEditing").then((m) => ({ default: m.CoverPicker })));
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

function fileSize(bytes: number | null | undefined, locale: string): string {
  if (bytes == null) return "";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString(locale, { maximumFractionDigits: unit ? 1 : 0 })} ${units[unit]}`;
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
  const { t, i18n } = useTranslation();
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
            {[fileSize(file.size, i18n.language), day(file.modified_at, i18n.language, timeZone)]
              .filter(Boolean)
              .join(", ")}
          </span>
        </span>
      </button>
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
}: {
  files: StageFiles | undefined;
  reference: string | null;
  slug: string;
  timeZone: string;
  fileMenu?: (file: FileItem) => ReactNode;
  view: FileView;
  onOpen: (file: FileItem, folder: string | null) => void; // folder: its subfolder's name
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
  if (!files.groups.length) return <p className="empty-stage">{t("page.noFiles")}</p>;
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

const THEME_KEY = "alinea-theme";

/** Light by default; the choice is remembered on this device. */
export function ThemeSwitch() {
  const { t } = useTranslation();
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme ?? "light");
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      className="theme-switch"
      type="button"
      aria-label={t(next === "dark" ? "page.useDark" : "page.useLight")}
      onClick={() => {
        document.documentElement.dataset.theme = next;
        try {
          localStorage.setItem(THEME_KEY, next);
        } catch {
          // Private browsing: the choice lasts until the tab closes.
        }
        setTheme(next);
      }}
    >
      <Icon name={next === "dark" ? "moon" : "sun"} />
      <span className="theme-switch__label">{t(next === "dark" ? "page.themeDark" : "page.themeLight")}</span>
    </button>
  );
}

export function applyStoredTheme(): void {
  try {
    if (localStorage.getItem(THEME_KEY) === "dark") document.documentElement.dataset.theme = "dark";
  } catch {
    // The default theme.
  }
}

/** The office's logo (it carries the name) or, without one, its name. */
export function SiteHeader({
  office,
  tools,
}: {
  office: { name: string; logo_url?: string | null; logo_dark_url?: string | null };
  tools?: ReactNode; // e.g. the project's "Atualizações"
}) {
  return (
    <div className="site">
      <div className="site__in">
        <div className="site__brand">
          {office.logo_url ? (
            <OfficeLogo light={office.logo_url} dark={office.logo_dark_url} alt={office.name} />
          ) : (
            <span>{office.name}</span>
          )}
        </div>
        <div className="client-header-tools">
          {tools}
          <ThemeSwitch />
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
      <dl className="facts">
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

function stateOf(page: Page, index: number): "done" | "current" | "upcoming" {
  const current = page.current_position ?? 0;
  if (page.completed || index + 1 < current) return "done";
  return index + 1 === current ? "current" : "upcoming";
}

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
      <ol className="tl" style={{ "--n": page.stages.length } as React.CSSProperties} aria-label={t("page.stages")}>
        {page.stages.map((stage, i) => {
          const state = stateOf(page, i);
          return (
            <li key={i} className={state === "upcoming" ? "" : state}>
              <button type="button" onClick={() => onJump(i)}>
                <span className="n">{pad(i + 1)}</span>
                <b>{stage.title}</b>
                <span>{state === "done" ? t("page.stageDone") : state === "current" ? t("page.stageCurrent") : ""}</span>
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
    <section className="meet" data-editable aria-label={t("page.nextMeeting")}>
      {onEdit && <EditButton label={meeting ? t("edit.meeting") : t("edit.schedule")} onClick={onEdit} />}
      <div>
        <h2>{narrow && meeting ? t("page.meetingScheduled") : t("page.nextMeeting")}</h2>
        <p className="meet__title" title={title}>
          {title}
        </p>
        {when ? (
          <p className="meet__meta meet__schedule">
            <span>{when.day}</span>
            <span>{when.time}</span>
          </p>
        ) : (
          <p className="meet__meta">{t("page.noMeeting")}</p>
        )}
        {meeting?.location && (
          <p className="meet__meta" title={meeting.location}>
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
          <details className="calendar-options">
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
          </details>
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
  controls,
  uploads,
  fileMenu,
  view = "grid",
  hidden = false,
  total,
  onOpenFile,
}: {
  page: Page;
  index: number;
  open: boolean;
  onToggle: () => void;
  files: StageFiles | undefined;
  reference: string | null;
  slug: string;
  editor?: { open: boolean; onOpen: () => void; render: () => ReactNode };
  controls?: ReactNode;
  uploads?: ReactNode; // edit mode: the drop area
  fileMenu?: (file: FileItem) => ReactNode;
  view?: FileView;
  hidden?: boolean; // a search or filter found nothing here
  total?: number; // its files before any search or filter
  onOpenFile: (file: FileItem, folder: string | null) => void;
}) {
  const { t } = useTranslation();
  const narrow = useNarrow();
  const [help, setHelp] = useState(false);
  const stage = page.stages[index]!;
  const state = stateOf(page, index);
  const helpPanel = stage.about && (
    <div className={`stage-help-pop${narrow ? " stage-help-pop--inline" : ""}`} hidden={!help}>
      <button type="button" className="iconbtn stage-help-close" aria-label={t("page.closeAbout")} onClick={() => setHelp(false)}>
        <Icon name="x" />
      </button>
      <p>{stage.about}</p>
    </div>
  );
  const helpControl = stage.about && (
    <div className="stage-help">
      <button
        className="stage-help-toggle"
        type="button"
        aria-expanded={help}
        aria-label={t("page.aboutStageOf", { title: stage.title })}
        onClick={() => setHelp(!help)}
      >
        <span className="stage-help-mark" aria-hidden="true">
          {narrow ? "+" : "i"}
        </span>
        {!narrow && <span>{t("page.aboutStage")}</span>}
      </button>
      {!narrow && helpPanel}
    </div>
  );
  return (
    <section
      className={`stage ${open ? "is-expanded " : ""}${state}`}
      id={`stage-${index}`}
      aria-labelledby={`st-${index}`}
      hidden={hidden}
    >
      <span className="stage__n">{pad(index + 1)}</span>
      <div className="stage__head">
        <div className="stage__title">
          <h2 id={`st-${index}`} tabIndex={-1}>
            {stage.title}
          </h2>
          <div className="client-stage-controls">
            {narrow && helpControl}
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
            {!narrow && helpControl}
          </div>
          {controls}
        </div>
        <p className="stage__meta">
          {state === "done" && <span className="pill">{t("page.stageDone")}</span>}
          {state === "current" && <span className="pill pill--current">{t("page.stageCurrent")}</span>}
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
      {narrow && helpPanel}
      <div className="stage__body" id={`stage-body-${index}`} aria-hidden={!open} inert={!open}>
        <div className="stage__body-inner">
          {editor?.open ? (
            editor.render()
          ) : stage.notes ? (
            <div className="notes" data-editable>
              {editor && <EditButton label={t("edit.notesShort")} onClick={editor.onOpen} />}
              <p>{stage.notes}</p>
            </div>
          ) : (
            editor && (
              <button className="ghostline addnote" type="button" onClick={editor.onOpen}>
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
          />
          {uploads}
        </div>
      </div>
    </section>
  );
}

/** For the office's signed-in staff only (the prototype's dock): back to the
 *  painel, the page's status, copy its link, and publish a draft. */
function StaffBar({
  page,
  ready,
  editing,
  onMode,
  onPublished,
  onTour,
}: {
  page: Page;
  ready: boolean;
  editing: boolean;
  onMode: (editing: boolean) => void;
  onPublished: () => void;
  onTour: () => void; // "?": the guided tour again
}) {
  const { t } = useTranslation();
  const [publishing, setPublishing] = useState(false);
  const staff = page.staff!;
  const draft = staff.status === "draft";
  const archived = staff.status === "archived"; // viewable, not editable (section 22)
  return (
    <nav className="dock" aria-label={t("page.staffBar")}>
      <a className="b" href="/painel/" aria-label={t("page.backToPainel")}>
        <Icon name="left" />
        <span className="hide-sm">{t("page.backToPainel")}</span>
      </a>
      <span className="dock__sep" />
      <span className="dock__title">
        {page.name}
        <small>{draft ? t("page.draftNote") : t("page.publishedNote")}</small>
      </span>
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
            () => toast(t(draft ? "page.linkCopiedDraft" : "page.linkCopied")),
            () => toast(link),
          );
        }}
      >
        <Icon name="link" />
      </button>
      {!archived && (
        <button className="iconbtn dock__help" type="button" aria-label={t("tour.again")} title={t("tour.again")} onClick={onTour}>
          ?
        </button>
      )}
      {draft && (
        <button
          className="b b--primary b--small"
          type="button"
          disabled={publishing || !ready}
          onClick={async () => {
            setPublishing(true);
            try {
              await call(
                api.POST("/api/projects/{project_id}/publish", { params: { path: { project_id: staff.project_id } } }),
              );
              toast(t("page.published"));
              onPublished();
            } catch (failure) {
              toastError(failure);
            } finally {
              setPublishing(false);
            }
          }}
        >
          {t("page.publish")}
        </button>
      )}
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

/** "/casa de praia" (the property or work type, else the first word) then the rest
 *  in bold, on two lines; a short name (under 15 characters) on one. */
function Title({ name }: { name: string }) {
  const { i18n } = useTranslation();
  const { lead, rest } = splitTitle(name);
  const oneLine = name.trim().length < 15;
  return (
    // The two parts are one name for screen readers ("/casa" + "jardim").
    <h1 className={`client-project-title${oneLine ? " client-project-title--one-line" : ""}`} title={name} aria-label={name}>
      <span className="project-title__lead">/{lead.toLocaleLowerCase(i18n.language)}</span>
      {rest && (
        <>
          {oneLine && " "}
          <strong className="project-title__tail">{rest.toLocaleLowerCase(i18n.language)}</strong>
        </>
      )}
    </h1>
  );
}

let tourOffered = false;

export function ProjectPage({
  page,
  slug,
  ready = false,
  tourSeen = true,
  onChanged,
  onTour,
}: {
  page: Page;
  slug: string;
  ready?: boolean; // the staff session's CSRF token is in hand
  tourSeen?: boolean; // false: this staff account hasn't had the tour yet
  onChanged?: () => void;
  onTour?: () => void; // "?" runs this tour instead (the example project's)
}) {
  const { t } = useTranslation();
  const narrow = useNarrow();
  const cover = useRef<HTMLDivElement>(null);
  useCoverWipe(cover);
  const stageFiles = useStageFiles(slug, page);
  const [editing, setEditing] = useState(false);
  // The guided tour (Tour.ts, loaded only for staff): once per account, then from "?".
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
  // One stage open at a time: the current one, until the client opens another.
  const [openStage, setOpenStage] = useState(() => Math.max(0, (page.current_position ?? 1) - 1));
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
  const hasFiles = shown.some((_, i) => countFiles(filesFor(stageFiles, i + 1).files) > 0);

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
      setOpenStage(index);
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
    // page's order (stable ids wait for the document index, A25).
    const file = filesFor(stageFiles, place.position)
      .files?.groups.filter((g) => (g.folder ?? null) === place.folder)
      .flatMap((g) => g.files)
      .find((candidate) => candidate.name === place.name);
    if (!file) return;
    setOpenStage(place.position - 1);
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

  return (
    <div className={`client${canEdit ? " editing" : ""}`}>
      <SiteHeader
        office={page.office}
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
        <div className="project-opening">
          <header className="project-heading">
            {canEdit && openEditor === "name" ? (
              <Suspense fallback={null}>
                <NameEditor page={page} staff={staff!} onDone={done} />
              </Suspense>
            ) : (
              <div className="project-heading__title" data-editable>
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
          <div className="project-layout__main">
            {/* No description: nothing for the client (staff in edit mode can add one). */}
            {(page.description || canEdit) && (
              <div className={`project-layout__desc${narrow && !canEdit ? " mobile-view-hidden" : ""}`}>
                {canEdit && openEditor === "desc" ? (
                  <Suspense fallback={null}>
                    <DescriptionEditor page={page} staff={staff!} onDone={done} />
                  </Suspense>
                ) : (
                  <div className="desc" data-editable>
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
          </div>
          <div className="project-layout__side">
            <div className={narrow && !canEdit ? "mobile-view-hidden" : undefined}>
              {canEdit && openEditor === "facts" ? (
                <Suspense fallback={null}>
                  <DetailsEditor page={page} staff={staff!} onDone={done} />
                </Suspense>
              ) : (
                <dl className="facts" data-editable>
                  {canEdit && <EditButton label={t("edit.details")} onClick={() => setOpenEditor("facts")} />}
                  <Facts page={page} />
                </dl>
              )}
            </div>
            <div className="project-status__meeting">
              {canEdit && openEditor === "meet" ? (
                <Suspense fallback={null}>
                  <MeetingEditor page={page} staff={staff!} onDone={done} />
                </Suspense>
              ) : (
                <MeetingCard page={page} slug={slug} onEdit={canEdit ? () => setOpenEditor("meet") : undefined} />
              )}
            </div>
          </div>
        </div>
        {canEdit && (
          <Suspense fallback={null}>
            <ProgressRail page={page} staff={staff!} onChanged={stagesChanged} locked={stagesLocked} />
          </Suspense>
        )}
        {(hasFiles || filtering) && (
          <FileToolbar
            query={query}
            onQuery={setQuery}
            prefs={prefs}
            onPrefs={setPrefs}
            found={filtering ? shown.reduce((sum, stage) => sum + stage.count, 0) : null}
            narrow={narrow}
          />
        )}
        {narrow && page.stages.length > 0 && <h2 className="stage-timeline-heading">{t("page.timeline").toLocaleUpperCase()}</h2>}
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
                : i === openStage
            }
            hidden={filtering && shown[i]!.count === 0 && !unreadable(i)}
            onToggle={() =>
              filtering
                ? setClosed((was) => {
                    const next = new Set(was);
                    if (!next.delete(i)) next.add(i);
                    return next;
                  })
                : setOpenStage(i === openStage ? -1 : i)
            }
            {...filesFor(stageFiles, i + 1)}
            files={shown[i]!.files}
            total={countFiles(filesFor(stageFiles, i + 1).files)}
            view={prefs.view}
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
            controls={
              canEdit ? (
                <Suspense fallback={null}>
                  <StageControls
                    page={page}
                    staff={staff!}
                    index={i}
                    onChanged={stagesChanged}
                    locked={stagesLocked}
                  />
                </Suspense>
              ) : undefined
            }
            editor={
              canEdit
                ? {
                    open: openEditor === `notes-${i}`,
                    onOpen: () => setOpenEditor(`notes-${i}`),
                    render: () => (
                      <Suspense fallback={null}>
                        <NotesEditor page={page} staff={staff!} index={i} onDone={done} />
                      </Suspense>
                    ),
                  }
                : undefined
            }
          />
        ))}
        {canEdit && (
          <Suspense fallback={null}>
            <AddStage page={page} staff={staff!} onChanged={stagesChanged} locked={stagesLocked} />
          </Suspense>
        )}
        <footer className="client-footer">{page.office.name}</footer>
      </div>
      {page.staff && (
        <StaffBar
          page={page}
          ready={ready}
          editing={editing}
          onMode={(next) => {
            setEditing(next);
            setOpenEditor(null);
          }}
          onPublished={() => onChanged?.()}
          onTour={onTour ?? (() => tour(false))}
        />
      )}
      {preview && <FilePreview {...preview} slug={slug} page={page} onClose={closePreview} />}
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
