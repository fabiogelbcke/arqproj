// "Are you sure?" before an action: its question, what it means, and the action's
// own word on the button ("Arquivar"), never a bare "OK". While the action runs
// (`busy`) it can't be left, so its outcome is never hidden; a destructive one
// (`danger`) starts on Cancelar, so a stray Enter can't do it.
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
  danger?: boolean; // destroys or removes something: the button in the danger colour, focus on Cancelar
  busy?: boolean; // the action runs: nothing closes the dialog until it answers
  onConfirm: () => void;
  onCancel: () => void;
  onDismiss?: () => void; // Escape or a click outside, when it isn't the cancel button's choice
}) {
  const { t } = useTranslation();
  return (
    <ModalOverlay
      className={styles.confirmOverlay}
      isDismissable={!busy}
      isKeyboardDismissDisabled={busy}
      isOpen
      onOpenChange={(open) => !open && (onDismiss ?? onCancel)()}
    >
      <Modal className={styles.confirmModal}>
        <Dialog role="alertdialog" className={styles.confirmDialog}>
          <Heading slot="title" className={styles.confirmTitle}>
            {title}
          </Heading>
          <p className={styles.confirmText}>{text}</p>
          {note && <p className={styles.confirmNote}>{note}</p>}
          <div className={styles.confirmActions}>
            <Button onPress={onCancel} isDisabled={busy} autoFocus={danger}>
              {cancel ?? t("confirm.cancel")}
            </Button>
            <Button variant={danger ? "danger" : "primary"} pending={busy} onPress={onConfirm} autoFocus={!danger}>
              {confirm}
            </Button>
          </div>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
