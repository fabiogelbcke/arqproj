// Edit mode: the prototype's drop area under each stage's files, and each file's
// menu ("Ocultar do cliente"). Files go from the browser straight to Drive (A31):
// the app opens the upload, the browser sends the bytes to the address it gets.
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api, call, type Schemas } from "../api/client";
import { toast } from "../ui/Toast";
import type { Page } from "./format";

type Staff = NonNullable<Page["staff"]>;
type FileItem = Schemas["FileOut"];

export const UPLOAD_MAX_MB = 100; // the server checks it too
const UPLOAD_MAX = UPLOAD_MAX_MB * 1024 * 1024;

/** One PUT with the whole file, reporting progress (which fetch can't). */
export function sendFile(url: string, file: File, onProgress: (fraction: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", url);
    if (file.type) request.setRequestHeader("Content-Type", file.type);
    request.upload.onprogress = (event) => event.lengthComputable && onProgress(event.loaded / event.total);
    request.onload = () => (request.status < 300 ? resolve() : reject(new ApiError("unexpected", request.status)));
    request.onerror = () => reject(new ApiError("network"));
    request.send(file);
  });
}

function useMessage() {
  const { t, i18n } = useTranslation();
  return (failure: unknown) => {
    const error = failure instanceof ApiError ? failure : new ApiError("unexpected");
    const message = i18n.exists(`errors.${error.code}`)
      ? t(`errors.${error.code}`, { max: UPLOAD_MAX_MB })
      : t("errors.unexpected");
    return error.requestId ? `${message} ${t("errors.reference", { id: error.requestId })}` : message;
  };
}

type Sending = { id: number; name: string; progress: number; failed?: string };

/** "Solte arquivos aqui ou escolha no computador", and how each upload goes. */
export function StageDrop({
  staff,
  position,
  folder,
  onChanged,
}: {
  staff: Staff;
  position: number;
  folder: string; // the stage folder's name, as staff know it in Drive
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const message = useMessage();
  const [over, setOver] = useState(false);
  const [sending, setSending] = useState<Sending[]>([]);
  const next = useRef(0);
  const update = (id: number, change: Partial<Sending>) =>
    setSending((all) => all.map((item) => (item.id === id ? { ...item, ...change } : item)));

  const sendOne = async (file: File) => {
    const id = (next.current += 1);
    setSending((all) => [...all, { id, name: file.name, progress: 0 }]);
    try {
      if (file.size > UPLOAD_MAX) throw new ApiError("file_too_large");
      const opened = await call(
        api.POST("/api/projects/{project_id}/stages/{position}/uploads", {
          params: { path: { project_id: staff.project_id, position } },
          body: { row_version: staff.row_version, name: file.name, size: file.size, mime_type: file.type },
        }),
      );
      await sendFile(opened.upload_url, file, (progress) => update(id, { progress }));
      setSending((all) => all.filter((item) => item.id !== id));
      return true;
    } catch (failure) {
      update(id, { failed: message(failure) });
      return false;
    }
  };

  const upload = async (files: File[]) => {
    if (!files.length) return;
    const sent = (await Promise.all(files.map(sendOne))).filter(Boolean).length;
    if (sent) {
      toast(t("edit.uploaded", { count: sent }));
      onChanged(); // the page lists Drive again (A10)
    }
  };

  return (
    <>
      <div
        className={`drop${over ? " over" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          void upload([...event.dataTransfer.files]);
        }}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <path d="M12 16V4M7 9l5-5 5 5" />
          <path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" />
        </svg>
        <span>{t("edit.dropFiles")}</span>
        <input
          type="file"
          id={`up-${position}`}
          multiple
          onChange={(event) => {
            void upload([...(event.target.files ?? [])]);
            event.target.value = ""; // the same file can be chosen again
          }}
        />
        <label htmlFor={`up-${position}`}>{t("edit.chooseFiles")}</label>
        <small>{t("edit.dropNote", { folder, max: UPLOAD_MAX_MB })}</small>
      </div>
      {sending.length > 0 && (
        <ul className="uploads" aria-live="polite">
          {sending.map((item) => (
            <li key={item.id} className={item.failed ? "uploads__failed" : undefined}>
              <span className="uploads__name">{item.name}</span>
              {item.failed ? (
                <>
                  <span role="alert">{item.failed}</span>
                  <button
                    className="b b--ghost b--small"
                    type="button"
                    onClick={() => setSending((all) => all.filter((other) => other.id !== item.id))}
                  >
                    {t("edit.dismiss")}
                  </button>
                </>
              ) : (
                <progress
                  max={1}
                  value={item.progress}
                  aria-label={t("edit.sending", { name: item.name })}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** The "⋯" on each file in edit mode: for now, "Ocultar do cliente". */
export function FileMenu({ slug, file, onChanged }: { slug: string; file: FileItem; onChanged: () => void }) {
  const { t } = useTranslation();
  const message = useMessage();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const hide = async () => {
    setBusy(true);
    try {
      await call(api.POST("/api/pages/{slug}/files/{key}/hide", { params: { path: { slug, key: file.key } } }));
      setOpen(false);
      toast(t("edit.fileHidden", { name: file.name }));
      onChanged();
    } catch (failure) {
      toast(message(failure));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div
      className="filemenu menu"
      onBlur={(event) => !event.currentTarget.contains(event.relatedTarget) && setOpen(false)}
      onKeyDown={(event) => event.key === "Escape" && setOpen(false)}
    >
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={t("edit.fileActions", { name: file.name })}
        onClick={() => setOpen(!open)}
      >
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <circle cx="5" cy="12" r="1.8" />
          <circle cx="12" cy="12" r="1.8" />
          <circle cx="19" cy="12" r="1.8" />
        </svg>
      </button>
      {open && (
        <div className="menu__list" role="menu">
          <button type="button" role="menuitem" disabled={busy} onClick={() => void hide()}>
            {t("edit.hideFile")}
            <small>{t("edit.hideFileNote")}</small>
          </button>
        </div>
      )}
    </div>
  );
}
