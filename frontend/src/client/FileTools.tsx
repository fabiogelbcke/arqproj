// The client page's file tools, after the prototype: search, filter by type, sort,
// list or thumbnails, and a file's preview with "Salvar", "Abrir original" and
// "Enviar". The view and the order are remembered in this browser.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { Schemas } from "../api/client";
import { PopoverDetails } from "../ui/PopoverDetails";
import { SearchBox } from "../ui/SearchBox";
import { SelectField } from "../ui/SelectField";
import { sortFromValue, sortLabelKey, sortOptions, sortValue, type Sort } from "../ui/sort";
import { useDismiss } from "../ui/useDismiss";
import { day, fileSource, type Page } from "./format";

type FileItem = Schemas["FileOut"];
type StageFiles = Schemas["StageFilesOut"];

export type FileType = "all" | "pdf" | "image" | "dwg" | "other";
export const FILE_SORT_KEYS = ["updated", "name", "type"] as const;
export type FileSort = Sort<(typeof FILE_SORT_KEYS)[number]>;
/** The files' orders, each in both directions, as the painel's (ui/sort). */
export const FILE_SORTS = sortOptions(FILE_SORT_KEYS, ["updated"]);
export type FileView = "grid" | "list";
export type Prefs = { type: FileType; sort: FileSort; view: FileView };

const PREFS_KEY = "file-prefs";
const DEFAULT_PREFS: Prefs = { type: "all", sort: { key: "updated", direction: "desc" }, view: "grid" };

/** A saved order: "name-desc", or from before directions "name" (its first direction). */
function savedSort(value: unknown): FileSort | null {
  if (typeof value !== "string") return null;
  return FILE_SORTS.find((sort) => sortValue(sort) === value) ?? FILE_SORTS.find((sort) => sort.key === value) ?? null;
}

/** View and order as this browser last left them; the type filter starts fresh. */
export function usePrefs(): [Prefs, (change: Partial<Prefs>) => void] {
  const [prefs, setPrefs] = useState<Prefs>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}") as { sort?: unknown; view?: FileView };
      return {
        ...DEFAULT_PREFS,
        sort: savedSort(saved.sort) ?? DEFAULT_PREFS.sort,
        ...(saved.view && ["grid", "list"].includes(saved.view) ? { view: saved.view } : {}),
      };
    } catch {
      return DEFAULT_PREFS;
    }
  });
  const change = (next: Partial<Prefs>) =>
    setPrefs((current) => {
      const merged = { ...current, ...next };
      try {
        localStorage.setItem(PREFS_KEY, JSON.stringify({ sort: sortValue(merged.sort), view: merged.view }));
      } catch {
        // Not remembered on this device.
      }
      return merged;
    });
  return [prefs, change];
}

export function fileSize(bytes: number | null | undefined, locale: string): string {
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

export const extension = (name: string) => (name.includes(".") ? name.split(".").pop()!.toLowerCase() : "");

export function category(file: FileItem): Exclude<FileType, "all"> {
  if (file.kind === "image") return "image";
  if (file.kind === "pdf") return "pdf";
  return extension(file.name) === "dwg" ? "dwg" : "other";
}

/** Lowercase, without accents: "planta" finds "Plânta" and "PLANTA". */
const normalize = (text: string) =>
  text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();

const byName = new Intl.Collator("pt-BR", { numeric: true, sensitivity: "base" });

export function sortFiles(files: FileItem[], sort: FileSort): FileItem[] {
  const way = sort.direction === "asc" ? 1 : -1;
  return [...files].sort((a, b) => {
    const name = byName.compare(a.name, b.name);
    if (sort.key === "name") return way * name;
    if (sort.key === "type") return way * byName.compare(extension(a.name), extension(b.name)) || name;
    return way * (Date.parse(a.modified_at) - Date.parse(b.modified_at)) || name;
  });
}

/** A stage's files that match the search (a file's name or the stage's title) and
 *  the type, each group sorted; with how many matched. */
export function shownFiles(
  files: StageFiles,
  stageTitle: string,
  query: string,
  prefs: Prefs,
): { files: StageFiles; count: number } {
  const wanted = normalize(query.trim());
  let count = 0;
  const groups = files.groups
    .map((group) => {
      const kept = group.files.filter(
        (file) =>
          (!wanted || normalize(`${file.name} ${stageTitle}`).includes(wanted)) &&
          (prefs.type === "all" || category(file) === prefs.type),
      );
      count += kept.length;
      return { ...group, files: sortFiles(kept, prefs.sort) };
    })
    .filter((group) => group.files.length > 0);
  return { files: { ...files, groups }, count };
}

const SearchIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <circle cx="11" cy="11" r="6" />
    <path d="M20 20l-4.5-4.5" />
  </svg>
);

