// The light or dark theme, one choice for the whole site on this device: the
// painel and the project pages read and save the same setting, so a choice made
// on one holds on the other. Light by default.
import { useEffect, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "theme";
export const THEME_CHANGED = "theme-changed";
const CHANGED = THEME_CHANGED;
let saving = true;

/** For the preview page: a change shows, but isn't kept as this device's choice. */
export function keepThemeUnsaved(): void {
  saving = false;
}

function stored(): Theme {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** At start, before the first paint: the theme chosen before. */
export function applyStoredTheme(): void {
  document.documentElement.dataset.theme = stored();
}

/** What the page shows now (set at start from storage, then by `useTheme`). */
function current(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : stored();
}

/** The theme and a way to change it. Every control showing it (the painel's
 *  button, the phone drawer's switch, the project page's switch) follows a change
 *  made by any of them. */
export function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(current);
  useEffect(() => {
    const follow = () => setTheme(current());
    window.addEventListener(CHANGED, follow);
    return () => window.removeEventListener(CHANGED, follow);
  }, []);
  const change = (next: Theme) => {
    document.documentElement.dataset.theme = next;
    try {
      if (saving) localStorage.setItem(KEY, next);
    } catch {
      // Private browsing: the choice lasts until the tab closes.
    }
    window.dispatchEvent(new Event(CHANGED));
  };
  return [theme, change];
}
