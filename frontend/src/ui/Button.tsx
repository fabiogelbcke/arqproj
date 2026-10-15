import { Button as AriaButton, type ButtonProps } from "react-aria-components";

import styles from "./ui.module.css";

type Variant = "primary" | "secondary" | "ghost";

export function Button({ variant = "secondary", className, ...props }: ButtonProps & { variant?: Variant }) {
  return <AriaButton {...props} className={[styles.button, styles[variant], className].filter(Boolean).join(" ")} />;
}