export function FileToolbar({
  query,
  onQuery,
  prefs,
  onPrefs,
  found,
  narrow,
  share,
}: {
  share?: ReactNode; // "Compartilhar arquivos", at the toolbar's end
  query: string;
  onQuery: (query: string) => void;
  prefs: Prefs;
  onPrefs: (change: Partial<Prefs>) => void;
  found: number | null; // null: not filtering
  narrow: boolean;
}) {
  const { t } = useTranslation();
  // The painel's search and sort (ui/SearchBox, ui/SelectField): one order
  // dropdown with its direction; the labels are for screen readers.
  const search = (
    <SearchBox
      className="client-file-search"
      id="client-file-search"
      label={t("files.search")}
      placeholder={t("files.searchPlaceholder")}
      value={query}
      onChange={onQuery}
    />
  );
  const selects = (
    <>
      <SelectField
        id="client-file-type"
        label={t("files.type")}
        labelHidden
        value={prefs.type}
        options={[
          { value: "all", label: t("files.allTypes") },
          { value: "pdf", label: "PDF" },
          { value: "image", label: t("files.images") },
          { value: "dwg", label: "DWG" },
          { value: "other", label: t("files.others") },
        ]}
        onChange={(value) => onPrefs({ type: value as FileType })}
      />
      <SelectField
        id="client-file-sort"
        label={t("files.sortBy")}
        labelHidden
        value={sortValue(prefs.sort)}
        options={FILE_SORTS.map((option) => ({ value: sortValue(option), label: t(sortLabelKey(option)) }))}
        onChange={(value) => onPrefs({ sort: sortFromValue(value, FILE_SORTS, DEFAULT_PREFS.sort) })}
      />
    </>
  );
  const views = (
    <div className="file-view-switch" role="group" aria-label={t("files.view")}>
      <button
        type="button"
        aria-label={t("files.asList")}
        title={t("files.list")}
        aria-pressed={prefs.view === "list"}
        onClick={() => onPrefs({ view: "list" })}
      >
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M3 5h14M3 10h14M3 15h14" />
        </svg>
      </button>
      <button
        type="button"
        aria-label={t("files.asGrid")}
        title={t("files.grid")}
        aria-pressed={prefs.view === "grid"}
        onClick={() => onPrefs({ view: "grid" })}
      >
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <rect x="3" y="3" width="5" height="5" />
          <rect x="12" y="3" width="5" height="5" />
          <rect x="3" y="12" width="5" height="5" />
          <rect x="12" y="12" width="5" height="5" />
        </svg>
      </button>
    </div>
  );
  const status = (
    <span className="client-search-status" role="status" aria-live="polite">
      {found === null ? "" : t("files.found", { count: found })}
    </span>
  );
  if (narrow)
    return (
      <div className="client-file-tools">
        <PopoverDetails className="client-search-disclosure">
          <summary aria-label={t("files.search")} title={t("files.search")}>
            <SearchIcon />
          </summary>
          <div className="client-tool-popover">{search}</div>
        </PopoverDetails>
        <PopoverDetails className="client-organize-disclosure">
          <summary>{t("files.filterAndSort")}</summary>
          <div className="client-tool-popover file-tools__controls">{selects}</div>
        </PopoverDetails>
        {views}
        {share}
        {status}
      </div>
    );
  return (
    <div className="client-file-tools">
      {search}
      <div className="file-tools__controls">
        {selects}
        {views}
        {share}
      </div>
      {status}
    </div>
  );
}

