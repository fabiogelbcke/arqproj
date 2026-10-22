import type { HTMLAttributes } from "react";

import styles from "./ui.module.css";

/** A grey rounded panel for a section of a page (Primeiros passos, a settings
 *  tab), its fields and rows white on it (painel redesign, 22 Oct 2026). */
export function Panel({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <section {...props} className={[styles.surfacePanel, className].filter(Boolean).join(" ")} />;
}
