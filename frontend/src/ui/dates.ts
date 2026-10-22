// Dates as people say them: "hoje", "ontem", "há 3 dias", "há 2 semanas"; past
// a month, the date itself (15/10/2026). Days are counted in the office's time
// zone, so "ontem" means the office's yesterday wherever the viewer is.

/** The calendar day of `date` in `timeZone`, as days since 1970. */
function dayNumber(date: Date, timeZone: string): number {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
  return Date.parse(`${parts}T00:00:00Z`) / 86_400_000;
}

export function relativeDay(value: string, now: Date, locale: string, timeZone: string): string {
  const date = new Date(value);
  const days = dayNumber(now, timeZone) - dayNumber(date, timeZone);
  const relative = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (days <= 0) return relative.format(0, "day"); // today (a clock slightly ahead too)
  if (days < 7) return relative.format(-days, "day");
  // Weeks by number: "semana passada" would read as the calendar week.
  if (days < 30) return new Intl.RelativeTimeFormat(locale).format(-Math.floor(days / 7), "week");
  return new Intl.DateTimeFormat(locale, { timeZone, day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}
