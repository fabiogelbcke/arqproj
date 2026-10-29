import type { ReactNode } from "react";
import { Switch } from "react-aria-components";

import styles from "./ui.module.css";

/** An on/off setting: the switch shows the state and changes it, so a row never
 *  shows a state beside a button naming the opposite. `label` names what it
 *  switches (read by screen readers); `children`, if any, show beside it. */
export function ToggleSwitch({
  label,
  isSelected,
  isDisabled,
  onChange,
  children,
}: {
  label: string;
  isSelected: boolean;
  isDisabled?: boolean;
  onChange: (on: boolean) => void;
  children?: ReactNode;
}) {
  return (
    <Switch
      className={styles.toggleSwitch}
      aria-label={label}
      isSelected={isSelected}
      isDisabled={isDisabled}
      onChange={onChange}
    >
      {children}
      <span className={styles.menuSwitch} aria-hidden="true" />
    </Switch>
  );
}
