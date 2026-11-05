import { Link, type LinkProps } from "react-aria-components";

import type { Variant } from "./Button";
import styles from "./ui.module.css";

/** A link dressed as a Button, for going somewhere (another page, a new tab)
 *  where a button-sized action is expected: "Ver portfólio" at the top of the
 *  Portfólio tab. Same variants and sizes as Button. */
export function LinkButton({
  variant = "secondary",
  size = "regular",
  className,
  ...props
}: LinkProps & { variant?: Variant; size?: "regular" | "small" }) {
  return (
    <Link
      {...props}
      className={[styles.button, styles[variant], size === "small" && styles.small, className].filter(Boolean).join(" ")}
    />
  );
}
