import { Button as AriaButton, type ButtonProps } from "react-aria-components";

import styles from "./ui.module.css";

/** A round icon-only button (ui/sizes.css: icon). Its name is for screen
 *  readers, as the icon shows nothing to them. */
export function IconButton({ label, className, ...props }: ButtonProps & { label: string }) {
  return <AriaButton {...props} aria-label={label} className={[styles.iconButton, className].filter(Boolean).join(" ")} />;
}
