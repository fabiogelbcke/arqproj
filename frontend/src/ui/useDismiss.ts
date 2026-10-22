import { useEffect, useRef, type RefObject } from "react";

/** Closes a menu or panel we draw ourselves when the person clicks or taps
 *  outside it, or presses Esc: what react-aria's Popover and dismissable
 *  ModalOverlay already do for theirs. `refs` hold the menu and its button, so
 *  the button's own click still toggles it; when they aren't in one element,
 *  pass both, the button first. Esc from inside also gives the focus back to
 *  the menu's button, so a keyboard user goes on from where they opened it. */
export function useDismiss(
  refs: RefObject<HTMLElement | null> | RefObject<HTMLElement | null>[],
  open: boolean,
  onDismiss: () => void,
) {
  // The latest callback, so a new arrow function each render doesn't re-listen.
  const dismiss = useRef(onDismiss);
  dismiss.current = onDismiss;
  const inside = useRef(refs);
  inside.current = refs;
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node | null;
      const parts = Array.isArray(inside.current) ? inside.current : [inside.current];
      if (target && !parts.some((part) => part.current?.contains(target))) dismiss.current();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const parts = Array.isArray(inside.current) ? inside.current : [inside.current];
      const focused = document.activeElement;
      const fromInside = parts.some((part) => focused && part.current?.contains(focused));
      // The button that opens it: the first element given, when it is one, or the
      // one inside it (a <details>' summary, a button marked aria-expanded).
      const first = parts[0]?.current;
      const trigger = first?.matches("button, summary") ? first : first?.querySelector<HTMLElement>("summary, [aria-expanded]");
      dismiss.current();
      // Closed from inside, the focus would fall to the page; back to the button instead.
      if (fromInside) trigger?.focus();
    };
    // Capture: a click whose own handler stops it from bubbling still closes the menu.
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
}
