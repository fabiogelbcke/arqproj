import type { Ref } from "react";
import { Input, SearchField } from "react-aria-components";

import styles from "./ui.module.css";

/** A grey pill to search a list (the painel's projects, a page's files): its name
 *  for screen readers, a magnifier, and Esc or × to clear it. */
export function SearchBox({
  label,
  placeholder,
  value,
  onChange,
  className,
  inputRef,
  id,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  className?: string; // where it sits (the painel floats it on phones)
  inputRef?: Ref<HTMLInputElement>;
  id?: string;
}) {
  return (
    <SearchField className={[styles.searchBox, className].filter(Boolean).join(" ")} value={value} onChange={onChange} aria-label={label}>
      <svg className={styles.searchIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        <circle cx="11" cy="11" r="6" />
        <path d="M20 20l-4.5-4.5" />
      </svg>
      <Input ref={inputRef} id={id} className={styles.searchInput} placeholder={placeholder} />
    </SearchField>
  );
}
