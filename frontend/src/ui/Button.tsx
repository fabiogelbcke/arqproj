import { Button as AriaButton, type ButtonProps } from "react-aria-components";

import { PendingContent } from "./PendingContent";
import styles from "./ui.module.css";

export type Variant = "primary" | "secondary" | "ghost" | "danger";

/** The site's text button: "primary" for the action a screen or dialog is about,
 *  "danger" for one that destroys or removes something. Size by role (ui/sizes.css): "regular" for the action
 *  a screen or dialog is about and in forms; "small" in toolbars and beside
 *  content. Pill-shaped (painel redesign). Icon-only buttons are IconButton.
 *  `pending` while its action runs: a spinner in place of the label, presses
 *  ignored, still focusable, and the wait announced (react-aria's isPending).
 *  The button that started an action shows `pending`; its neighbours (Cancelar)
 *  are `isDisabled`. */
export function Button({
  variant = "secondary",
  size = "regular",
  pending,
  className,
  children,
  ...props
}: ButtonProps & { variant?: Variant; size?: "regular" | "small"; pending?: boolean }) {
  const button = (
    <AriaButton
      {...props}
      isPending={pending}
      className={[styles.button, styles[variant], size === "small" && styles.small, className].filter(Boolean).join(" ")}
    >
      {pending === undefined || typeof children === "function" ? (
        children
      ) : (
        <PendingContent pending={pending}>{children}</PendingContent>
      )}
    </AriaButton>
  );
  // Pending, react-aria makes a submit button a plain one; a form with one
  // field and no submit button is then sent by Enter (implicit submission).
  // A disabled submit button stands in, so Enter does nothing until it answers.
  // Same tree either way, so the button keeps focus as it starts and stops.
  return (
    <>
      {pending && props.type === "submit" && <button type="submit" disabled hidden aria-hidden="true" />}
      {button}
    </>
  );
}
