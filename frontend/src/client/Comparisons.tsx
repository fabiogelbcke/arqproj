// Edit mode: before-and-after comparisons (A46). The "+" card at the end of each
// stage's (and section's) files offers "Enviar arquivos" and "Comparação antes e
// depois": two images and a name, uploaded as two files whose names make them a
// comparison (`Cozinha (antes).jpg`, `Cozinha (depois).jpg`; nothing is stored).
// A comparison's "⋯" changes both images at once: its name and labels, a new
// version of either image, moving it, hiding it.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, call, type Schemas } from "../api/client";
import { LIMITS } from "../api/limits";
import { capture } from "../posthog";
import { BeforeAfter } from "../ui/BeforeAfter";
import { Button } from "../ui/Button";
import { DialogFrame } from "../ui/DialogFrame";
import { MoreIcon } from "../ui/MoreIcon";
import { TextField } from "../ui/TextField";
import { toast, toastError } from "../ui/Toast";
import styles from "../ui/ui.module.css";
import { useDismiss } from "../ui/useDismiss";
import { type Page } from "./format";
import { movePlaces, sendFile, UPLOAD_MAX_MB, UploadBroke, uploadFile, type MovePlace } from "./StageUploads";

type Staff = NonNullable<Page["staff"]>;
type FileItem = Schemas["FileOut"];

// What the page shows in itself (backend/web/page_files.py, INLINE_IMAGES).
export const COMPARABLE = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const UPLOAD_MAX = UPLOAD_MAX_MB * 1024 * 1024;

/** Why this file can't be a side, if it can't. */
function refusal(file: File): string | null {
  if (!COMPARABLE.includes(file.type)) return "comparison_not_image";
  if (file.size > UPLOAD_MAX) return "file_too_large";
  return null;
}

/** A side's name in Drive, as the server writes it (backend/documents/comparisons.py):
 *  "Fachada (antes - Estudo)". */
const savedAs = (title: string, marker: string, label: string) =>
  `${title} (${label.trim() ? `${marker} - ${label.trim()}` : marker})`;

/** Moves a comparison, both its images, to a stage and maybe one of its sections. */
export const moveComparison = (page: Page, slug: string, key: string, to: { position: number; section: string | null }) =>
  call(
    api.POST("/api/pages/{slug}/comparisons/{key}/move", {
      params: { path: { slug, key } },
      body: { position: to.position, row_version: page.staff!.row_version, ...(to.section ? { folder: to.section } : {}) },
    }),
  );

/** The "+" card after a stage's or a section's files. */
export function AddCard({
  staff,
  position,
  section,
  inputId,
  folder,
  onChanged,
}: {
  staff: Staff;
  position: number;
  section: string | null; // the section it adds to; null: the stage's own files
  inputId: string; // the drop area's file chooser for this place (StageDrop)
  folder: string; // the folder's path, as staff know it in Drive
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<false | "menu" | "compare">(false);
  const menu = useRef<HTMLDivElement>(null);
  useDismiss(menu, open === "menu", () => setOpen(false));
  return (
    <div ref={menu} className={`file file--add menu${open === "menu" ? " is-open" : ""}`}>
      <button
        type="button"
        className="file--add__button"
        aria-haspopup="true"
        aria-expanded={open === "menu"}
        aria-label={section ? t("compare.addToSection", { section }) : t("compare.add")}
        onClick={() => setOpen(open === "menu" ? false : "menu")}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M12 5v14M5 12h14" />
        </svg>
        <span>{t("compare.addShort")}</span>
      </button>
      {open === "menu" && (
        <div className="menu__list" role="menu">
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              document.getElementById(inputId)?.click(); // the drop area's own chooser
            }}
          >
            {t("compare.sendFiles")}
          </button>
          <button type="button" role="menuitem" onClick={() => setOpen("compare")}>
            {t("compare.new")}
            <small>{t("compare.newNote")}</small>
          </button>
        </div>
      )}
      {open === "compare" && (
        <NewComparison
          staff={staff}
          position={position}
          section={section}
          folder={folder}
          onClose={() => setOpen(false)}
          onChanged={onChanged}
        />
      )}
    </div>
  );
}

