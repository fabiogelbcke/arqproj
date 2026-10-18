import { useState } from "react";
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

/** Light by default; the choice is remembered on this device only. */
export function ThemeToggle() {
  const { t } = useTranslation();
  const [theme, setTheme] = useState<Theme>(stored);
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <Button
      variant="ghost"
      aria-label={t(next === "light" ? "theme.useLight" : "theme.useDark")}
      onPress={() => {
        document.documentElement.dataset.theme = next;
        try {
          localStorage.setItem(KEY, next);
        } catch {
          // Private browsing: the choice lasts until the tab closes.
        }
        setTheme(next);
      }}
    >
      <span aria-hidden="true">{next === "light" ? "☀" : "☾"}</span>
    </Button>
  );
}
