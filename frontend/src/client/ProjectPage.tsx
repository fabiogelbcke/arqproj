// The client's project page, read-only (slice 2.3), after the fresh prototype's
// markup: its stylesheet (prototype.css) styles these same class names.
import { Suspense, lazy, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api, call, type Schemas } from "../api/client";
import { Toaster, toast } from "../ui/Toast";
import { EditButton } from "./EditButton";

// Staff editing code loads only once staff press "Editar" (A20): visitors never get it.
const DescriptionEditor = lazy(() => import("./Editors").then((m) => ({ default: m.DescriptionEditor })));
const DetailsEditor = lazy(() => import("./Editors").then((m) => ({ default: m.DetailsEditor })));
const MeetingEditor = lazy(() => import("./Editors").then((m) => ({ default: m.MeetingEditor })));
const NotesEditor = lazy(() => import("./Editors").then((m) => ({ default: m.NotesEditor })));
const AddStage = lazy(() => import("./StageEditing").then((m) => ({ default: m.AddStage })));
const ProgressRail = lazy(() => import("./StageEditing").then((m) => ({ default: m.ProgressRail })));
const StageControls = lazy(() => import("./StageEditing").then((m) => ({ default: m.StageControls })));
import { day, detailValue, googleCalendarLink, meetingWhen, paragraphs, type Page } from "./format";

const pad = (n: number) => String(n).padStart(2, "0");

type StageFiles = Schemas["StageFilesOut"];
type FileItem = Schemas["FileOut"];

/** Every stage's files, read live from the office's Drive (2.5). */
type FilesState = { stages: StageFiles[]; reference: string | null; failed: boolean };

