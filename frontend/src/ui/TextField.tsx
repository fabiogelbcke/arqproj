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

type Props = TextFieldProps & { label: string; description?: string };

/** A labelled input with its hint and validation message; with `maxLength`, the
 *  "12/28" counter in the input's right edge (ui/TextInput's). */
export function TextField({ label, description, ...props }: Props) {
  return (
    <AriaTextField {...props} className={styles.field}>
      <Label className={styles.label}>{label}</Label>
      {props.maxLength ? (
        <LengthCounter length={(props.value ?? "").length} max={props.maxLength}>
          <Input className={styles.input} />
        </LengthCounter>
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
