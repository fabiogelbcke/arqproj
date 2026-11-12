// Comments on a stage or a file (A49): the conversation, oldest first, and a box
// to add to it. A client signs with a name typed once and remembered on this
// device; staff comment as their account. Staff may remove any comment.
import { createContext, useContext, useEffect, useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api, call, type Schemas } from "../api/client";
import { LIMITS } from "../api/limits";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { toastError } from "../ui/Toast";
import { day } from "./format";

type Comment = Schemas["CommentOut"];

const NAME_KEY = "comment-name";

/** Each conversation as it is now, by its place ("stage:2", "file:<key>"): what
 *  was posted or removed here since the page listed its files, which it doesn't do
 *  again for a comment (that reads the office's Drive). A conversation closed and
 *  opened again, and a card's count, show it; a new listing starts over. */
type Lists = { lists: Record<string, Comment[]>; change: (id: string, base: Comment[], to: (list: Comment[]) => Comment[]) => void };
const CommentLists = createContext<Lists | null>(null);

export function CommentListsProvider({ listing, children }: { listing: unknown; children: ReactNode }) {
  const [lists, setLists] = useState<Record<string, Comment[]>>({});
  useEffect(() => setLists({}), [listing]);
  const change: Lists["change"] = (id, base, to) => setLists((all) => ({ ...all, [id]: to(all[id] ?? base) }));
  return <CommentLists.Provider value={{ lists, change }}>{children}</CommentLists.Provider>;
}

/** A conversation as it is now: as listed, unless changed here since. */
export function useCommentList(id: string, listed: Comment[]): [Comment[], (to: (list: Comment[]) => Comment[]) => void] {
  const store = useContext(CommentLists);
  const [own, setOwn] = useState(listed); // without a page around it (its tests)
  useEffect(() => setOwn(listed), [listed]);
  if (!store) return [own, (to) => setOwn(to)];
  return [store.lists[id] ?? listed, (to) => store.change(id, listed, to)];
}

export const stageThread = (position: number) => `stage:${position}`;
export const fileThread = (key: string) => `file:${key}`;

/** The name this device signed its last comment with, if any. */
function rememberedName(): string {
  try {
    return localStorage.getItem(NAME_KEY) ?? "";
  } catch {
    return ""; // storage blocked: asked every time
  }
}

function remember(name: string) {
  try {
    localStorage.setItem(NAME_KEY, name);
  } catch {
    // storage blocked: asked again next time
  }
}

