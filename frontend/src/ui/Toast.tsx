// Short messages at the bottom of the screen: a confirmation ("Salvo."), optionally
// with "Desfazer", or a failure with its support code. One at a time; each replaces
// the last and leaves after 5 seconds (a failure after 8, to note the code).
import { useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";

import { errorMessage } from "./ErrorNotice";
import styles from "./ui.module.css";

type Toast = { id: number; message: string; kind: "success" | "error"; undo?: () => void };

let current: Toast | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;
const listeners = new Set<() => void>();

function set(next: Toast | null) {
  current = next;
  listeners.forEach((listener) => listener());
}

function show(toast: Omit<Toast, "id">, seconds: number) {
  clearTimeout(timer);
  set({ ...toast, id: (current?.id ?? 0) + 1 });
  timer = setTimeout(() => set(null), seconds * 1000);
}

/** Something worked: "Salvo.", "Projeto criado.", with an optional "Desfazer". */
export function toast(message: string, undo?: () => void): void {
  show({ message, kind: "success", undo }, 5);
}

/** A request failed: its message in the user's language and the support code, as
 *  ErrorNotice shows them. `values` fill the message (e.g. a size limit). */
export function toastError(failure: unknown, values?: Record<string, unknown>): void {
  show({ message: errorMessage(failure, values), kind: "error" }, 8);
}

const store = {
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  snapshot: () => current,
};

/** The live region is always present, so screen readers announce each message. */
export function Toaster() {
  const { t } = useTranslation();
  const shown = useSyncExternalStore(store.subscribe, store.snapshot);
  return (
    <div role="status" className={styles.toastRegion}>
      {shown && (
        <div key={shown.id} className={styles.toast} data-kind={shown.kind}>
          <span className={styles.toastMark} aria-hidden="true">
            {shown.kind === "error" ? "!" : "✓"}
          </span>
          <span>{shown.message}</span>
          {shown.undo && (
            <button
              type="button"
              onClick={() => {
                shown.undo?.();
                set(null);
              }}
            >
              {t("projectSettings.undo")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