/** The dialogs' ×, drawn: a "×" character sits low in its box. */
const CloseIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
);

/** Where a file is on the page: its stage (from 1) and subfolder, if any. */
export type FilePlace = { position: number; folder: string | null };

/** A file's own link: the page's address with its stage, subfolder and name
 *  (`/casa-jardim?etapa=3&pasta=Renders&arquivo=Fachada.jpg`), opening the page at
 *  that file with its preview open (ProjectPage). Not its key: keys expire, and
 *  Drive's ids never reach the page (backend/web/page_files.py). */
export function fileLink(slug: string, place: FilePlace, name: string): string {
  const query = new URLSearchParams({ etapa: String(place.position) });
  if (place.folder) query.set("pasta", place.folder);
  query.set("arquivo", name);
  return `${window.location.origin}/${slug}?${query}`;
}

/** The file a page address points at, if any (fileLink). */
export function linkedFile(search: string): (FilePlace & { name: string }) | null {
  const query = new URLSearchParams(search);
  const name = query.get("arquivo");
  const position = Number(query.get("etapa"));
  if (!name || !Number.isInteger(position) || position < 1) return null;
  return { position, folder: query.get("pasta"), name };
}

/** A file's preview (the prototype's): the image itself, or a word about PDFs and
 *  other files; "Salvar", "Abrir original" and "Enviar" (by email or WhatsApp, the
 *  page's address at this file: a file's own download address works only for a while,
 *  and the page keeps its password, if it has one). */
export function FilePreview({
  file,
  place,
  slug,
  page,
  onClose,
}: {
  file: FileItem;
  place: FilePlace;
  slug: string;
  page: Page;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const dialog = useRef<HTMLDialogElement>(null);
  const [sending, setSending] = useState(false);
  const sendButton = useRef<HTMLButtonElement>(null);
  const sendMenu = useRef<HTMLDivElement>(null);
  useDismiss([sendButton, sendMenu], sending, () => setSending(false));
  const [broken, setBroken] = useState(false); // gone, expired, or not an image after all
  const url = fileSource.address(slug, file.key, "file")!;
  const shown = fileSource.address(slug, file.key, "inline")!;
  const inline = file.kind === "image" || file.kind === "pdf";
  const pageUrl = fileLink(slug, place, file.name);
  const message = `${file.name} · ${page.name}\n${pageUrl}`;
  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) {
      // Older browsers (and test DOMs) without modal dialogs: just open it.
      if (typeof element.showModal === "function") element.showModal();
      else element.setAttribute("open", "");
    }
    return () => (typeof element?.close === "function" ? element.close() : element?.removeAttribute("open"));
  }, []);
  const save = async () => {
    // On a phone, the share sheet saves to Files or Photos; elsewhere a download.
    try {
      if (window.matchMedia?.("(pointer: coarse)").matches && navigator.canShare) {
        const response = await fetch(url);
        // Gone, moved or expired: the link below shows the page's own message.
        if (!response.ok) throw new Error(`file ${response.status}`);
        const blob = await response.blob();
        const shared = new File([blob], file.name, { type: blob.type || "application/octet-stream" });
        if (navigator.canShare({ files: [shared] })) {
          await navigator.share({ files: [shared], title: file.name });
          return;
        }
      }
    } catch (error) {
      if ((error as Error)?.name === "AbortError") return;
    }
    if (fileSource.bundled) {
      const link = Object.assign(document.createElement("a"), { href: url, download: file.name });
      link.click();
      return;
    }
    // Sent as an attachment, so the page stays (a link added to the page would
    // sit behind the open dialog, where clicks do nothing).
    window.location.assign(url);
  };
  return (
    <dialog
      ref={dialog}
      className="file-preview"
      aria-labelledby="file-preview-title"
      // Closed by the person (Esc), not by React re-running the effect in
      // development, which closes the dialog and opens it again at once.
      onClose={() => !dialog.current?.open && onClose()}
      // A click on the dimmed page around it lands on the dialog itself (it has no padding).
      onClick={(event) => event.target === dialog.current && onClose()}
    >
      <div className="file-preview__head">
        <h2 id="file-preview-title">{file.name}</h2>
        <button className="file-preview__close" type="button" aria-label={t("files.close")} onClick={onClose}>
          <CloseIcon />
        </button>
      </div>
      <div className="file-preview__content">
        {file.kind === "image" && !broken ? (
          <img src={shown} alt={file.name} onError={() => setBroken(true)} />
        ) : (
          <p>{file.kind === "pdf" ? t("files.pdfHint") : t("files.otherHint")}</p>
        )}
      </div>
      <div className="file-preview__actions">
        <button type="button" onClick={() => void save()}>
          {t("files.save")}
        </button>
        <a href={inline ? shown : url} {...(inline ? { target: "_blank", rel: "noopener" } : {})}>
          {t("files.openOriginal")}
        </a>
        <button
          ref={sendButton}
          type="button"
          aria-expanded={sending}
          aria-controls="file-preview-send-menu"
          onClick={() => setSending(!sending)}
        >
          {t("files.send")}
        </button>
      </div>
      <div ref={sendMenu} className="file-preview__send-menu" id="file-preview-send-menu" hidden={!sending}>
        <a href={`mailto:?subject=${encodeURIComponent(file.name)}&body=${encodeURIComponent(message)}`}>
          {t("files.byEmail")}
        </a>
        <a href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noopener noreferrer">
          WhatsApp
        </a>
      </div>
    </dialog>
  );
}

