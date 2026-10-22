import { Button as AriaButton, type ButtonProps } from "react-aria-components";

import styles from "./ui.module.css";

type Variant = "primary" | "secondary" | "ghost";

/** The site's text button. Size by role (ui/sizes.css): "regular" for the action
 *  a screen or dialog is about and in forms; "small" in toolbars and beside
 *  content. Pill-shaped (painel redesign). Icon-only buttons are IconButton. */
export function Button({
  variant = "secondary",
  size = "regular",
  className,
  ...props
}: ButtonProps & { variant?: Variant; size?: "regular" | "small" }) {
  return (
    <AriaButton
      {...props}
      className={[styles.button, styles[variant], size === "small" && styles.small, className].filter(Boolean).join(" ")}
    />
  );
}