/** One side's image: chosen or dropped, shown as chosen, with its label. */
function SidePicker({
  word,
  file,
  label,
  onFile,
  onLabel,
}: {
  word: string; // "Antes", "Depois": the label until one is typed
  file: File | null;
  label: string;
  onFile: (file: File) => void;
  onLabel: (label: string) => void;
}) {
  const { t } = useTranslation();
  const chooser = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const preview = useObjectUrl(file);
  return (
    <div className="compare-side">
      <button
        type="button"
        className={`compare-side__image${over ? " over" : ""}${preview ? " is-chosen" : ""}`}
        onClick={() => chooser.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          const dropped = event.dataTransfer.files[0];
          if (dropped) onFile(dropped);
        }}
      >
        {preview ? <img src={preview} alt="" /> : <span className="compare-side__plus" aria-hidden="true" />}
        <span className="compare-side__word">{label.trim() || word}</span>
        <span className="compare-side__action">{preview ? t("compare.change") : t("compare.choose")}</span>
      </button>
      <input
        ref={chooser}
        type="file"
        hidden
        accept={COMPARABLE.join(",")}
        aria-label={t("compare.chooseSide", { side: word })}
        onChange={(event) => {
          const chosen = event.target.files?.[0];
          event.target.value = ""; // the same file can be chosen again
          if (chosen) onFile(chosen);
        }}
      />
      <TextField
        label={t("compare.label", { side: word })}
        placeholder={word}
        value={label}
        onChange={onLabel}
        maxLength={LIMITS.comparisonLabel}
      />
    </div>
  );
}

function useObjectUrl(file: File | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file) return setUrl(null);
    const made = URL.createObjectURL(file);
    setUrl(made);
    return () => URL.revokeObjectURL(made);
  }, [file]);
  return url;
}

/** "Comparação antes e depois": a name, two images and their labels, a preview
 *  of the slider, then both go up. */
function NewComparison({
  staff,
  position,
  section,
  folder,
  onClose,
  onChanged,
}: {
  staff: Staff;
  position: number;
  section: string | null;
  folder: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [before, setBefore] = useState<File | null>(null);
  const [after, setAfter] = useState<File | null>(null);
  const [labels, setLabels] = useState({ before: "", after: "" });
  const [problem, setProblem] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null); // both images', while sending
  const beforeUrl = useObjectUrl(before);
  const afterUrl = useObjectUrl(after);
  const words = { before: t("compare.before"), after: t("compare.after") };
  const pick = (side: "before" | "after") => (file: File) => {
    const refused = refusal(file);
    setProblem(refused && t(`errors.${refused}`, { max: UPLOAD_MAX_MB }));
    if (refused) return;
    (side === "before" ? setBefore : setAfter)(file);
    // The first image's name, without its extension, until a name is typed.
    if (!title.trim() && side === "before") setTitle(file.name.replace(/\.[^.]+$/, "").slice(0, LIMITS.comparisonTitle));
  };
  const ready = !!before && !!after && !!title.trim() && progress === null;
  const send = async () => {
    if (!before || !after) return;
    setProgress(0);
    setProblem(null);
    const path = { project_id: staff.project_id, position };
    try {
      const opened = await call(
        api.POST("/api/projects/{project_id}/stages/{position}/comparisons", {
          params: { path },
          body: {
            row_version: staff.row_version,
            title: title.trim(),
            ...(section ? { folder: section } : {}),
            before: { name: before.name, size: before.size, mime_type: before.type },
            after: { name: after.name, size: after.size, mime_type: after.type },
            ...(labels.before.trim() ? { before_label: labels.before.trim() } : {}),
            ...(labels.after.trim() ? { after_label: labels.after.trim() } : {}),
          },
        }),
      );
      const total = before.size + after.size || 1;
      const sent = { before: 0, after: 0 };
      const track = (side: "before" | "after", file: File) => (fraction: number) => {
        sent[side] = fraction * file.size;
        setProgress((sent.before + sent.after) / total);
      };
      await Promise.all(
        (
          [
            [opened.before_url, before, "before"],
            [opened.after_url, after, "after"],
          ] as const
        ).map(([url, file, side]) =>
          sendFile(url, file, track(side, file)).catch((broke) =>
            broke instanceof UploadBroke
              ? call(
                  api.POST("/api/projects/{project_id}/stages/{position}/uploads/failed", {
                    params: { path },
                    body: { name: file.name, size: file.size, status: broke.status, detail: broke.detail },
                  }),
                ) // always an error: "upload_failed", with the support code
              : Promise.reject(broke),
          ),
        ),
      );
      capture("comparison_uploaded", { stage_position: position });
      toast(t("compare.sent", { name: title.trim() }));
      onClose();
      onChanged(); // the page lists Drive again (A10)
    } catch (failure) {
      // The dialog stays, with what was chosen, to try again.
      setProgress(null);
      toastError(failure, { max: UPLOAD_MAX_MB });
      onChanged(); // one image may have gone up: the page shows it on its own
    }
  };
  return (
    <DialogFrame title={t("compare.new")} onClose={progress === null ? onClose : () => {}} outsideCloses={false}>
      <form
        className="compare-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (ready) void send();
        }}
      >
        <TextField
          label={t("compare.title")}
          placeholder={t("compare.titlePlaceholder")}
          value={title}
          onChange={setTitle}
          maxLength={LIMITS.comparisonTitle}
          isRequired
          autoFocus
        />
        <div className="compare-form__sides">
          <SidePicker
            word={words.before}
            file={before}
            label={labels.before}
            onFile={pick("before")}
            onLabel={(label) => setLabels({ ...labels, before: label })}
          />
          <SidePicker
            word={words.after}
            file={after}
            label={labels.after}
            onFile={pick("after")}
            onLabel={(label) => setLabels({ ...labels, after: label })}
          />
        </div>
        {beforeUrl && afterUrl && (
          <div className="compare-form__preview" aria-label={t("compare.preview")} role="group">
            <BeforeAfter
              title={title.trim() || words.before}
              before={{ src: beforeUrl, label: labels.before.trim() || words.before }}
              after={{ src: afterUrl, label: labels.after.trim() || words.after }}
            />
          </div>
        )}
        <p className={styles.hint}>
          {t("compare.note", {
            folder,
            before: savedAs(title.trim() || t("compare.titlePlaceholderShort"), t("compare.markerBefore"), labels.before),
            after: savedAs(title.trim() || t("compare.titlePlaceholderShort"), t("compare.markerAfter"), labels.after),
            max: UPLOAD_MAX_MB,
          })}
        </p>
        {problem && (
          <p className={styles.fieldError} role="alert">
            {problem}
          </p>
        )}
        {progress !== null && (
          <progress className="upload-bar" max={1} value={progress} aria-label={t("compare.sending", { name: title })} />
        )}
        <div className={styles.confirmActions}>
          <Button onPress={onClose} isDisabled={progress !== null}>
            {t("confirm.cancel")}
          </Button>
          <Button variant="primary" type="submit" isDisabled={!ready}>
            {t("compare.send")}
          </Button>
        </div>
      </form>
    </DialogFrame>
  );
}

