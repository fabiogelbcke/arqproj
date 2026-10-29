// "Are you sure?" before an action: its question, what it means, and the action's
// own word on the button ("Arquivar"), never a bare "OK".
import { Dialog, Heading, Modal, ModalOverlay } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { Button } from "./Button";
import styles from "./ui.module.css";

export function ConfirmDialog({
  title,
  text,
  note,
  confirm,
  cancel,
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
  onDismiss,
}: {
  title: string;
  text: string;
  note?: string; // a short heads-up under the text, e.g. who will be emailed
  confirm: string;
  cancel?: string; // the way out's own word, e.g. "Agora não"; "Cancelar" by default
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  onDismiss?: () => void; // Escape or a click outside, when it isn't the cancel button's choice
}) {
  const { t } = useTranslation();
  return (
    <ModalOverlay className={styles.confirmOverlay} isDismissable isOpen onOpenChange={(open) => !open && (onDismiss ?? onCancel)()}>
      <Modal className={styles.confirmModal}>
        <Dialog role="alertdialog" className={styles.confirmDialog}>
          <Heading slot="title" className={styles.confirmTitle}>
            {title}
          </Heading>
          <p className={styles.confirmText}>{text}</p>
          {note && <p className={styles.confirmNote}>{note}</p>}
          <div className={styles.confirmActions}>
            <Button onPress={onCancel}>{cancel ?? t("confirm.cancel")}</Button>
            <Button
              variant="primary"
              className={danger ? styles.dangerAction : undefined}
              isDisabled={busy}
              onPress={onConfirm}
              autoFocus
            >
              {confirm}
            </Button>
          </div>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
