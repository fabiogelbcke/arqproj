// The client page's file tools, after the prototype: search, filter by type, sort,
// list or thumbnails, and a file's preview with "Salvar", "Abrir original" and
// "Enviar". The view and the order are remembered in this browser.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Schemas } from "../api/client";
import type { Page } from "./format";

type FileItem = Schemas["FileOut"];
type StageFiles = Schemas["StageFilesOut"];

export type FileType = "all" | "pdf" | "image" | "dwg" | "other";
export type FileSort = "updated" | "type" | "name";
export type FileView = "grid" | "list";
export type Prefs = { type: FileType; sort: FileSort; view: FileView };

const PREFS_KEY = "file-prefs";
const DEFAULT_PREFS: Prefs = { type: "all", sort: "updated", view: "grid" };

/** View and order as this browser last left them; the type filter starts fresh. */
export function usePrefs(): [Prefs, (change: Partial<Prefs>) => void] {
  const [prefs, setPrefs] = useState<Prefs>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}") as Partial<Prefs>;
      return {
        ...DEFAULT_PREFS,
        ...(saved.sort && ["updated", "type", "name"].includes(saved.sort) ? { sort: saved.sort } : {}),
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
        localStorage.setItem(PREFS_KEY, JSON.stringify({ sort: merged.sort, view: merged.view }));
      } catch {
        // Not remembered on this device.
      }
      return merged;
    });
  return [prefs, change];
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
  return [...files].sort((a, b) => {
    const name = byName.compare(a.name, b.name);
    if (sort === "name") return name;
    if (sort === "type") return byName.compare(extension(a.name), extension(b.name)) || name;
    return Date.parse(b.modified_at) - Date.parse(a.modified_at) || name; // newest first
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
}: {
  query: string;
  onQuery: (query: string) => void;
  prefs: Prefs;
  onPrefs: (change: Partial<Prefs>) => void;
  found: number | null; // null: not filtering
  narrow: boolean;
}) {
  const { t } = useTranslation();
  const search = (
    <>
      <label className="sr" htmlFor="client-file-search">
        {t("files.search")}
      </label>
      <input
        className="input"
        type="search"
        id="client-file-search"
        placeholder={t("files.searchPlaceholder")}
        value={query}
        onChange={(e) => onQuery(e.target.value)}
      />
    </>
  );
  const selects = (
    <>
      <label htmlFor="client-file-type">
        {t("files.type")}
        <select id="client-file-type" value={prefs.type} onChange={(e) => onPrefs({ type: e.target.value as FileType })}>
          <option value="all">{t("files.allTypes")}</option>
          <option value="pdf">PDF</option>
          <option value="image">{t("files.images")}</option>
          <option value="dwg">DWG</option>
          <option value="other">{t("files.others")}</option>
        </select>
      </label>
      <label htmlFor="client-file-sort">
        {t("files.sortBy")}
        <select id="client-file-sort" value={prefs.sort} onChange={(e) => onPrefs({ sort: e.target.value as FileSort })}>
          <option value="updated">{t("files.byUpdated")}</option>
          <option value="type">{t("files.byType")}</option>
          <option value="name">{t("files.byName")}</option>
        </select>
      </label>
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
        <details className="client-search-disclosure">
          <summary aria-label={t("files.search")} title={t("files.search")}>
            <SearchIcon />
          </summary>
          <div className="client-tool-popover">{search}</div>
        </details>
        <details className="client-organize-disclosure">
          <summary>{t("files.filterAndSort")}</summary>
          <div className="client-tool-popover client-file-controls">{selects}</div>
        </details>
        {views}
        {status}
      </div>
    );
  return (
    <div className="client-file-tools">
      <div className="search">
        <SearchIcon />
        {search}
      </div>
      <div className="client-file-controls">
        {selects}
        {views}
      </div>
      {status}
    </div>
  );
}

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
  const [broken, setBroken] = useState(false); // gone, expired, or not an image after all
  const url = `/api/pages/${slug}/files/${encodeURIComponent(file.key)}`;
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
    >
      <div className="file-preview__head">
        <h2 id="file-preview-title">{file.name}</h2>
        <button className="file-preview__close" type="button" aria-label={t("files.close")} onClick={onClose}>
          ×
        </button>
      </div>
      <div className="file-preview__content">
        {file.kind === "image" && !broken ? (
          <img src={`${url}?inline=true`} alt={file.name} onError={() => setBroken(true)} />
        ) : (
          <p>{file.kind === "pdf" ? t("files.pdfHint") : t("files.otherHint")}</p>
        )}
      </div>
      <div className="file-preview__actions">
        <button type="button" onClick={() => void save()}>
          {t("files.save")}
        </button>
        <a href={inline ? `${url}?inline=true` : url} {...(inline ? { target: "_blank", rel: "noopener" } : {})}>
          {t("files.openOriginal")}
        </a>
        <button
          type="button"
          aria-expanded={sending}
          aria-controls="file-preview-send-menu"
          onClick={() => setSending(!sending)}
        >
          {t("files.send")}
        </button>
      </div>
      <div className="file-preview__send-menu" id="file-preview-send-menu" hidden={!sending}>
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
