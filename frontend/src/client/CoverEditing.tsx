// The cover from the project page in edit mode: "Adicionar foto de capa" in the
// cover's place when there is none, "Trocar capa" and "Remover capa" on one there
// is (plan section 10). The photo is cropped to 3:2 first (ImageCropDialog).
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, call } from "../api/client";
import { ImageCropDialog } from "../ui/ImageCropDialog";
import { toast, toastError } from "../ui/Toast";
import type { Page } from "./format";

const PHOTOS = "image/jpeg,image/png,image/webp";

export function CoverPicker({ page, onChanged }: { page: Page; onChanged: () => void }) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [cropping, setCropping] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const stop = () => {
    if (cropping) URL.revokeObjectURL(cropping);
    setCropping(null);
  };
  const remove = async () => {
    setBusy(true);
    try {
      await call(
        api.DELETE("/api/projects/{project_id}/cover", { params: { path: { project_id: page.staff!.project_id } } }),
      );
      toast(t("edit.coverRemoved"));
      onChanged();
    } catch (failure) {
      toastError(failure);
    } finally {
      setBusy(false);
    }
  };
  const upload = async (file: File) => {
    setBusy(true);
    try {
      await call(
        api.PUT("/api/projects/{project_id}/cover", {
          params: { path: { project_id: page.staff!.project_id } },
          // OpenAPI describes an uploaded file as a binary string; it is the File.
          body: { file: file as unknown as string },
          bodySerializer: (body) => {
            const form = new FormData();
            form.append("file", body.file as unknown as Blob, file.name);
            return form;
          },
        }),
      );
      toast(t("edit.coverSaved"));
      onChanged();
    } catch (failure) {
      toastError(failure);
    } finally {
      setBusy(false);
    }
  };
  const chooser = (
    <input
      ref={input}
      type="file"
      hidden // opened by the buttons; the client page has no sr-only class
      accept={PHOTOS}
      onChange={(event) => {
        const file = event.target.files?.[0];
        event.target.value = ""; // the same photo can be chosen again
        if (file) setCropping(URL.createObjectURL(file));
      }}
    />
  );
  return (
    <>
      {page.cover_url ? (
        <div className="cover-actions">
          <button className="editbtn" type="button" disabled={busy} onClick={() => input.current?.click()}>
            {t("edit.changeCover")}
          </button>
          <button className="editbtn" type="button" disabled={busy} onClick={() => void remove()}>
            {t("edit.removeCover")}
          </button>
        </div>
      ) : (
        <figure className="banner">
          <button className="banner__img cover-empty" type="button" disabled={busy} onClick={() => input.current?.click()}>
            <strong>{t("edit.addCover")}</strong>
            <span>{t("edit.addCoverHint")}</span>
          </button>
        </figure>
      )}
      {chooser}
      {cropping && (
        <ImageCropDialog
          source={cropping}
          kind="cover"
          name="capa.jpg"
          onCancel={stop}
          onCropped={(file) => {
            stop();
            void upload(file);
          }}
        />
      )}
    </>
  );
}
