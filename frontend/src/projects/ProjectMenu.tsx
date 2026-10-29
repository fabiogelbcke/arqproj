import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { ApiError, api, call } from "../api/client";
import { ActionMenu, type MenuAction } from "../ui/ActionMenu";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { ImageCropDialog } from "../ui/ImageCropDialog";
import { MoreIcon } from "../ui/MoreIcon";
import { toast, toastError } from "../ui/Toast";
import ui from "../ui/ui.module.css";
import { ProjectDialog } from "./ProjectDialog";
import {
  COVER_MAX_BYTES,
  COVER_TYPES,
  PROJECTS,
  useChangeProject,
  useRemoveCover,
  useUploadCover,
  type ProjectSummary,
} from "./projects";
import styles from "./projects.module.css";

/** The card's "⋯" (A24, revised 19 Oct 2026; a pencil until 22 Oct): a short menu. The photo is
 *  changed straight from it (picker, then the 3:2 crop) or removed; "Configurações
 *  do projeto" opens the "Projeto" dialog; "Proposta" the proposal generator (A42);
 *  archiving asks first, then offers
 *  "Desfazer". */
export function ProjectMenu({ project }: { project: ProjectSummary }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const upload = useUploadCover();
  const remove = useRemoveCover();
  const archive = useChangeProject();
  const chooser = useRef<HTMLInputElement>(null);
  const [cropping, setCropping] = useState<string | null>(null);
  const [open, setOpen] = useState<"settings" | "archive" | null>(null);

  const stopCropping = () => {
    if (cropping) URL.revokeObjectURL(cropping);
    setCropping(null);
  };
  const choose = (file: File | undefined) => {
    if (!file) return;
    // Checked here for a quick answer; the server checks the bytes again.
    if (!COVER_TYPES.includes(file.type)) return toastError(new ApiError("cover_wrong_type"));
    setCropping(URL.createObjectURL(file));
  };
  const savePhoto = (file: File) => {
    if (file.size > COVER_MAX_BYTES) return toastError(new ApiError("cover_too_large"));
    upload.mutate(
      { id: project.id, file },
      { onSuccess: () => toast(t("projectSettings.photoSaved")), onError: (failure) => toastError(failure) },
    );
  };
  const removePhoto = () =>
    remove.mutate(project.id, {
      onSuccess: () => toast(t("projectSettings.photoRemoved")),
      onError: (failure) => toastError(failure),
    });
  const archiveNow = () =>
    archive.mutate(
      { id: project.id, row_version: project.row_version, status: "archived" },
      {
        onSuccess: (archived) => {
          setOpen(null);
          // "Desfazer" runs after the menu has gone, so it needs nothing from it.
          toast(t("projectSettings.archived", { name: archived.name }), async () => {
            try {
              const back = await call(
                api.PATCH("/api/projects/{project_id}", {
                  params: { path: { project_id: archived.id } },
                  body: { row_version: archived.row_version, status: project.status },
                }),
              );
              toast(t("projectSettings.restored", { name: back.name }));
            } catch (failure) {
              toastError(failure);
            }
            void queryClient.invalidateQueries({ queryKey: PROJECTS });
          });
        },
        onError: (failure) => {
          setOpen(null);
          toastError(failure);
        },
      },
    );

  const items: MenuAction[] = [
    { id: "photo", label: project.cover_url ? t("projectSettings.changePhoto") : t("projectSettings.addPhoto") },
    ...(project.cover_url ? [{ id: "removePhoto", label: t("projectSettings.removePhoto") }] : []),
    { id: "settings", label: t("projectSettings.openSettings") },
    // The proposal generator (A42): a new one, or the latest to change.
    { id: "proposal", label: t("projectSettings.proposal") },
    { id: "archive", label: t("projectSettings.archiveProject"), danger: true },
  ];
  return (
    <>
      <ActionMenu
        label={t("projectSettings.open", { name: project.name })}
        className={`${ui.photoAction} ${styles.menuButton}`}
        items={items}
        onAction={(id) => {
          if (id === "photo") chooser.current?.click();
          else if (id === "removePhoto") removePhoto();
          else if (id === "proposal") navigate(`/projetos/${project.id}/proposta`);
          else setOpen(id as "settings" | "archive");
        }}
      >
        <MoreIcon />
      </ActionMenu>
      <input
        ref={chooser}
        type="file"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        accept={COVER_TYPES.join(",")}
        onChange={(event) => {
          choose(event.target.files?.[0]);
          event.target.value = ""; // the same file can be chosen again
        }}
      />
      {cropping && (
        <ImageCropDialog
          source={cropping}
          kind="cover"
          name="capa.jpg"
          onCancel={stopCropping}
          onCropped={(file) => {
            stopCropping();
            savePhoto(file);
          }}
        />
      )}
      {open === "settings" && <ProjectDialog project={project} onClose={() => setOpen(null)} />}
      {open === "archive" && (
        <ConfirmDialog
          title={t("projectSettings.archiveAsk", { name: project.name })}
          text={t("projectSettings.archiveMeans")}
          confirm={t("projectSettings.archive")}
          danger
          busy={archive.isPending}
          onConfirm={archiveNow}
          onCancel={() => setOpen(null)}
        />
      )}
    </>
  );
}
