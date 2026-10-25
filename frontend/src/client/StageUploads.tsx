// Edit mode: the prototype's drop area under each stage's files, and each file's
// menu ("Enviar nova versão", "Ocultar do cliente"). Files go from the browser
// straight to Drive (A31): the app opens the upload, the browser sends the bytes to
// the address it gets. Versions come from the names (A25): a new version is saved
// as the next "vN", which the app names.
import { useRef, useState } from "react";
import { Dialog, Heading, Modal, ModalOverlay } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { ApiError, api, call, type Schemas } from "../api/client";
import { Button } from "../ui/Button";
import { errorMessage } from "../ui/ErrorNotice";
import { ImageCropDialog } from "../ui/ImageCropDialog";
import { MoreIcon } from "../ui/MoreIcon";
import { toast, toastError } from "../ui/Toast";
import styles from "../ui/ui.module.css";
import { useDismiss } from "../ui/useDismiss";
import { fileSource, type Page } from "./format";

type Staff = NonNullable<Page["staff"]>;
type FileItem = Schemas["FileOut"];
type Match = Schemas["MatchOut"];

export const UPLOAD_MAX_MB = 100; // the server checks it too
const UPLOAD_MAX = UPLOAD_MAX_MB * 1024 * 1024;

// Waits before trying again after a break: about half a minute in all.
const RETRY_WAITS = [1000, 2000, 4000, 8000, 16000];

/** One PUT, reporting how much of its body went (which fetch can't). Resolves
 *  with any answer; rejects only when the connection breaks. */
function put(
  url: string,
  body: Blob | null,
  headers: Record<string, string>,
  onSent?: (loaded: number) => void,
): Promise<XMLHttpRequest> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", url);
    for (const [name, value] of Object.entries(headers)) request.setRequestHeader(name, value);
    if (onSent) request.upload.onprogress = (event) => onSent(event.loaded);
    request.onload = () => resolve(request);
    request.onerror = () => reject(new ApiError("network"));
    request.send(body);
  });
}

class Refused extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(String(status));
  }
}

/** Sending failed for good. The app never sees these bytes, so the page reports
 *  it (`/uploads/failed`) to have it logged and get the support code. */
export class UploadBroke extends Error {
  constructor(
    readonly status: number, // Google's last answer; 0 when the connection kept breaking
    readonly detail: string,
  ) {
    super("upload_broke");
  }
}

/** Worth another try later: Google busy (5xx) or asking us to slow down (429). */
const passing = (status: number) => status >= 500 || status === 429;

const refused = (answer: XMLHttpRequest) => new Refused(answer.status, (answer.responseText ?? "").slice(0, 500));

/** How much of the file the upload session already has (Google's resumable
 *  protocol): all of it once it answered 200/201, else its "Range". */
async function received(url: string, size: number): Promise<number> {
  const answer = await put(url, null, { "Content-Range": `bytes */${size}` });
  if (answer.status < 300) return size;
  if (passing(answer.status)) throw new Error("busy"); // a break: ask again later
  if (answer.status !== 308) throw refused(answer); // the session is gone
  const range = /bytes=0-(\d+)/.exec(answer.getResponseHeader("Range") ?? "");
  return range ? Number(range[1]) + 1 : 0;
}

/** Sends the file to its upload session. After a break (a lost connection, a
 *  5xx, a 429) it asks the session how much arrived and sends the rest, so a large
 *  file need not start over (plan section 11). A refusal (4xx) is final. */
export async function sendFile(
  url: string,
  file: File,
  onProgress: (fraction: number) => void,
  waits: number[] = RETRY_WAITS,
): Promise<void> {
  let last = { status: 0, detail: "the connection kept breaking" };
  for (let attempt = 0; ; attempt += 1) {
    try {
      const from = attempt === 0 ? 0 : await received(url, file.size);
      if (attempt > 0 && from >= file.size) return;
      const headers: Record<string, string> =
        from === 0
          ? file.type
            ? { "Content-Type": file.type }
            : {}
          : { "Content-Range": `bytes ${from}-${file.size - 1}/${file.size}` };
      const answer = await put(url, from ? file.slice(from) : file, headers, (loaded) =>
        onProgress(file.size ? (from + loaded) / file.size : 1),
      );
      if (answer.status < 300) return;
      if (!passing(answer.status)) throw refused(answer);
      last = { status: answer.status, detail: (answer.responseText ?? "").slice(0, 500) };
    } catch (failure) {
      if (failure instanceof Refused) throw new UploadBroke(failure.status, failure.detail);
      // A break: try again below.
    }
    if (attempt >= waits.length) throw new UploadBroke(last.status, last.detail);
    await new Promise((resume) => setTimeout(resume, waits[attempt]));
  }
}