function useStageFiles(slug: string, version: unknown): FilesState | null {
  const [state, setState] = useState<FilesState | null>(null); // null while loading
  useEffect(() => {
    call(api.GET("/api/pages/{slug}/files", { params: { path: { slug } } })).then(
      (found) => setState({ stages: found.stages, reference: found.reference ?? null, failed: false }),
      // Couldn't be fetched at all: every stage says so, with the support code.
      (failure: { requestId?: string | null }) =>
        setState({ stages: [], reference: failure?.requestId ?? null, failed: true }),
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

function FileCard({ file, slug, timeZone }: { file: FileItem; slug: string; timeZone: string }) {
  const { t, i18n } = useTranslation();
  // Only images and PDFs have previews (Drive's); other files show their type.
  const [thumb, setThumb] = useState<"thumb" | "original" | "none">(file.kind === "other" ? "none" : "thumb");
  const url = `/api/pages/${slug}/files/${encodeURIComponent(file.key)}`;
  const opens = file.kind === "image" || file.kind === "pdf";
  const extension = file.name.includes(".") ? file.name.split(".").pop()!.toUpperCase() : "";
  // Drive's preview first; for an image without one (local folders), the image itself.
  const src = thumb === "thumb" ? `${url}/thumb` : thumb === "original" ? `${url}?inline=true` : null;
  return (
    <div className="file">
      <a
        className="file__open"
        href={opens ? `${url}?inline=true` : url}
        {...(opens ? { target: "_blank", rel: "noopener" } : { download: file.name })}
        aria-label={t(opens ? "page.openFile" : "page.downloadFile", { name: file.name })}
      >
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
      </a>
    </div>
  );
}

function StageFilesList({
  files,
  reference,
  slug,
  timeZone,
}: {
  files: StageFiles | undefined;
  reference: string | null;
  slug: string;
  timeZone: string;
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
          <div className="files" data-view="grid">
            {group.files.map((file) => (
              <FileCard key={file.key} file={file} slug={slug} timeZone={timeZone} />
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
export function SiteHeader({ office }: { office: { name: string; logo_url?: string | null } }) {
  return (
    <div className="site">
      <div className="site__in">
        <div className="site__brand">
          {office.logo_url ? <img src={office.logo_url} alt={office.name} /> : <span>{office.name}</span>}
        </div>
        <div className="client-header-tools">
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
function Facts({ page, skipClient = false }: { page: Page; skipClient?: boolean }) {
  const { t, i18n } = useTranslation();
  const rows: Array<[string, string]> = [
    ...(skipClient ? [] : [[t("page.client"), page.client_name.toLocaleUpperCase(i18n.language)] as [string, string]]),
    [t("page.projectType"), page.project_type.toLocaleUpperCase(i18n.language)],
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

/** On phones: the client's name, opening to the details and the description. */
function MobileSummary({ page }: { page: Page }) {
  const { t, i18n } = useTranslation();
  return (
    <details className="facts-disclosure mobile-project-summary">
      <summary>
        <span className="facts-summary-label">{t("page.client")}</span>
        <strong>{page.client_name.toLocaleUpperCase(i18n.language)}</strong>
        <span className="facts-summary-action" aria-hidden="true">
          <Icon name="down" />
        </span>
      </summary>
      <dl className="facts">
        <Facts page={page} skipClient />
        <div className="mobile-project-description">
          <dt>{t("page.description")}</dt>
          <dd>{page.description ? <Description text={page.description} /> : <p>{t("page.noDescription")}</p>}</dd>
        </div>
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
            <>
              <span className="journey-kicker">{t("page.journeyKicker").toLocaleUpperCase()}</span>
              <h2>{t("page.journeyTitle")}</h2>
            </>
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
              <a href={`/api/pages/${slug}/meeting.ics`} download="reuniao.ics">
                {t("page.otherCalendar")}
              </a>
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
              {countFiles(files)
                ? t("page.fileCount", { count: countFiles(files), padded: pad(countFiles(files)) })
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
          <StageFilesList files={files} reference={reference} slug={slug} timeZone={page.timezone} />
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
}: {
  page: Page;
  ready: boolean;
  editing: boolean;
  onMode: (editing: boolean) => void;
  onPublished: () => void;
}) {
  const { t, i18n } = useTranslation();
  const [publishing, setPublishing] = useState(false);
  const staff = page.staff!;
  const draft = staff.status === "draft";
  const archived = staff.status === "archived"; // viewable, not editable (section 22)
  return (
    <nav className="dock" aria-label={t("page.staffBar")}>
      <a className="b" href="/painel/">
        <Icon name="left" />
        {t("page.backToPainel")}
      </a>
      <span className="dock__sep" />
      <span className="dock__title">
        {page.name}
        <small>{draft ? t("page.draftNote") : t("page.publishedNote")}</small>
      </span>
      {/* The prototype's switch: the page as the client sees it, or with controls. */}
      <div className="seg" role="group" aria-label={t("edit.mode")} data-on={editing ? "edit" : "view"}>
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
              const code = (failure as { code?: string }).code ?? "unexpected";
              const reference = (failure as { requestId?: string | null }).requestId;
              const message = i18n.exists(`errors.${code}`) ? t(`errors.${code}`) : t("errors.unexpected");
              toast(reference ? `${message} ${t("errors.reference", { id: reference })}` : message);
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

function Title({ name }: { name: string }) {
  const { i18n } = useTranslation();
  const [lead, ...rest] = name.trim().split(/\s+/);
  return (
    // The two parts are one name for screen readers ("/casa" + "jardim").
    <h1 className="client-project-title" title={name} aria-label={name}>
      <span className="project-title__lead">/{lead?.toLocaleLowerCase(i18n.language)}</span>
      {rest.length > 0 && (
        <strong className="project-title__tail">{rest.join(" ").toLocaleLowerCase(i18n.language)}</strong>
      )}
    </h1>
  );
}

export function ProjectPage({
  page,
  slug,
  ready = false,
  onChanged,
}: {
  page: Page;
  slug: string;
  ready?: boolean; // the staff session's CSRF token is in hand
  onChanged?: () => void;
}) {
  const { t } = useTranslation();
  const narrow = useNarrow();
  const cover = useRef<HTMLDivElement>(null);
  useCoverWipe(cover);
  const stageFiles = useStageFiles(slug, page);
  const [editing, setEditing] = useState(false);
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

  useEffect(() => {
    document.title = `${page.name} · ${page.office.name}`;
  }, [page.name, page.office.name]);

  const jump = (index: number) => {
    setOpenStage(index);
    const section = document.getElementById(`stage-${index}`);
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    section?.scrollIntoView({ behavior: reduce ? "instant" : "smooth", block: "start" });
    section?.querySelector("h2")?.focus({ preventScroll: true });
  };

  return (
    <div className={`client${canEdit ? " editing" : ""}`}>
      <SiteHeader office={page.office} />
      <div className="cwrap">
        <div className="project-opening">
          <header className="project-heading">
            <Title name={page.name} />
          </header>
          {narrow && <MobileSummary page={page} />}
          {page.cover_url && (
            <figure className="banner">
              <div className="banner__img" ref={cover}>
                <img src={page.cover_url} alt={t("page.cover", { name: page.name })} />
              </div>
            </figure>
          )}
        </div>
        <section className={`hero${narrow && !canEdit ? " mobile-view-hidden" : ""}`}>
          <div>
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
          <div>
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
        </section>
        <div className={`project-status${page.stages.length ? "" : " project-status--single"}`}>
          {!narrow && page.stages.length > 0 && (
            <div className="project-status__timeline">
              <Timeline page={page} onJump={jump} />
            </div>
          )}
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
        {canEdit && (
          <Suspense fallback={null}>
            <ProgressRail page={page} staff={staff!} onChanged={stagesChanged} locked={stagesLocked} />
          </Suspense>
        )}
        {narrow && page.stages.length > 0 && <h2 className="stage-timeline-heading">{t("page.timeline").toLocaleUpperCase()}</h2>}
        {page.stages.map((_, i) => (
          <Stage
            key={i}
            page={page}
            index={i}
            open={i === openStage}
            onToggle={() => setOpenStage(i === openStage ? -1 : i)}
            {...filesFor(stageFiles, i + 1)}
            slug={slug}
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
        />
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
