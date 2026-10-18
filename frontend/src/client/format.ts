// Formatting for the client page: dates in the office's time zone, areas in m²,
// and the "add to calendar" link.
import type { Schemas } from "../api/client";

export type Page = Schemas["PageOut"];
export type Meeting = Schemas["MeetingOut"];
export type Detail = Schemas["DetailOut"];

/** 15/10/2026, in the office's time zone. */
export function day(value: string, locale: string, timeZone: string): string {
  return new Intl.DateTimeFormat(locale, { timeZone, day: "2-digit", month: "2-digit", year: "numeric" }).format(
    new Date(value),
  );
}

/** A calendar date as stored ("2026-03-02"), shown without any time-zone shift. */
function calendarDay(value: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { timeZone: "UTC", day: "2-digit", month: "2-digit", year: "numeric" }).format(
    new Date(`${value}T12:00:00Z`),
  );
}

/** Text as typed (in capitals, as the design shows facts), 1.240 m², or a date. */
export function detailValue(detail: Detail, locale: string): string {
  if (detail.type === "area") return `${Number(detail.value).toLocaleString(locale)} m²`;
  if (detail.type === "date") return calendarDay(String(detail.value), locale);
  return String(detail.value).toLocaleUpperCase(locale);
}

/** "terça-feira 21/10/2026" and "16:00 – 17:00", in the office's time zone. */
export function meetingWhen(meeting: Meeting, locale: string, timeZone: string) {
  const start = new Date(meeting.starts_at);
  const weekday = new Intl.DateTimeFormat(locale, { timeZone, weekday: "long" }).format(start);
  const time = new Intl.DateTimeFormat(locale, { timeZone, hour: "2-digit", minute: "2-digit" });
  return {
    day: `${weekday} ${day(meeting.starts_at, locale, timeZone)}`,
    time: `${time.format(start)} – ${time.format(new Date(meeting.ends_at))}`,
  };
}

const utc = (value: string) => new Date(value).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");

/** Google Calendar's "new event" page, filled in. */
export function googleCalendarLink(meeting: Meeting, projectName: string, pageUrl: string): string {
  const query = new URLSearchParams({
    action: "TEMPLATE",
    text: `${meeting.title} · ${projectName}`,
    dates: `${utc(meeting.starts_at)}/${utc(meeting.ends_at)}`,
    details: pageUrl,
  });
  if (meeting.location) query.set("location", meeting.location);
  return `https://calendar.google.com/calendar/render?${query}`;
}

/** Description: plain paragraphs, and "- " lines as a list (as the painel writes it). */
export function paragraphs(text: string): Array<{ kind: "p"; text: string } | { kind: "ul"; items: string[] }> {
  const out: Array<{ kind: "p"; text: string } | { kind: "ul"; items: string[] }> = [];
  for (const line of text.split("\n").map((l) => l.trim()).filter(Boolean)) {
    if (line.startsWith("- ")) {
      const last = out[out.length - 1];
      if (last?.kind === "ul") last.items.push(line.slice(2));
      else out.push({ kind: "ul", items: [line.slice(2)] });
    } else {
      out.push({ kind: "p", text: line });
    }
  }
  return out;
}

/** Where the page reads its files: through the API, from the office's Drive. The
 *  example project (example/) points these at files bundled with the page. */
export const fileSource = {
  /** A file to download ("file"), to show ("inline"), or its preview image
   *  ("thumb"; null: it has none). */
  address(slug: string, key: string, as: "file" | "inline" | "thumb"): string | null {
    const url = `/api/pages/${slug}/files/${encodeURIComponent(key)}`;
    return as === "thumb" ? `${url}/thumb` : as === "inline" ? `${url}?inline=true` : url;
  },
  /** The meeting as a calendar file (null: none). */
  calendar: (slug: string): string | null => `/api/pages/${slug}/meeting.ics`,
  /** Files in the page's bundle download by the link's own name (the API's
   *  answer says "attachment" itself). */
  bundled: false,
};
