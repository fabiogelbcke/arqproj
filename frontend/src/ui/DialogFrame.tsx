import type { ReactNode } from "react";
import { Dialog, Heading, Modal, ModalOverlay, type DialogProps } from "react-aria-components";

import { CloseButton } from "./CloseButton";
import styles from "./ui.module.css";

/** A dialog's frame: the dimmed page, the box, its title and ×; Esc and a click
 *  outside close it too, unless `outsideCloses` is false (a dialog of several
 *  steps, which a stray click shouldn't end). With `onClose` it is open while
 *  rendered; without, it is the dialog of the DialogTrigger around it.
 *  While `busy` (a save or an upload under way) the × is disabled and Esc and a
 *  click outside do nothing, so its outcome is never lost with the dialog; the
 *  dialog's own Cancel is the caller's to disable. */
export function DialogFrame({
  title,
  onClose,
  role,
  outsideCloses = true,
  busy = false,
  children,
}: {
  title: ReactNode;
  onClose?: () => void;
  role?: DialogProps["role"];
  outsideCloses?: boolean;
  busy?: boolean;
  children: ReactNode | ((close: () => void) => ReactNode);
}) {
  const open = onClose ? { isOpen: true, onOpenChange: (isOpen: boolean) => !isOpen && onClose() } : {};
  return (
    <ModalOverlay
      className={styles.dialogOverlay}
      isDismissable={outsideCloses && !busy}
      isKeyboardDismissDisabled={busy}
      {...open}
    >
      <Modal className={styles.dialogModal}>
        <Dialog className={styles.dialog} role={role}>
          {({ close }) => (
            <>
              <Heading slot="title" className={styles.dialogTitle}>
                {title}
              </Heading>
              <CloseButton onPress={onClose ?? close} isDisabled={busy} />
              {typeof children === "function" ? children(onClose ?? close) : children}
            </>
          )}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
