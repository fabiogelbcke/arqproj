import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Dialog, Form, Heading, Label, Modal, ModalOverlay, Radio, RadioGroup } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { ApiError, api, call } from "../api/client";
import { Button } from "../ui/Button";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { toast } from "../ui/Toast";
import { Cover } from "./Cover";
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

const NAME_MAX = 120;
const CLIENT_MAX = 48;

/** What happens to the cover on Salvar: nothing, a new photo, or back to the placeholder. */
type CoverChoice = { kind: "keep" } | { kind: "new"; file: File; preview: string } | { kind: "remove" };

/** The project's settings (A24), after the prototype's "Projeto" dialog, opened
 *  from the card's pencil. Name, client and cover are saved together by Salvar.
 *  The client link and access join it with the client page (slice 2). */
export function ProjectDialog({ project, onClose }: { project: ProjectSummary; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const change = useChangeProject();
  const archive = useChangeProject();
  const upload = useUploadCover();
  const remove = useRemoveCover();
  const [name, setName] = useState(project.name);
  const [client, setClient] = useState(project.client_name);
  // What the server has, so a retry after a failed photo doesn't resend (and
  // conflict with) a name change that already went through.
  const [saved, setSaved] = useState(project);
  const [cover, setCover] = useState<CoverChoice>({ kind: "keep" });
  const [slug, setSlug] = useState(project.slug);
  const [access, setAccess] = useState(project.access_mode);
  const [password, setPassword] = useState("");
  const [coverProblem, setCoverProblem] = useState<string | null>(null);
  const saving = change.isPending || upload.isPending || remove.isPending;

  const preview = cover.kind === "new" ? cover.preview : null;
  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);

  const choose = (file: File | undefined) => {
    setCoverProblem(null);
    if (!file) return;
    // Checked here for a quick answer; the server checks the bytes again.
    if (!COVER_TYPES.includes(file.type)) return setCoverProblem(t("errors.cover_wrong_type"));
    if (file.size > COVER_MAX_BYTES) return setCoverProblem(t("errors.cover_too_large"));
    setCover({ kind: "new", file, preview: URL.createObjectURL(file) });
  };

  const save = async () => {
    try {
      const linkChanged = slug !== saved.slug;
      const accessChanged = access !== saved.access_mode || (access === "password" && password !== "");
      if (name !== saved.name || client !== saved.client_name || linkChanged || accessChanged) {
        setSaved(
          await change.mutateAsync({
            id: project.id,
            row_version: saved.row_version,
            name,
            client_name: client,
            ...(linkChanged ? { slug } : {}),
            ...(accessChanged ? { access_mode: access, ...(password ? { password } : {}) } : {}),
          }),
        );
        setPassword("");
      }
      if (cover.kind === "new") await upload.mutateAsync({ id: project.id, file: cover.file });
      if (cover.kind === "remove") await remove.mutateAsync(project.id);
      toast(t("projectSettings.saved"));
      onClose();
    } catch {
      // Shown below, from the step that failed; what was saved before it stays saved.
    }
  };

  const archiveNow = () =>
    archive.mutate(
      { id: project.id, row_version: saved.row_version, status: "archived" },
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
              // As ErrorNotice: the message, plus the support code the log line carries.
              const error = failure instanceof ApiError ? failure : new ApiError("unexpected");
              const message = i18n.exists(`errors.${error.code}`) ? t(`errors.${error.code}`) : t("errors.unexpected");
              const reference = error.requestId ? ` ${t("errors.reference", { id: error.requestId })}` : "";
              toast(message + reference);
            }
            void queryClient.invalidateQueries({ queryKey: PROJECTS });
          });
        },
      },
    );

  const error = change.error ?? archive.error;
  const nameTaken =
    error instanceof ApiError && error.conflictName
      ? error.code === "project_name_taken"
        ? t("newProject.nameTakenBy", { name: error.conflictName })
        : error.code === "slug_taken"
          ? t("newProject.slugTakenBy", { name: error.conflictName })
          : null
      : null;
  // The preview: the chosen photo, the placeholder after "Remover", or the current cover.
  const shown = cover.kind === "remove" ? { ...project, cover_url: null } : project;
  const hasPhoto = !!preview || !!shown.cover_url;

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
              void save();
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

            <fieldset className={styles.coverField}>
              <legend className={styles.label}>{t("projectSettings.cover")}</legend>
              <div className={styles.coverStage}>
                {preview ? (
                  <span className={styles.cover}>
                    <img src={preview} alt={t("cover.preview")} onError={() => setCoverProblem(t("cover.unreadable"))} />
                  </span>
                ) : (
                  <Cover project={shown} />
                )}
                {!hasPhoto && <span className={styles.coverCaption}>{t("projectSettings.noCover")}</span>}
              </div>
              <div className={styles.coverActions}>
                <label className={styles.uploadChoice}>
                  {hasPhoto ? t("projectSettings.changeCover") : t("cover.choose")}
                  <span>{t("cover.chooseHint")}</span>
                  <input
                    type="file"
                    className="sr-only"
                    accept={COVER_TYPES.join(",")}
                    onChange={(event) => {
                      choose(event.target.files?.[0]);
                      event.target.value = ""; // the same file can be chosen again
                    }}
                  />
                </label>
                {hasPhoto && (
                  <Button
                    variant="ghost"
                    className={styles.danger}
                    onPress={() => {
                      setCoverProblem(null);
                      setCover(project.cover_url ? { kind: "remove" } : { kind: "keep" });
                    }}
                  >
                    {t("projectSettings.removeCover")}
                  </Button>
                )}
              </div>
              {coverProblem && (
                <p role="alert" className={styles.problem}>
                  {coverProblem}
                </p>
              )}
              <ErrorNotice error={upload.error ?? remove.error} />
            </fieldset>

            <TextField
              label={t("projectSettings.link")}
              description={t("projectSettings.linkHint", { address: `${window.location.host}/${slug || "…"}` })}
              value={slug}
              onChange={(value) => setSlug(value.toLowerCase())}
              isRequired
              maxLength={80}
              autoComplete="off"
              spellCheck="false"
            />
            <RadioGroup
              className={styles.types}
              value={access}
              onChange={(value) => setAccess(value as typeof access)}
            >
              <Label className={styles.label}>{t("projectSettings.access")}</Label>
              <Radio value="public" className={styles.choice}>
                <b>{t("projectSettings.public")}</b>
                <small className={styles.choiceNote}>{t("projectSettings.publicHint")}</small>
              </Radio>
              <Radio value="password" className={styles.choice}>
                <b>{t("projectSettings.withPassword")}</b>
                <small className={styles.choiceNote}>{t("projectSettings.withPasswordHint")}</small>
              </Radio>
            </RadioGroup>
            {access === "password" && (
              <TextField
                label={t("projectSettings.password")}
                description={
                  saved.access_mode === "password"
                    ? t("projectSettings.passwordKeep")
                    : t("projectSettings.passwordNew")
                }
                type="password"
                value={password}
                onChange={setPassword}
                isRequired={saved.access_mode !== "password"}
                minLength={6}
                autoComplete="new-password"
              />
            )}

            {nameTaken ? (
              <p role="alert" className={styles.problem}>
                {nameTaken}
              </p>
            ) : (
              <ErrorNotice error={error} values={{ min: 6 }} />
            )}
            <div className={styles.actions}>
              <Button
                variant="ghost"
                className={`${styles.danger} ${styles.pushLeft}`}
                isDisabled={archive.isPending || saving}
                onPress={archiveNow}
              >
                {t("projectSettings.archive")}
              </Button>
              <Button onPress={onClose}>{t("projectSettings.cancel")}</Button>
              <Button type="submit" variant="primary" isDisabled={saving || archive.isPending || !!coverProblem}>
                {saving ? t("projectSettings.saving") : t("projectSettings.save")}
              </Button>
            </div>
          </Form>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
