import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "./Button";

type Theme = "light" | "dark";
const KEY = "painel-theme";

function stored(): Theme {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyStoredTheme(): void {
  document.documentElement.dataset.theme = stored();
}

const CHANGED = "painel-theme-changed";

/** The painel's theme: light by default, remembered on this device only. Every
 *  control showing it (the top bar's button, the phone drawer's switch) follows
 *  a change made by any of them. */
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
      localStorage.setItem(KEY, next);
    } catch {
      // Private browsing: the choice lasts until the tab closes.
    }
    window.dispatchEvent(new Event(CHANGED));
  };
  return [theme, change];
}

/** What the page shows now (set at start from storage, then by `useTheme`). */
function current(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : stored();
}

export function ThemeToggle({ className }: { className?: string }) {
  const { t } = useTranslation();
  const [theme, setTheme] = useTheme();
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <Button
      variant="ghost"
      className={className}
      aria-label={t(next === "light" ? "theme.useLight" : "theme.useDark")}
      onPress={() => setTheme(next)}
    >
      <span aria-hidden="true">{next === "light" ? "☀" : "☾"}</span>
    </Button>
  );
}
