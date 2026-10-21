// The preview page's controls (plan section 18, "Visual variants"), in one place:
// each control's values, its starting value and its label. The settings live in
// the address (only those changed from the start), so a link reproduces a view.
// To add a control: one entry here, its label in the catalogs, its use in variant.ts.

export const CONTROLS = {
  view: { kind: "choice", options: ["client", "staff"], initial: "client" },
  theme: { kind: "choice", options: ["light", "dark"], initial: "light" },
  width: { kind: "choice", options: ["desktop", "phone"], initial: "desktop" },
  cover: { kind: "toggle", initial: true },
  description: { kind: "choice", options: ["none", "short", "long"], initial: "long" },
  length: { kind: "range", min: 200, max: 4000, step: 100, initial: 600 }, // a long description's
  meeting: { kind: "choice", options: ["none", "short", "long"], initial: "short" },
  stages: { kind: "range", min: 1, max: 12, step: 1, initial: 7 },
  files: { kind: "range", min: 0, max: 20, step: 1, initial: 3 }, // per stage, up to the current one
  longNames: { kind: "toggle", initial: false }, // of stages and files
  emails: { kind: "toggle", initial: true }, // the client's addresses for updates
} as const;

type Controls = typeof CONTROLS;
export type Key = keyof Controls;
export type Settings = {
  [K in Key]: Controls[K] extends { options: readonly (infer O)[] }
    ? O
    : Controls[K] extends { kind: "toggle" }
      ? boolean
      : number;
};

export const KEYS = Object.keys(CONTROLS) as Key[];

/** The settings an address names; anything missing or unknown keeps its start. */
export function readSettings(query: string): Settings {
  const given = new URLSearchParams(query);
  const settings = Object.fromEntries(KEYS.map((key) => [key, CONTROLS[key].initial])) as Settings;
  for (const key of KEYS) {
    const value = given.get(key);
    if (value === null) continue;
    const control = CONTROLS[key];
    if (control.kind === "toggle") (settings as Record<Key, unknown>)[key] = value === "1";
    else if (control.kind === "choice") {
      if ((control.options as readonly string[]).includes(value)) (settings as Record<Key, unknown>)[key] = value;
    } else {
      const number = Number(value);
      if (Number.isFinite(number))
        (settings as Record<Key, unknown>)[key] = Math.min(control.max, Math.max(control.min, Math.round(number)));
    }
  }
  return settings;
}

/** The address's query for these settings: only what differs from the start. */
export function writeSettings(settings: Settings): string {
  const query = new URLSearchParams();
  for (const key of KEYS) {
    const value = settings[key];
    if (value === CONTROLS[key].initial) continue;
    query.set(key, typeof value === "boolean" ? (value ? "1" : "0") : String(value));
  }
  return query.toString();
}
