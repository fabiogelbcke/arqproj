import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";

import styles from "./ui.module.css";

/** "12/40" in an input's right edge: how much of its maximum length is used. The
 *  limit itself stops the typing; the counter only shows it, so screen readers
 *  skip it (they announce the input's own limit). */
export function LengthCounter({ length, max, children }: { length: number; max: number; children: ReactNode }) {
  return (
    <div className={styles.counted}>
      {children}
      <span className={styles.counter} aria-hidden="true">
        {length}/{max}
      </span>
    </div>
  );
}

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "value"> & { value: string };

/** A text input. With `maxLength`, it shows the counter instead of a hint saying
 *  "up to N characters". The painel's labelled `TextField` does the same. */
export const TextInput = forwardRef<HTMLInputElement, Props>(function TextInput({ maxLength, ...props }, ref) {
  const input = <input ref={ref} maxLength={maxLength} {...props} />;
  return maxLength ? (
    <LengthCounter length={props.value.length} max={maxLength}>
      {input}
    </LengthCounter>
  ) : (
    input
  );
});
