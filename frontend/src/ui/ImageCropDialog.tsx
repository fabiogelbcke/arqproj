import { useEffect, useRef, useState } from "react";
import { Dialog, Heading, Modal, ModalOverlay } from "react-aria-components";
import { useTranslation } from "react-i18next";
import ReactCrop, { type PercentCrop } from "react-image-crop";
import "react-image-crop/dist/ReactCrop.css";

import { Button } from "./Button";
import { CloseButton } from "./CloseButton";
import {
  COVER_ASPECT,
  COVER_OUTPUT,
  LOGO_OUTPUT,
  centred,
  cropToFile,
  loadImage,
  sizeOf,
  trimmed,
  withoutBackground,
  type Box,
} from "./imageCrop";
import { OfficeLogo } from "./OfficeLogo";
import styles from "./ui.module.css";

type Kind = "logo" | "cover";

/** Crops an image before it is uploaded: a logo to any shape, its empty margins
 *  already trimmed, with a preview of the top bar and, on a plain background,
 *  "Remover fundo"; a cover to 3:2, the shape it shows in everywhere. `source` is
 *  an address on this site or an object URL. */
export function ImageCropDialog({
  source,
  kind,
  dark = false,
  name,
  onCancel,
  onCropped,
}: {
  source: string;
  kind: Kind;
  dark?: boolean; // a dark mode logo: shown on a dark background
  name: string; // the file's name once cropped
  onCancel: () => void;
  onCropped: (file: File) => void;
}) {
  const { t } = useTranslation();
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [failed, setFailed] = useState(false);
  const [crop, setCrop] = useState<PercentCrop | undefined>();
  const [preview, setPreview] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // The logo without its plain background, when it has one, and whether to use it.
  const [clean, setClean] = useState<{ url: string; image: HTMLImageElement } | null>(null);
  const [cleared, setCleared] = useState(false);
  const shown = useRef<HTMLImageElement>(null);
  const output = kind === "logo" ? LOGO_OUTPUT : COVER_OUTPUT;
  const working = cleared && clean ? clean.image : image;

  // The image itself (for drawing the crop) and where the box starts.
  useEffect(() => {
    let live = true;
    loadImage(source).then(
      (loaded) => {
        if (!live) return;
        const { width, height } = sizeOf(loaded);
        const start: Box =
          kind === "logo"
            ? (trimmed(loaded) ?? { x: 0, y: 0, width: 100, height: 100 })
            : centred(COVER_ASPECT, width, height);
        setImage(loaded);
        setCrop({ unit: "%", ...start });
        if (kind === "logo")
          void withoutBackground(loaded).then(async (url) => {
            if (!url) return;
            if (live) setClean({ url, image: await loadImage(url) });
            else URL.revokeObjectURL(url);
          });
      },
      () => live && setFailed(true),
    );
    return () => {
      live = false;
    };
  }, [source, kind]);
  useEffect(
    () => () => {
      if (clean) URL.revokeObjectURL(clean.url);
    },
    [clean],
  );

  // The logo as it will look in the top bar, redrawn when the box is let go.
  const box = crop && crop.width > 0 && crop.height > 0 ? crop : null;
  const [settled, setSettled] = useState<Box | null>(null);
  useEffect(() => {
    if (kind !== "logo" || !working || !settled) return;
    let url: string | null = null;
    let live = true;
    void cropToFile(working, settled, { ...output, long: 480 }, name).then((file) => {
      if (!live) return;
      url = URL.createObjectURL(file);
      setPreview(url);
    });
    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [kind, working, settled, output, name]);
  useEffect(() => {
    if (box && !settled) setSettled(box); // the trimmed start
  }, [box, settled]);

  const apply = async () => {
    if (!working || !box) return;
    setSaving(true);
    try {
      onCropped(await cropToFile(working, box, output, name));
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalOverlay className={styles.cropOverlay} isOpen isDismissable onOpenChange={(open) => !open && onCancel()}>
      <Modal className={styles.cropModal}>
        <Dialog className={styles.cropDialog}>
          <Heading slot="title" className={styles.cropTitle}>
            {t(kind === "logo" ? (dark ? "crop.darkLogoTitle" : "crop.logoTitle") : "crop.coverTitle")}
          </Heading>
          <CloseButton onPress={onCancel} />
          <p className={styles.cropHint}>{t(kind === "logo" ? "crop.logoHint" : "crop.coverHint")}</p>
          {failed ? (
            <p role="alert">{t("crop.unreadable")}</p>
          ) : (
            <div className={styles.cropStage} data-dark={dark ? "" : undefined}>
              {image && (
                <ReactCrop
                  crop={crop}
                  aspect={kind === "cover" ? COVER_ASPECT : undefined}
                  keepSelection
                  ruleOfThirds={kind === "cover"}
                  onChange={(_pixels, percent) => setCrop(percent)}
                  onComplete={(_pixels, percent) => setSettled(percent)}
                >
                  <img ref={shown} src={cleared && clean ? clean.url : source} alt={t("crop.imageAlt")} />
                </ReactCrop>
              )}
            </div>
          )}
          {clean && (
            <label className={styles.cropOption}>
              <input type="checkbox" checked={cleared} onChange={(event) => setCleared(event.target.checked)} />
              {t("crop.removeBackground")}
            </label>
          )}
          {kind === "logo" && preview && (
            <div className={styles.cropPreview}>
              <span>{t("crop.inTheBar")}</span>
              <div className={styles.cropBar} data-dark={dark ? "" : undefined}>
                <OfficeLogo light={preview} alt={t("crop.previewAlt")} />
              </div>
            </div>
          )}
          <div className={styles.cropActions}>
            <Button variant="ghost" onPress={onCancel}>
              {t("crop.cancel")}
            </Button>
            <Button variant="primary" onPress={() => void apply()} isDisabled={!box || saving || failed}>
              {t("crop.apply")}
            </Button>
          </div>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
