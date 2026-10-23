// A small ⓘ that shows a sentence of explanation beside it: on a click or tap
// (a phone has no hover), and gone on Esc or a click outside.
import type { ReactNode } from "react";
import { Button, Dialog, DialogTrigger, OverlayArrow, Popover } from "react-aria-components";

import styles from "./ui.module.css";

export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <DialogTrigger>
      <Button className={styles.infoTip} aria-label={label}>
        <span aria-hidden="true">i</span>
      </Button>
      <Popover className={styles.infoPopover} placement="top" offset={10}>
        <OverlayArrow className={styles.infoArrow}>
          <svg width={12} height={12} viewBox="0 0 12 12" aria-hidden="true">
            <path d="M0 0 L6 6 L12 0" />
          </svg>
        </OverlayArrow>
        <Dialog className={styles.infoText} aria-label={label}>
          {children}
        </Dialog>
      </Popover>
    </DialogTrigger>
  );
}
