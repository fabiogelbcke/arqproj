import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Dialog, FileTrigger, Form, Heading, Modal, ModalOverlay } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { ApiError, api, call } from "../api/client";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { toast } from "../ui/Toast";
import { Cover } from "./Cover";
import {
  COVER_TYPES,
  PROJECTS,
  useChangeProject,
  useRemoveCover,
  useUploadCover,
  type ProjectSummary,
} from "./projects";
import styles from "./projects.module.css";

const NAME_MAX = 120;
const CLIENT_MAX = 48;

/** The project's settings (A24), after the prototype's "Projeto" dialog. The
 *  client link and access join it with the client page (slice 2). */
export function ProjectDialog({ project, onClose }: { project: ProjectSummary; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const change = useChangeProject();
  const archive = useChangeProject();
  const upload = useUploadCover();
  const remove = useRemoveCover();
  const queryClient = useQueryClient();
  const [name, setName] = useState(project.name);
  const [client, setClient] = useState(project.client_name);
  // The cover is saved at once (as in the prototype); show the latest one.
  const [shown, setShown] = useState(project);

  const error = change.error ?? archive.error;
  const nameTaken =
    error instanceof ApiError && error.code === "project_name_taken" && error.conflictName
      ? t("newProject.nameTakenBy", { name: error.conflictName })
      : null;

  const archiveNow = () =>
    archive.mutate(
      { id: project.id, row_version: project.row_version, status: "archived" },
      {
        onSuccess: (archived) => {
          onClose();
          // "Desfazer" runs after this dialog has gone, so it needs nothing from it.
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
              const code = failure instanceof ApiError ? failure.code : "unexpected";
              toast(i18n.exists(`errors.${code}`) ? t(`errors.${code}`) : t("errors.unexpected"));
            }
            void queryClient.invalidateQueries({ queryKey: PROJECTS });
          });
        },
      },
    );

  return (
    <ModalOverlay className={styles.overlay} isDismissable isOpen onOpenChange={(open) => !open && onClose()}>
      <Modal className={styles.modal}>
        <Dialog className={styles.dialog}>
          <Heading slot="title" className={styles.dialogTitle}>
            {t("projectSettings.title")}
          </Heading>
          <Form
            className={styles.form}
            onSubmit={(event) => {
              event.preventDefault();
              change.mutate(
                { id: project.id, row_version: project.row_version, name, client_name: client },
                {
                  onSuccess: () => {
                    toast(t("projectSettings.saved"));
                    onClose();
                  },
                },
              );
            }}
          >
            <div className={styles.row2}>
              <TextField
                label={t("projectSettings.name")}
                value={name}
                onChange={setName}
                isRequired
                maxLength={NAME_MAX}
                autoComplete="off"
              />
              <TextField
                label={t("projectSettings.client")}
                value={client}
                onChange={setClient}
                isRequired
                maxLength={CLIENT_MAX}
                autoComplete="off"
              />
            </div>

            <div className={styles.field}>
              <span className={styles.label}>{t("projectSettings.cover")}</span>
              <div className={styles.coverPreview}>
                <Cover project={shown} className={styles.coverSmall} />
                <div className={styles.coverActions}>
                  <FileTrigger
                    acceptedFileTypes={COVER_TYPES}
                    onSelect={(files) => {
                      const file = files?.[0];
                      if (file)
                        upload.mutate(
                          { id: project.id, file },
                          {
                            onSuccess: (updated) => {
                              setShown(updated);
                              toast(t("cover.saved"));
                            },
                          },
                        );
                    }}
                  >
                    <Button isDisabled={upload.isPending || remove.isPending}>
                      {shown.cover_url ? t("projectSettings.changeCover") : t("projectSettings.setCover")}
                    </Button>
                  </FileTrigger>
                  {shown.cover_url ? (
                    <Button
                      variant="ghost"
                      className={styles.danger}
                      isDisabled={upload.isPending || remove.isPending}
                      onPress={() =>
                        remove.mutate(project.id, {
                          onSuccess: (updated) => {
                            setShown(updated);
                            toast(t("projectSettings.coverRemoved"));
                          },
                        })
                      }
                    >
                      {t("projectSettings.removeCover")}
                    </Button>
                  ) : (
                    <span className={styles.note}>{t("projectSettings.noCover")}</span>
                  )}
                </div>
              </div>
              <ErrorNotice error={upload.error ?? remove.error} />
            </div>

            {nameTaken ? (
              <p role="alert" className={styles.problem}>
                {nameTaken}
              </p>
            ) : (
              <ErrorNotice error={error} />
            )}
            <div className={styles.actions}>
              <Button
                variant="ghost"
                className={`${styles.danger} ${styles.pushLeft}`}
                isDisabled={archive.isPending || change.isPending}
                onPress={archiveNow}
              >
                {t("projectSettings.archive")}
              </Button>
              <Button onPress={onClose}>{t("projectSettings.cancel")}</Button>
              <Button type="submit" variant="primary" isDisabled={change.isPending || archive.isPending}>
                {change.isPending ? t("projectSettings.saving") : t("projectSettings.save")}
              </Button>
            </div>
          </Form>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
