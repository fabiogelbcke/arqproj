import { useId } from "react";

import styles from "./ui.module.css";

/** A pill dropdown with its label ("Ordenar por"): the browser's own select, for
 *  its native list on phones. `labelHidden`: for screen readers only. */
export function SelectField({
  label,
  labelHidden = false,
  value,
  options,
  onChange,
  className,
  id,
}: {
  label: string;
  labelHidden?: boolean;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  className?: string;
  id?: string;
}) {
  const own = useId();
  const selectId = id ?? own;
  return (
    <div className={[styles.selectField, className].filter(Boolean).join(" ")}>
      <label className={labelHidden ? styles.visuallyHidden : styles.selectLabel} htmlFor={selectId}>
        {label}
      </label>
      <select id={selectId} className={styles.select} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
