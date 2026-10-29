import {
  FieldError,
  Input,
  Label,
  Text,
  TextArea,
  TextField as AriaTextField,
  type TextFieldProps,
} from "react-aria-components";

import { LengthCounter } from "./TextInput";
import styles from "./ui.module.css";

// `placeholder`: an example of what to type ("Ex.: Marcenaria Silva"), never the
// field's only label (plan section 16, "Interface voice and wording").
// `suffix`: fixed text after what is typed, inside the field (".myunio.app").
type Props = TextFieldProps & { label: string; description?: string; placeholder?: string; suffix?: string };

/** A labelled input with its hint and validation message; with `maxLength`, the
 *  "12/28" counter in the input's right edge (ui/TextInput's); with `suffix`, that
 *  text in its right edge, not editable, and the counter just before it. */
export function TextField({ label, description, placeholder, suffix, ...props }: Props) {
  return (
    <AriaTextField {...props} className={styles.field}>
      <Label className={styles.label}>{label}</Label>
      {suffix ? (
        <div className={styles.affixed}>
          <Input placeholder={placeholder} />
          {props.maxLength && (
            <span className={styles.affixCounter} aria-hidden="true">
              {(props.value ?? "").length}/{props.maxLength}
            </span>
          )}
          <span className={styles.suffix}>{suffix}</span>
        </div>
      ) : props.maxLength ? (
        <LengthCounter length={(props.value ?? "").length} max={props.maxLength}>
          <Input className={styles.input} placeholder={placeholder} />
        </LengthCounter>
      ) : (
        <Input className={styles.input} placeholder={placeholder} />
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

/** A labelled multi-line field (a proposal's opening, a service's description).
 *  The text sets its height, from `rows` up; the limit stops the typing. */
export function TextAreaField({
  label,
  description,
  placeholder,
  rows = 3,
  ...props
}: Props & { rows?: number }) {
  return (
    <AriaTextField {...props} className={styles.field}>
      <Label className={styles.label}>{label}</Label>
      <TextArea className={`${styles.input} ${styles.textarea}`} placeholder={placeholder} rows={rows} />
      {description && (
        <Text slot="description" className={styles.hint}>
          {description}
        </Text>
      )}
      <FieldError className={styles.fieldError} />
    </AriaTextField>
  );
}