/** "Editar comparação": its name and labels, which are in its images' names. */
function EditComparison({
  slug,
  file,
  onClose,
  onChanged,
}: {
  slug: string;
  file: FileItem;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const comparison = file.comparison!;
  const [title, setTitle] = useState(file.name);
  const [labels, setLabels] = useState({ before: comparison.before_label ?? "", after: comparison.after_label ?? "" });
  const [busy, setBusy] = useState(false);
  const words = { before: t("compare.before"), after: t("compare.after") };
  const unchanged =
    title.trim() === file.name &&
    labels.before.trim() === (comparison.before_label ?? "") &&
    labels.after.trim() === (comparison.after_label ?? "");
  const save = async () => {
    setBusy(true);
    try {
      await call(
        api.POST("/api/pages/{slug}/comparisons/{key}/edit", {
          params: { path: { slug, key: file.key } },
          body: { title: title.trim(), before_label: labels.before.trim(), after_label: labels.after.trim() },
        }),
      );
      toast(t("compare.edited", { name: title.trim() }));
      onClose();
      onChanged();
    } catch (failure) {
      toastError(failure);
    } finally {
      setBusy(false);
    }
  };
  return (
    <DialogFrame title={t("compare.edit")} onClose={onClose}>
      <form
        className="compare-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (unchanged) onClose();
          else if (title.trim() && !busy) void save();
        }}
      >
        <TextField
          label={t("compare.title")}
          value={title}
          onChange={setTitle}
          maxLength={LIMITS.comparisonTitle}
          isRequired
          autoFocus
        />
        <div className="compare-form__sides">
          {(["before", "after"] as const).map((side) => (
            <TextField
              key={side}
              label={t("compare.label", { side: words[side] })}
              placeholder={words[side]}
              value={labels[side]}
              onChange={(label) => setLabels({ ...labels, [side]: label })}
              maxLength={LIMITS.comparisonLabel}
            />
          ))}
        </div>
        <p className={styles.hint}>{t("compare.editNote")}</p>
        <div className={styles.confirmActions}>
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button variant="primary" type="submit" isDisabled={busy || !title.trim()}>
            {t("projectSettings.save")}
          </Button>
        </div>
      </form>
    </DialogFrame>
  );
}

