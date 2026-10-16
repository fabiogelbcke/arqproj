import { useEffect, useState } from "react";
import { Dialog, Heading, Modal, ModalOverlay } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { toast } from "../ui/Toast";
import { Cover } from "./Cover";
import { COVER_MAX_BYTES, COVER_TYPES, useUploadCover, type ProjectSummary } from "./projects";
import styles from "./projects.module.css";

/** The card's photo button: preview a new cover, then save it (prototype "Trocar foto"). */
export function CoverDialog({ project, onClose }: { project: ProjectSummary; onClose: () => void }) {
  const { t } = useTranslation();
  const upload = useUploadCover();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);

  const choose = (chosen: File | undefined) => {
    setFile(null);
    setPreview(null);
    setProblem(null);
    upload.reset();
    if (!chosen) return;
    // Checked here for a quick answer; the server checks the bytes again.
    if (!COVER_TYPES.includes(chosen.type)) return setProblem(t("errors.cover_wrong_type"));
    if (chosen.size > COVER_MAX_BYTES) return setProblem(t("errors.cover_too_large"));
    setFile(chosen);
    setPreview(URL.createObjectURL(chosen));
  };

  return (
    <ModalOverlay className={styles.overlay} isDismissable isOpen onOpenChange={(open) => !open && onClose()}>
      <Modal className={styles.modal}>
        <Dialog className={styles.dialog}>
          <Heading slot="title" className={styles.dialogTitle}>
            {t("cover.change")}
          </Heading>
          <p className={styles.note}>{project.name}</p>
          {preview ? (
            <span className={styles.coverFrame}>
              <img src={preview} alt={t("cover.preview")} onError={() => setProblem(t("cover.unreadable"))} />
            </span>
          ) : (
            <Cover project={project} className={styles.coverFrame} />
          )}
          <label className={styles.uploadChoice}>
            {t("cover.choose")} <span>{t("cover.chooseHint")}</span>
            <input
              type="file"
              className="sr-only"
              accept={COVER_TYPES.join(",")}
              onChange={(event) => choose(event.target.files?.[0])}
            />
          </label>
          {problem && (
            <p role="alert" className={styles.problem}>
              {problem}
            </p>
          )}
          <ErrorNotice error={upload.error} />
          <div className={styles.actions}>
            <Button onPress={onClose}>{t("projectSettings.cancel")}</Button>
            <Button
              variant="primary"
              isDisabled={!file || !!problem || upload.isPending}
              onPress={() =>
                file &&
                upload.mutate(
                  { id: project.id, file },
                  {
                    onSuccess: () => {
                      toast(t("cover.saved"));
                      onClose();
                    },
                  },
                )
              }
            >
              {upload.isPending ? t("cover.saving") : t("cover.save")}
            </Button>
          </div>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
