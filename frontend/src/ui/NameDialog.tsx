// A dialog asking for one name ("Renomear seção"): the field, filled with the
// current name, and the action's own word on the button. Laid out like ConfirmDialog.
import { useId, useState } from "react";
import { Dialog, Heading, Modal, ModalOverlay } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { Button } from "./Button";
import { TextField } from "./TextField";
import styles from "./ui.module.css";

export function NameDialog({
  title,
  label,
  initial,
  confirm,
  maxLength,
  problem,
  busy = false,
  onConfirm,
  onCancel,
}: {
  title: string;
  label: string;
  initial: string;
  confirm: string;
  maxLength?: number;
  problem?: (name: string) => string | null; // why this name can't be used, if it can't
  busy?: boolean;
  onConfirm: (name: string) => void; // trimmed, and only when it changed
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const errorId = useId();
  const [name, setName] = useState(initial);
  const trimmed = name.trim();
  const error = trimmed ? (problem?.(trimmed) ?? null) : null;
  const ready = !!trimmed && !error && !busy;
  return (
    <ModalOverlay className={styles.confirmOverlay} isDismissable isOpen onOpenChange={(open) => !open && onCancel()}>
      <Modal className={styles.confirmModal}>
        <Dialog className={styles.confirmDialog}>
          <form
            className={styles.nameDialogForm}
            onSubmit={(event) => {
              event.preventDefault();
              if (!ready) return;
              if (trimmed === initial) onCancel();
              else onConfirm(trimmed);
            }}
          >
            <Heading slot="title" className={styles.confirmTitle}>
              {title}
            </Heading>
            <TextField
              label={label}
              value={name}
              onChange={setName}
              maxLength={maxLength}
              isInvalid={!!error}
              aria-describedby={error ? errorId : undefined}
              autoFocus
            />
            {error && (
              <p id={errorId} className={styles.fieldError}>
                {error}
              </p>
            )}
            <div className={styles.confirmActions}>
              <Button onPress={onCancel}>{t("confirm.cancel")}</Button>
              <Button variant="primary" type="submit" isDisabled={!ready}>
                {confirm}
              </Button>
            </div>
          </form>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
