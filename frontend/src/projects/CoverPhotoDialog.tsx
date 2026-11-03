// Choosing a cover (plan section 10): upload one's own photo (then the 3:2 crop),
// or one of the bundled photos, set at once. Opened from the painel card's "⋯",
// the project page's edit mode and its first-steps cover step.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "../ui/Button";
import { DialogFrame } from "../ui/DialogFrame";
import { useCoverPhotos } from "./coverPhotos";
import styles from "./projects.module.css";

export function CoverPhotoDialog({
  onClose,
  onUpload,
  onPick,
}: {
  onClose: () => void;
  onUpload: () => void; // opens the file chooser; the dialog closes
  onPick: (name: string, smallUrl: string) => Promise<void> | void; // the dialog closes once it's done
}) {
  const { t } = useTranslation();
  const photos = useCoverPhotos();
  const [saving, setSaving] = useState<string | null>(null);
  const pick = async (name: string, smallUrl: string) => {
    setSaving(name);
    try {
      await onPick(name, smallUrl);
      onClose();
    } catch {
      setSaving(null); // the caller has said what went wrong
    }
  };
  return (
    <DialogFrame title={t("coverPhotos.title")} onClose={onClose}>
      <div className={styles.coverUpload}>
        <Button
          variant="primary"
          isDisabled={saving !== null}
          onPress={() => {
            onUpload();
            onClose();
          }}
        >
          {t("coverPhotos.upload")}
        </Button>
        <span className={styles.note}>{t("coverPhotos.uploadHint")}</span>
      </div>
      <section className={styles.coverGallery} aria-labelledby="cover-gallery-title" aria-busy={photos === null}>
        <h3 id="cover-gallery-title" className={styles.coverGalleryTitle}>
          {t("coverPhotos.gallery")}
        </h3>
        {photos === "failed" ? (
          <p role="alert" className={styles.note}>
            {t("coverPhotos.unavailable")}
          </p>
        ) : (
          <div className={styles.coverGrid}>
            {(photos ?? []).map((photo, index) => (
              <button
                key={photo.name}
                type="button"
                className={styles.coverChoice}
                data-saving={saving === photo.name ? "" : undefined}
                disabled={saving !== null}
                aria-label={t("coverPhotos.photo", { number: index + 1 })}
                onClick={() => void pick(photo.name, photo.small_url)}
              >
                <img src={photo.small_url} alt="" loading="lazy" />
              </button>
            ))}
          </div>
        )}
      </section>
    </DialogFrame>
  );
}