export function CommentThread({
  slug,
  comments,
  where,
  staff,
  timeZone,
  label,
}: {
  slug: string;
  comments: Comment[];
  where: { key: string } | { position: number }; // a file (its key) or a stage (from 1)
  staff: boolean; // signed in as the office's staff: signs as them, may remove any
  timeZone: string;
  label: string; // what it is about, for screen readers: "Comentários sobre Planta.pdf"
}) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const [list, setList] = useCommentList("key" in where ? fileThread(where.key) : stageThread(where.position), comments);
  const [body, setBody] = useState("");
  const [name, setName] = useState(rememberedName);
  const [naming, setNaming] = useState(() => !rememberedName());
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState<Comment | null>(null);
  const ready = body.trim() !== "" && (staff || name.trim() !== "");

  const send = async () => {
    if (!ready || busy) return;
    setBusy(true);
    const sent = body;
    try {
      const posted = await call(
        api.POST("/api/pages/{slug}/comments", {
          params: { path: { slug } },
          body: { body: sent, ...where, ...(staff ? {} : { name: name.trim() }) },
        }),
      );
      setList((all) => [...all, posted]);
      // Emptied for the next one, unless a next one was begun while this went.
      setBody((now) => (now === sent ? "" : now));
      if (!staff) {
        remember(name.trim());
        setNaming(false);
      }
    } catch (failure) {
      toastError(failure);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (comment: Comment) => {
    setBusy(true);
    try {
      await call(
        api.DELETE("/api/pages/{slug}/comments/{comment_id}", {
          params: { path: { slug, comment_id: comment.id } },
        }),
      );
      setList((all) => all.filter((other) => other.id !== comment.id));
      setRemoving(null);
    } catch (failure) {
      toastError(failure);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="comments" aria-label={label}>
      {list.length > 0 ? (
        <ol className="comments__list">
          {list.map((comment) => (
            <li key={comment.id} className={`comment comment--${comment.author}`}>
              <p className="comment__who">
                <strong>{comment.name}</strong>
                {comment.author === "staff" && <span className="comment__staff">{t("comments.staffTag")}</span>}
                <time dateTime={comment.created_at}>{day(comment.created_at, i18n.language, timeZone)}</time>
                {staff && (
                  <button
                    type="button"
                    className="comment__remove"
                    aria-label={t("comments.removeOf", { name: comment.name })}
                    onClick={() => setRemoving(comment)}
                  >
                    {t("comments.remove")}
                  </button>
                )}
              </p>
              <p className="comment__body">{comment.body}</p>
            </li>
          ))}
        </ol>
      ) : (
        <p className="comments__empty">{t("comments.empty")}</p>
      )}
      <form
        className="comments__new"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <label className="sr" htmlFor={`${id}-body`}>
          {t("comments.write")}
        </label>
        <textarea
          className="textarea"
          id={`${id}-body`}
          rows={2}
          maxLength={LIMITS.commentBody}
          placeholder={t("comments.placeholder")}
          value={body}
          onChange={(event) => setBody(event.target.value)}
          onKeyDown={(event) => {
            // Ctrl/⌘ + Enter sends; Enter alone makes a new line.
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <div className="comments__send">
          {staff ? (
            <span className="comments__as">{t("comments.asStaff")}</span>
          ) : naming ? (
            <span className="comments__name">
              <label htmlFor={`${id}-name`}>{t("comments.yourName")}</label>
              <input
                className="input"
                id={`${id}-name`}
                maxLength={LIMITS.commentName}
                autoComplete="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </span>
          ) : (
            <span className="comments__as">
              {t("comments.as", { name })}{" "}
              <button type="button" className="linklike" onClick={() => setNaming(true)}>
                {t("comments.changeName")}
              </button>
            </span>
          )}
          <button className="b b--primary b--small" type="submit" disabled={!ready || busy}>
            {t("comments.send")}
          </button>
        </div>
      </form>
      {removing && (
        <ConfirmDialog
          title={t("comments.removeTitle")}
          text={t("comments.removeText", { name: removing.name })}
          confirm={t("comments.remove")}
          danger
          busy={busy}
          onConfirm={() => void remove(removing)}
          onCancel={() => setRemoving(null)}
        />
      )}
    </section>
  );
}

/** A stage's conversation, folded under "Comentários" until opened. */
export function StageComments({
  slug,
  comments,
  position,
  title,
  staff,
  timeZone,
}: {
  slug: string;
  comments: Comment[];
  position: number;
  title: string;
  staff: boolean;
  timeZone: string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [now] = useCommentList(stageThread(position), comments);
  const count = now.length;
  const panel = useId();
  return (
    <div className="stage-comments">
      <button
        type="button"
        className="ghostline stage-comments__toggle"
        aria-expanded={open}
        aria-controls={panel}
        onClick={() => setOpen(!open)}
      >
        <CommentIcon />
        {count ? t("comments.count", { count }) : t("comments.add")}
      </button>
      <div id={panel} hidden={!open}>
        {open && (
          <CommentThread
            slug={slug}
            comments={comments}
            where={{ position }}
            staff={staff}
            timeZone={timeZone}
            label={t("comments.about", { name: title })}
          />
        )}
      </div>
    </div>
  );
}

export function CommentIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M4 5.5h16v10H9l-5 4v-14Z" strokeLinejoin="round" />
    </svg>
  );
}
