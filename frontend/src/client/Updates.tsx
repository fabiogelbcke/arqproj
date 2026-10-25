// The client page's "Atualizações" (A28, after the prototype): the latest changes,
// worded from what the page shows now. Which ones were read stays in this browser.
import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Schemas } from "../api/client";
import { useDismiss } from "../ui/useDismiss";
import { day, meetingWhen, type Page } from "./format";

type Update = Schemas["UpdateOut"];
type Entry = { id: string; date: string; title: string; context: string; target: number | "meeting" | null };

const pad = (n: number) => String(n).padStart(2, "0");
const storageKey = (slug: string) => `updates-read:${slug}`;

function readIds(slug: string): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(storageKey(slug)) ?? "[]") as string[]);
  } catch {
    return new Set(); // private mode, or storage off: everything stays unread
  }
}

/** The entries, newest first: a file as it is now, a stage's latest note, the
 *  stages still completed, the meeting as it is now. */
export function entriesFor(
  page: Page,
  updates: Update[],
  t: (key: string, values?: Record<string, unknown>) => string,
  locale: string,
) {
  const entries: Entry[] = [];
  const notes = new Set<number>();
  const finished = new Set<number>();
  let completed = false;
  let meeting = false;
  for (const update of updates) {
    const index = (update.stage_position ?? 0) - 1;
    const stage = page.stages[index];
    const base = { id: update.id, date: day(update.occurred_at, locale, page.timezone) };
    if (update.kind === "file_published") {
      if (stage && update.name)
        entries.push({
          ...base,
          // A version (A25) says which: the card shows the document's clean name.
          title:
            update.version != null ? t("updates.fileVersion", { name: update.name, version: update.version }) : update.name,
          context: `${pad(index + 1)} ${stage.title}`,
          target: index,
        });
    } else if (update.kind === "note_changed") {
      if (!stage || notes.has(index)) continue;
      notes.add(index);
      if (stage.notes) entries.push({ ...base, title: t("updates.note"), context: stage.notes, target: index });
    } else if (update.kind === "stage_completed") {
      if (!stage?.completed || finished.has(index)) continue; // reopened since
      finished.add(index);
      entries.push({ ...base, title: t("updates.stageCompleted"), context: `${pad(index + 1)} ${stage.title}`, target: index });
    } else if (update.kind === "stage_reopened") {
      if (!stage || stage.completed || finished.has(index)) continue; // completed again since
      finished.add(index);
      entries.push({ ...base, title: t("updates.stageReopened"), context: `${pad(index + 1)} ${stage.title}`, target: index });
    } else if (update.kind === "stage_advanced") {
      continue; // the old progress (before stages completed on their own): nothing holds it now
    } else if (update.kind === "project_completed") {
      if (completed || !page.completed) continue;
      completed = true;
      entries.push({ ...base, title: t("updates.completed"), context: page.name, target: null });
    } else {
      if (meeting) continue;
      meeting = true;
      const next = page.next_meeting;
      if (next) {
        const when = meetingWhen(next, locale, page.timezone);
        const title = update.kind === "meeting_scheduled" ? t("updates.meetingScheduled") : t("updates.meetingChanged");
        entries.push({ ...base, title, context: `${next.title} · ${when.day} · ${when.time}`, target: "meeting" });
      } else if (update.kind === "meeting_cleared" && update.name) {
        entries.push({ ...base, title: t("updates.meetingCancelled"), context: update.name, target: null });
      }
    }
  }
  return entries;
}

export function UpdatesBell({
  page,
  slug,
  updates,
  onStage,
}: {
  page: Page;
  slug: string;
  updates: Update[];
  onStage: (index: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const entries = useMemo(() => entriesFor(page, updates, t, i18n.language), [page, updates, t, i18n.language]);
  const [read, setRead] = useState(() => readIds(slug));
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDetailsElement>(null);
  useDismiss(panel, open, () => setOpen(false));
  const unread = entries.filter((entry) => !read.has(entry.id)).length;
  const markRead = () => {
    const all = new Set([...read, ...entries.map((entry) => entry.id)]);
    setRead(all);
    try {
      localStorage.setItem(storageKey(slug), JSON.stringify([...all]));
    } catch {
      // Not remembered on this device; nothing else to do.
    }
  };
  const go = (target: number | "meeting") => {
    setOpen(false);
    if (target === "meeting") {
      document.querySelector(".meeting")?.scrollIntoView({ block: "center" });
      return;
    }
    onStage(target);
  };
  return (
    <details ref={panel} className="client-notifications" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary
        className="b b--small"
        aria-label={unread ? t("updates.unread", { count: unread }) : t("updates.noneUnread")}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
        </svg>
        <span className="notification-label">{t("updates.label")}</span>
        {unread > 0 && <span className="notification-count">{unread}</span>}
      </summary>
      <section className="notification-panel" aria-label={t("updates.title")}>
        <div className="notification-head">
          <h2>{t("updates.title")}</h2>
          <button className="iconbtn" type="button" aria-label={t("updates.close")} onClick={() => setOpen(false)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        {entries.length ? (
          <>
            <button className="notification-read" type="button" onClick={markRead} disabled={!unread}>
              {unread ? t("updates.markRead") : t("updates.allRead")}
            </button>
            <ul>
              {entries.map((entry) => (
                <li key={entry.id} className={read.has(entry.id) ? undefined : "is-unread"}>
                  <small>{entry.date}</small>
                  <strong>{entry.title}</strong>
                  <p>{entry.context}</p>
                  {entry.target !== null && (
                    <button type="button" onClick={() => go(entry.target!)}>
                      {entry.target === "meeting" ? t("updates.seeMeeting") : t("updates.seeStage")} →
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="notification-empty">{t("updates.empty")}</p>
        )}
      </section>
    </details>
  );
}
