import {
  FieldError,
  Input,
  Label,
  Text,
  TextField as AriaTextField,
  type TextFieldProps,
} from "react-aria-components";

import styles from "./ui.module.css";

type Props = TextFieldProps & { label: string; description?: string; showCount?: boolean };

/** A labelled input with its hint and validation message; with `showCount` and a
 *  `maxLength`, a small "12/28" counter in the input's right edge. */
export function TextField({ label, description, showCount, ...props }: Props) {
  const count = showCount && props.maxLength ? `${(props.value ?? "").length}/${props.maxLength}` : null;
  return (
    <AriaTextField {...props} className={styles.field}>
      <Label className={styles.label}>{label}</Label>
      {count ? (
        <div className={styles.counted}>
          <Input className={styles.input} />
          {/* The limit itself stops typing; this only shows how much is left. */}
          <span className={styles.counter} aria-hidden="true">
            {count}
          </span>
        </div>
      ) : (
        <Input className={styles.input} />
      )}
      {description && (
        <Text slot="description" className={styles.hint}>
          {description}
        </Text>
      )}
      <FieldError className={styles.fieldError} />
    </AriaTextField>
  );
}
