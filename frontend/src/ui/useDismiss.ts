import { useEffect, useRef, type RefObject } from "react";

/** Closes a menu or panel we draw ourselves when the person clicks or taps
 *  outside it, or presses Esc: what react-aria's Popover and dismissable
 *  ModalOverlay already do for theirs. `refs` hold the menu and its button, so
 *  the button's own click still toggles it; when they aren't in one element,
 *  pass both. */
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
    const escape = (event: KeyboardEvent) => event.key === "Escape" && dismiss.current();
    // Capture: a click whose own handler stops it from bubbling still closes the menu.
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
}
