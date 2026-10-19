import { useTranslation } from "react-i18next";

import { Button } from "./Button";
import { useTheme, type Theme } from "./theme";

export { applyStoredTheme, useTheme } from "./theme";

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
