// Short confirmations at the bottom of the screen ("Salvo."), optionally with
// "Desfazer". One at a time; each replaces the last and leaves after 5 seconds.
import { useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";

import styles from "./ui.module.css";

type Toast = { id: number; message: string; undo?: () => void };

let current: Toast | null = null;
let timer: ReturnType<typeof setTimeout> | undefined;
const listeners = new Set<() => void>();

function set(next: Toast | null) {
  current = next;
  listeners.forEach((listener) => listener());
}

export function toast(message: string, undo?: () => void): void {
  clearTimeout(timer);
  set({ id: (current?.id ?? 0) + 1, message, undo });
  timer = setTimeout(() => set(null), 5000);
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
        <div key={shown.id} className={styles.toast}>
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
