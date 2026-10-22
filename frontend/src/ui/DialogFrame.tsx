import type { ReactNode } from "react";
import { Dialog, Heading, Modal, ModalOverlay, type DialogProps } from "react-aria-components";

import { CloseButton } from "./CloseButton";
import styles from "./ui.module.css";

/** A dialog's frame: the dimmed page, the box, its title and ×; Esc and a click
 *  outside close it too. With `onClose` it is open while rendered; without, it
 *  is the dialog of the DialogTrigger around it. */
export function DialogFrame({
  title,
  onClose,
  role,
  children,
}: {
  title: ReactNode;
  onClose?: () => void;
  role?: DialogProps["role"];
  children: ReactNode | ((close: () => void) => ReactNode);
}) {
  const open = onClose ? { isOpen: true, onOpenChange: (isOpen: boolean) => !isOpen && onClose() } : {};
  return (
    <ModalOverlay className={styles.dialogOverlay} isDismissable {...open}>
      <Modal className={styles.dialogModal}>
        <Dialog className={styles.dialog} role={role}>
          {({ close }) => (
            <>
              <Heading slot="title" className={styles.dialogTitle}>
                {title}
              </Heading>
              <CloseButton onPress={onClose ?? close} />
              {typeof children === "function" ? children(onClose ?? close) : children}
            </>
          )}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
