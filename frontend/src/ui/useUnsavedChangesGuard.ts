// Leaving a form with unsaved changes asks first: the browser's own question when
// the tab closes or reloads, and the screen's when a link in the app is followed
// (a ConfirmDialog while the returned blocker's state is "blocked").
import { useEffect, useRef } from "react";
import { useBlocker } from "react-router";

export function useUnsavedChangesGuard(dirty: boolean) {
  const leaving = useBlocker(dirty);
  const released = useRef(false);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      if (!released.current) event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  /** Leaving on purpose, before the changes count as saved (a save that opens
   *  another page at once): the browser asks nothing. */
  const release = () => {
    released.current = true;
  };
  return { leaving, release };
}