const message = (failure: unknown) => errorMessage(failure, { max: UPLOAD_MAX_MB });

/** Opens the upload and sends the file. `versionOf`: a file's key, to save this
 *  one as the next version of its document, in its folder. */
async function uploadFile(
  staff: Staff,
  position: number,
  file: File,
  onProgress: (fraction: number) => void,
  versionOf?: string,
): Promise<void> {
  if (file.size > UPLOAD_MAX) throw new ApiError("file_too_large");
  const path = { project_id: staff.project_id, position };
  const opened = await call(
    api.POST("/api/projects/{project_id}/stages/{position}/uploads", {
      params: { path },
      body: {
        row_version: staff.row_version,
        name: file.name,
        size: file.size,
        mime_type: file.type,
        ...(versionOf ? { version_of: versionOf } : {}),
      },
    }),
  );
  await sendFile(opened.upload_url, file, onProgress).catch((broke) =>
    broke instanceof UploadBroke
      ? call(
          api.POST("/api/projects/{project_id}/stages/{position}/uploads/failed", {
            params: { path },
            body: { name: file.name, size: file.size, status: broke.status, detail: broke.detail },
          }),
        ) // always an error: "upload_failed", with the support code
      : Promise.reject(broke),
  );
}

type Answer = "version" | "separate" | "cancel";

/** The prototype's "É uma nova versão?": the current file stays and becomes an
 *  older version, the new one is saved as the next. Closing it skips the file. */