/** A comparison's "⋯" in edit mode: what FileMenu offers a file, for both images. */
export function ComparisonMenu({
  slug,
  file,
  page,
  position,
  folder = null,
  sections = [],
  onChanged,
}: {
  slug: string;
  file: FileItem; // its card: the "before" image, with the "after" one in `comparison`
  page: Page;
  position: number;
  folder?: string | null;
  sections?: string[][];
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const comparison = file.comparison!;
  const [open, setOpen] = useState<false | "menu" | "move" | "edit">(false);
  const menu = useRef<HTMLDivElement>(null);
  useDismiss(menu, open === "menu" || open === "move", () => setOpen(false));
  const [busy, setBusy] = useState(false);
  const words = {
    before: comparison.before_label ?? t("compare.before"),
    after: comparison.after_label ?? t("compare.after"),
  };
  const act = async (request: () => Promise<unknown>, done: string) => {
    setBusy(true);
    try {
      await request();
      setOpen(false);
      toast(done);
      onChanged();
    } catch (failure) {
      toastError(failure, { max: UPLOAD_MAX_MB });
    } finally {
      setBusy(false);
    }
  };
  // "Nova versão": the chosen image goes up as the next version of that side (A25).
  const chooser = useRef<HTMLInputElement>(null);
  const [side, setSide] = useState<"before" | "after">("before");
  const [sending, setSending] = useState<number | null>(null);
  const sideKey = side === "before" ? file.key : comparison.after.key;
  const sideName = side === "before" ? comparison.before_name : comparison.after_name;
  const sendVersion = async (chosen: File) => {
    setSending(0);
    await act(
      () => uploadFile(page.staff!, position, chosen, setSending, sideKey),
      t("compare.versionSent", { side: words[side], name: file.name }),
    );
    setSending(null);
  };
  const places = movePlaces(page, sections, position, folder);
  const move = (to: MovePlace) =>
    act(() => moveComparison(page, slug, file.key, to), t("edit.fileMoved", { name: file.name, stage: to.done }));
  const hide = () =>
    act(
      () => call(api.POST("/api/pages/{slug}/comparisons/{key}/hide", { params: { path: { slug, key: file.key } } })),
      t("edit.fileHidden", { name: file.name }),
    );
  return (
    <div
      ref={menu}
      className={`filemenu menu${open === "menu" || open === "move" ? " is-open" : ""}`}
      onBlur={(event) => !event.currentTarget.contains(event.relatedTarget) && (open === "menu" || open === "move") && setOpen(false)}
    >
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open === "menu" || open === "move"}
        aria-label={t("edit.fileActions", { name: file.name })}
        onClick={() => setOpen(open ? false : "menu")}
      >
        <MoreIcon />
      </button>
      <input
        ref={chooser}
        type="file"
        hidden
        // The same type as that image, or it wouldn't be a version of it.
        accept={sideName.includes(".") ? `.${sideName.split(".").pop()}` : COMPARABLE.join(",")}
        aria-label={t("compare.newVersion", { side: words[side] })}
        onChange={(event) => {
          const chosen = event.target.files?.[0];
          event.target.value = "";
          if (chosen) void sendVersion(chosen);
        }}
      />
      {sending !== null && (
        <progress
          className="upload-bar filemenu__progress"
          max={1}
          value={sending}
          aria-label={t("edit.sending", { name: file.name })}
        />
      )}
      {open === "menu" && (
        <div className="menu__list" role="menu">
          <button type="button" role="menuitem" disabled={busy} onClick={() => setOpen("edit")}>
            {t("compare.edit")}
            <small>{t("compare.editShort")}</small>
          </button>
          {(["before", "after"] as const).map((which) => (
            <button
              key={which}
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={() => {
                setOpen(false);
                setSide(which);
                // After the input's `accept` follows the side chosen.
                requestAnimationFrame(() => chooser.current?.click());
              }}
            >
              {t("compare.newVersion", { side: words[which] })}
            </button>
          ))}
          {places.length > 0 && (
            <button type="button" role="menuitem" disabled={busy} onClick={() => setOpen("move")}>
              {t("edit.moveFile")}
            </button>
          )}
          <hr />
          <button type="button" role="menuitem" disabled={busy} onClick={() => void hide()}>
            {t("edit.hideFile")}
            <small>{t("compare.hideNote")}</small>
          </button>
        </div>
      )}
      {open === "move" && (
        <div className="menu__list" role="menu" aria-label={t("edit.moveFileTo", { name: file.name })}>
          {places.map((place) => (
            <button
              key={`${place.position}/${place.section ?? ""}`}
              type="button"
              role="menuitem"
              className={place.section ? "menu__sub" : undefined}
              disabled={busy}
              onClick={() => void move(place)}
            >
              {place.label}
            </button>
          ))}
          <hr />
          <button type="button" role="menuitem" disabled={busy} onClick={() => setOpen("menu")}>
            {t("edit.menuBack")}
          </button>
        </div>
      )}
      {open === "edit" && <EditComparison slug={slug} file={file} onClose={() => setOpen(false)} onChanged={onChanged} />}
    </div>
  );
}