/** A document's versions (A25), newest first: the current one marked, each with
 *  its date and size, to open or download. Opened from "6 versões" on its
 *  card, so a card stays one size however many versions there are. */
export function FileVersions({
  file,
  slug,
  timeZone,
  onClose,
}: {
  file: FileItem;
  slug: string;
  timeZone: string;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) {
      if (typeof element.showModal === "function") element.showModal();
      else element.setAttribute("open", "");
    }
    return () => (typeof element?.close === "function" ? element.close() : element?.removeAttribute("open"));
  }, []);
  const all = [file, ...file.older];
  return (
    <dialog
      ref={dialog}
      className="file-preview file-versions"
      aria-labelledby="file-versions-title"
      onClose={() => !dialog.current?.open && onClose()}
      onClick={(event) => event.target === dialog.current && onClose()}
    >
      <div className="file-preview__head">
        <div>
          <h2 id="file-versions-title">{file.name}</h2>
          <p>{t("files.versionCount", { count: all.length })}</p>
        </div>
        <button className="file-preview__close" type="button" aria-label={t("files.close")} onClick={onClose}>
          <CloseIcon />
        </button>
      </div>
      <ol className="file-versions__list">
        {all.map((version, i) => {
          const inline = version.kind === "image" || version.kind === "pdf";
          return (
            <li key={version.key} className={i === 0 ? "is-current" : undefined}>
              <span className="file-versions__number">{t("files.version", { version: version.version ?? 1 })}</span>
              <span className="file-versions__about">
                {i === 0 && <span className="file-versions__current">{t("files.current")}</span>}
                {[day(version.modified_at, i18n.language, timeZone), fileSize(version.size, i18n.language)]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
              <span className="file-versions__actions">
                {inline && (
                  <a
                    href={fileSource.address(slug, version.key, "inline")!}
                    target="_blank"
                    rel="noopener"
                    aria-label={t("files.openVersion", { version: version.version ?? 1, name: file.name })}
                  >
                    {t("files.open")}
                  </a>
                )}
                <a
                  href={fileSource.address(slug, version.key, "file")!}
                  download={fileSource.bundled ? version.name : undefined}
                  aria-label={t("files.downloadVersion", { version: version.version ?? 1, name: file.name })}
                >
                  {t("files.download")}
                </a>
              </span>
            </li>
          );
        })}
      </ol>
    </dialog>
  );
}