function VersionQuestion({ match, onAnswer }: { match: Match; onAnswer: (answer: Answer) => void }) {
  const { t } = useTranslation();
  return (
    <ModalOverlay className={styles.confirmOverlay} isDismissable isOpen onOpenChange={(open) => !open && onAnswer("cancel")}>
      <Modal className={styles.confirmModal}>
        <Dialog role="alertdialog" className={styles.confirmDialog}>
          <Heading slot="title" className={styles.confirmTitle}>
            {t("edit.versionTitle")}
          </Heading>
          <p className={styles.confirmText}>{t("edit.versionExists", { name: match.document })}</p>
          <div className="vflow">
            <div>
              <span>{t("edit.versionCurrent")}</span>
              <div>
                <p>{match.current}</p>
                <p>{t("edit.versionCurrentNote", { version: match.current_version })}</p>
              </div>
            </div>
            <div className="new">
              <span>{t("edit.versionNew")}</span>
              <div>
                <p>
                  <b>{match.saved_as}</b>
                </p>
                <p>{t("edit.versionNewNote")}</p>
              </div>
            </div>
          </div>
          <div className={styles.confirmActions}>
            <Button onPress={() => onAnswer("separate")}>{t("edit.versionNo")}</Button>
            <Button variant="primary" onPress={() => onAnswer("version")} autoFocus>
              {t("edit.versionYes", { version: match.next_version })}
            </Button>
          </div>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
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
  const [over, setOver] = useState(false);
  const chooser = useRef<HTMLInputElement>(null);
  const touch = window.matchMedia?.("(pointer: coarse)").matches ?? false;
  const [sending, setSending] = useState<Sending[]>([]);
  const next = useRef(0);
  const update = (id: number, change: Partial<Sending>) =>
    setSending((all) => all.map((item) => (item.id === id ? { ...item, ...change } : item)));
  const [asking, setAsking] = useState<{ match: Match; answer: (answer: Answer) => void } | null>(null);

  const sendOne = async (file: File, versionOf?: string) => {
    const id = (next.current += 1);
    setSending((all) => [...all, { id, name: file.name, progress: 0 }]);
    try {
      await uploadFile(staff, position, file, (progress) => update(id, { progress }), versionOf);
      setSending((all) => all.filter((item) => item.id !== id));
      return true;
    } catch (failure) {
      update(id, { failed: message(failure) });
      return false;
    }
  };

  /** Each file named like a document already in the stage: a new version of it?
   *  One question at a time; the files then go up together. One too large asks
   *  nothing: it fails on its own when sent. */
  const choose = async (files: File[]) => {
    const names = files.filter((file) => file.size <= UPLOAD_MAX).map((file) => file.name);
    const found = names.length
      ? await call(
          api.POST("/api/projects/{project_id}/stages/{position}/uploads/check", {
            params: { path: { project_id: staff.project_id, position } },
            body: { row_version: staff.row_version, names },
          }),
        )
      : { matches: [] };
    const chosen: { file: File; versionOf?: string }[] = [];
    for (const file of files) {
      const match = file.size <= UPLOAD_MAX && found.matches.find((candidate) => candidate.name === file.name);
      if (!match) {
        chosen.push({ file });
        continue;
      }
      const answer = await new Promise<Answer>((resolve) => setAsking({ match, answer: resolve }));
      setAsking(null);
      if (answer === "version") chosen.push({ file, versionOf: match.key });
      else if (answer === "separate") chosen.push({ file }); // saved apart: "Planta (2).pdf"
    }
    return chosen;
  };

  const upload = async (files: File[]) => {
    if (!files.length) return;
    let chosen;
    try {
      chosen = await choose(files);
    } catch (failure) {
      toastError(failure, { max: UPLOAD_MAX_MB });
      return;
    }
    const sent = (await Promise.all(chosen.map(({ file, versionOf }) => sendOne(file, versionOf)))).filter(Boolean)
      .length;
    if (sent) {
      toast(t("edit.uploaded", { count: sent }));
      onChanged(); // the page lists Drive again (A10)
    }
  };

  return (
    <>
      <div
        className={`drop${over ? " over" : ""}`}
        data-tour="upload"
        // A click anywhere in the area chooses files, not only on its link (whose
        // label opens the chooser itself).
        onClick={(event) => {
          if (!(event.target as Element).closest("label, input")) chooser.current?.click();
        }}
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
        {/* A touch screen has nothing to drag: the whole area opens the picker. */}
        {!touch && <span>{t("edit.dropFiles")}</span>}
        <input
          ref={chooser}
          type="file"
          id={`up-${position}`}
          multiple
          onChange={(event) => {
            void upload([...(event.target.files ?? [])]);
            event.target.value = ""; // the same file can be chosen again
          }}
        />
        <label htmlFor={`up-${position}`}>{touch ? t("edit.tapToChoose") : t("edit.chooseFiles")}</label>
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
      {asking && <VersionQuestion match={asking.match} onAnswer={asking.answer} />}
    </>
  );
}

/** The "⋯" on each file in edit mode: set as cover (images), move to another
 *  stage, hide from the client. Changes are made here, not in Drive (A34). */
export function FileMenu({
  slug,
  file,
  page,
  position,
  onChanged,
}: {
  slug: string;
  file: FileItem;
  page: Page;
  position: number; // the stage it is in, from 1
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<false | "menu" | "move">(false);
  const menu = useRef<HTMLDivElement>(null);
  useDismiss(menu, open !== false, () => setOpen(false));
  const [busy, setBusy] = useState(false);
  const path = { slug, key: file.key };
  // "Enviar nova versão": the chosen file goes up as the next version (A25).
  const versionChooser = useRef<HTMLInputElement>(null);
  const [sendingVersion, setSendingVersion] = useState<number | null>(null); // its progress
  const sendVersion = async (chosen: File) => {
    setBusy(true);
    setSendingVersion(0);
    try {
      await uploadFile(page.staff!, position, chosen, setSendingVersion, file.key);
      toast(t("edit.newVersionSent", { name: file.name }));
      onChanged(); // the page lists Drive again (A10)
    } catch (failure) {
      toastError(failure, { max: UPLOAD_MAX_MB });
    } finally {
      setBusy(false);
      setSendingVersion(null);
    }
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
  const hide = () =>
    act(
      () => call(api.POST("/api/pages/{slug}/files/{key}/hide", { params: { path } })),
      t("edit.fileHidden", { name: file.name }),
    );
  // "Definir como capa": the image, cropped to the cover's shape here, goes up as the
  // cover (a copy: the file stays where it is).
  const [cropping, setCropping] = useState(false);
  const cover = (cropped: File) =>
    act(
      () =>
        call(
          api.PUT("/api/projects/{project_id}/cover", {
            params: { path: { project_id: page.staff!.project_id } },
            // OpenAPI describes an uploaded file as a binary string; it is the File.
            body: { file: cropped as unknown as string },
            bodySerializer: (body) => {
              const form = new FormData();
              form.append("file", body.file as unknown as Blob, cropped.name);
              return form;
            },
          }),
        ),
      t("edit.coverSet", { name: file.name }),
    );
  const move = (to: number) =>
    act(
      () =>
        call(
          api.POST("/api/pages/{slug}/files/{key}/move", {
            params: { path },
            body: { position: to, row_version: page.staff!.row_version },
          }),
        ),
      t("edit.fileMoved", { name: file.name, stage: page.stages[to - 1]!.title }),
    );
  return (
    <div
      ref={menu}
      className={`filemenu menu${open ? " is-open" : ""}`}
      onBlur={(event) => !event.currentTarget.contains(event.relatedTarget) && setOpen(false)}
    >
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open !== false}
        aria-label={t("edit.fileActions", { name: file.name })}
        onClick={() => setOpen(open ? false : "menu")}
      >
        <MoreIcon />
      </button>
      <input
        ref={versionChooser}
        type="file"
        hidden
        // The same type as the document, or it wouldn't be a version of it.
        accept={file.name.includes(".") ? `.${file.name.split(".").pop()}` : undefined}
        aria-label={t("edit.newVersion")}
        onChange={(event) => {
          const chosen = event.target.files?.[0];
          event.target.value = ""; // the same file can be chosen again
          if (chosen) void sendVersion(chosen);
        }}
      />
      {sendingVersion !== null && (
        <progress
          className="filemenu__progress"
          max={1}
          value={sendingVersion}
          aria-label={t("edit.sending", { name: file.name })}
        />
      )}
      {open === "menu" && (
        <div className="menu__list" role="menu">
          <button
            type="button"
            role="menuitem"
            disabled={busy}
            onClick={() => {
              setOpen(false);
              versionChooser.current?.click();
            }}
          >
            {t("edit.newVersion")}
            <small>{t("edit.newVersionNote")}</small>
          </button>
          {file.kind === "image" && (
            <button
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={() => {
                setOpen(false);
                setCropping(true);
              }}
            >
              {t("edit.setCover")}
            </button>
          )}
          {page.stages.length > 1 && (
            <button type="button" role="menuitem" disabled={busy} onClick={() => setOpen("move")}>
              {t("edit.moveFile")}
            </button>
          )}
          <hr />
          <button type="button" role="menuitem" disabled={busy} onClick={() => void hide()}>
            {t("edit.hideFile")}
            <small>{t("edit.hideFileNote")}</small>
          </button>
        </div>
      )}
      {open === "move" && (
        <div className="menu__list" role="menu" aria-label={t("edit.moveFileTo", { name: file.name })}>
          {page.stages.map((stage, i) =>
            i + 1 === position ? null : (
              <button key={i} type="button" role="menuitem" disabled={busy} onClick={() => void move(i + 1)}>
                {`${String(i + 1).padStart(2, "0")} ${stage.title}`}
              </button>
            ),
          )}
          <hr />
          <button type="button" role="menuitem" disabled={busy} onClick={() => setOpen("menu")}>
            {t("edit.menuBack")}
          </button>
        </div>
      )}
      {cropping && (
        <ImageCropDialog
          source={fileSource.address(slug, file.key, "inline")!}
          kind="cover"
          name="capa.jpg"
          onCancel={() => setCropping(false)}
          onCropped={(cropped) => {
            setCropping(false);
            void cover(cropped);
          }}
        />
      )}
    </div>
  );
}
