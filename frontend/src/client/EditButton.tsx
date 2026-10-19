// The pencil on each editable section in edit mode. Small and always loaded;
// the editors themselves load only once staff press "Editar" (A20).
import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";

// In edit mode a click anywhere on an editable section opens its editor, as its
// pencil does. Its own links and buttons keep their job, and selecting text
// doesn't open it. The pencil stays: the way in from the keyboard.
export function openOnClick(onOpen: (() => void) | undefined) {
  if (!onOpen) return {};
  return {
    "data-opens": "",
    onClick: (event: MouseEvent) => {
      if ((event.target as Element).closest("a, button, summary, input, select, textarea, label")) return;
      if (window.getSelection()?.toString()) return;
      onOpen();
    },
  };
}

export function EditButton({ label, onClick }: { label: string; onClick: () => void }) {
  const { t } = useTranslation();
  return (
    <button className="editbtn" type="button" aria-label={t("edit.editThis", { what: label.toLowerCase() })} onClick={onClick}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        <path d="M4 20h4L19 9l-4-4L4 16v4Z M13.5 6.5l4 4" />
      </svg>
      {label}
    </button>
  );
}
