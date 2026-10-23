// A row of filter chips, one chosen at a time (react-aria's toggle button group:
// for screen readers a radio group; arrow keys move between them).
import { ToggleButton, ToggleButtonGroup } from "react-aria-components";

import styles from "./ui.module.css";

export type Chip = { id: string; label: string };

export function ChipGroup({
  label,
  chips,
  value,
  onChange,
  className,
}: {
  label: string; // the group's name for screen readers
  chips: Chip[];
  value: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <ToggleButtonGroup
      aria-label={label}
      className={[styles.chips, className].filter(Boolean).join(" ")}
      selectionMode="single"
      disallowEmptySelection
      selectedKeys={[value]}
      onSelectionChange={(keys) => {
        const [id] = keys;
        if (id !== undefined) onChange(String(id));
      }}
    >
      {chips.map((chip) => (
        <ToggleButton key={chip.id} id={chip.id} className={styles.chip}>
          {chip.label}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}
