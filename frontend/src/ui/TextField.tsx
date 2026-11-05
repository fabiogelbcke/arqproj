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
// `suffix`: fixed text after what is typed, inside the field (".myunio.app");
// `prefix`: before it ("alinea.myunio.app/"), so the whole address reads as one.
type Props = TextFieldProps & {
  label: string;
  /** The label for screen readers only, where the layout shows it another way. */
  labelHidden?: boolean;
  description?: string;
  placeholder?: string;
  suffix?: string;
  prefix?: string;
  className?: string;
};

/** A labelled input with its hint and validation message; with `maxLength`, the
 *  "12/28" counter in the input's right edge (ui/TextInput's); with `suffix` or
 *  `prefix`, that text in its right or left edge, not editable, and the counter
 *  just before the suffix. */
export function TextField({ label, labelHidden, description, placeholder, suffix, prefix, className, ...props }: Props) {
  return (
    <AriaTextField {...props} className={[styles.field, className].filter(Boolean).join(" ")}>
      <Label className={labelHidden ? styles.visuallyHidden : styles.label}>{label}</Label>
      {suffix || prefix ? (
        <div className={styles.affixed}>
          {prefix && (
            <span className={styles.prefix}>
              <bdi dir="ltr">{prefix}</bdi>
            </span>
          )}
          <Input placeholder={placeholder} />
          {props.maxLength && (
            <span className={styles.affixCounter} aria-hidden="true">
              {(props.value ?? "").length}/{props.maxLength}
            </span>
          )}
          {suffix && <span className={styles.suffix}>{suffix}</span>}
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
  labelHidden,
  description,
  placeholder,
  rows = 3,
  className,
  ...props
}: Props & { rows?: number }) {
  return (
    <AriaTextField {...props} className={[styles.field, className].filter(Boolean).join(" ")}>
      <Label className={labelHidden ? styles.visuallyHidden : styles.label}>{label}</Label>
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
