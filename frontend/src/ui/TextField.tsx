import {
  FieldError,
  Input,
  Label,
  Text,
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
 *  text in its right edge, not editable. */
export function TextField({ label, description, placeholder, suffix, ...props }: Props) {
  return (
    <AriaTextField {...props} className={styles.field}>
      <Label className={styles.label}>{label}</Label>
      {suffix ? (
        <div className={styles.affixed}>
          <Input placeholder={placeholder} />
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
