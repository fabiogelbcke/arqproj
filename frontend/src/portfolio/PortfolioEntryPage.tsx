// One work of the portfolio: /painel/portfolio/:entryId. Its texts, and its
// photos in order (the first is its cover): sent from the computer, or picked
// from a project's images. Either way the browser shrinks each to a JPEG of at
// most 2400 px and uploads it; the portfolio keeps its own copy.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router";

import { api, call } from "../api/client";
import { fileSource } from "../client/format";
import { useProjects, type ProjectSummary } from "../projects/projects";
import { Button } from "../ui/Button";
import { DialogFrame } from "../ui/DialogFrame";
import { ErrorNotice } from "../ui/ErrorNotice";
import { IconButton } from "../ui/IconButton";
import { Panel } from "../ui/Panel";
import { TextAreaField, TextField } from "../ui/TextField";
import { toast, toastError } from "../ui/Toast";
import {
  LIMITS,
  moved,
  resized,
  useAddPhoto,
  useChangeEntry,
  usePortfolio,
  useRemovePhoto,
  type Entry,
} from "./portfolio";
import { ProjectChoice } from "./PortfolioPage";
import styles from "./portfolio.module.css";

export function PortfolioEntryPage() {
  const { t } = useTranslation();
  const { entryId } = useParams();
  const portfolio = usePortfolio();
  const entry = portfolio.data?.entries.find((item) => item.id === entryId);
  return (
    <div className={styles.page}>
      <div className={styles.head}>
        <p className={styles.crumbs}>
          <Link to="/portfolio">{t("portfolio.title")}</Link> /
        </p>
        <h1 className={styles.title}>{entry?.title ?? t("portfolio.title")}</h1>
      </div>
      {portfolio.error ? (
        <ErrorNotice error={portfolio.error} />
      ) : !portfolio.data ? (
        <p className={styles.hint}>{t("app.loading")}</p>
      ) : !entry ? (
        <p className={styles.hint}>
          {t("portfolio.notFound")} <Link to="/portfolio">{t("portfolio.backToList")}</Link>
        </p>
      ) : (
        <>
          <Details key={entry.id} entry={entry} />
          <Photos entry={entry} />
        </>
      )}
    </div>
  );
}

function Details({ entry }: { entry: Entry }) {
  const { t } = useTranslation();
  const change = useChangeEntry();
  const [title, setTitle] = useState(entry.title);
  const [place, setPlace] = useState(entry.place);
  const [year, setYear] = useState(entry.year ? String(entry.year) : "");
  const [description, setDescription] = useState(entry.description);
  const yearNumber = year.trim() ? Number(year.trim()) : null;
  const yearOk = yearNumber === null || (Number.isInteger(yearNumber) && yearNumber >= 1900 && yearNumber <= 2100);
  const changed =
    title.trim() !== entry.title ||
    place.trim() !== entry.place ||
    yearNumber !== entry.year ||
    description.trim() !== entry.description;
  return (
    <Panel className={styles.section} aria-labelledby="portfolio-details">
      <h2 id="portfolio-details">{t("portfolio.details")}</h2>
      {entry.project_name && <p className={styles.hint}>{t("portfolio.linked", { name: entry.project_name })}</p>}
      <TextField label={t("portfolio.titleLabel")} value={title} onChange={setTitle} maxLength={LIMITS.title} isRequired />
      <div className={styles.pair}>
        <TextField
          label={t("portfolio.place")}
          placeholder={t("portfolio.placePlaceholder")}
          value={place}
          onChange={setPlace}
          maxLength={LIMITS.place}
        />
        <TextField
          label={t("portfolio.year")}
          placeholder="2025"
          inputMode="numeric"
          value={year}
          onChange={setYear}
          isInvalid={!yearOk}
          validate={() => (yearOk ? null : t("portfolio.yearInvalid"))}
          validationBehavior="aria"
        />
      </div>
      <TextAreaField
        label={t("portfolio.description")}
        description={t("portfolio.descriptionHint")}
        value={description}
        onChange={setDescription}
        maxLength={LIMITS.description}
        rows={5}
      />
      <Button
        size="small"
        className={styles.save}
        isDisabled={!changed || !title.trim() || !yearOk || change.isPending}
        onPress={() =>
          change.mutate(
            { id: entry.id, title: title.trim(), place, year: yearNumber, description },
            { onSuccess: () => toast(t("portfolio.saved")), onError: (failure) => toastError(failure) },
          )
        }
      >
        {t("portfolio.save")}
      </Button>
    </Panel>
  );
}

function Photos({ entry }: { entry: Entry }) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const change = useChangeEntry();
  const remove = useRemovePhoto();
  const add = useAddPhoto();
  const input = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  // Arriving from "Adicionar de um projeto": its images, to pick from.
  const [picking, setPicking] = useState(params.get("fotos") === "projeto");
  useEffect(() => {
    if (params.has("fotos")) setParams({}, { replace: true });
  }, [params, setParams]);
  const room = LIMITS.photos - entry.photos.length;

  /** Each source shrunk and uploaded in turn, so the order is kept. */
  async function upload(sources: { blob: () => Promise<Blob>; name: string }[]) {
    const chosen = sources.slice(0, Math.max(0, room));
    setProgress({ done: 0, total: chosen.length });
    try {
      for (const [index, source] of chosen.entries()) {
        const file = await resized(await source.blob(), source.name);
        await add.mutateAsync({ entry: entry.id, file });
        setProgress({ done: index + 1, total: chosen.length });
      }
      if (chosen.length) toast(t("portfolio.photosAdded", { count: chosen.length }));
      if (sources.length > chosen.length) toast(t("portfolio.tooManyPhotos", { count: LIMITS.photos }));
    } catch (failure) {
      toastError(failure);
    } finally {
      setProgress(null);
    }
  }

  const move = (index: number, step: number) =>
    change.mutate({ id: entry.id, photos: moved(entry.photos, index, step) }, { onError: (failure) => toastError(failure) });

  return (
    <section className={styles.section} aria-labelledby="portfolio-photos">
      <div className={styles.sectionHead}>
        <h2 id="portfolio-photos">
          {t("portfolio.photos")} <span className={styles.count}>{entry.photos.length}</span>
        </h2>
        <div className={styles.actions}>
          <Button size="small" variant="primary" isDisabled={!!progress || room <= 0} onPress={() => setPicking(true)}>
            {t("portfolio.fromProjectPhotos")}
          </Button>
          <Button size="small" isDisabled={!!progress || room <= 0} onPress={() => input.current?.click()}>
            {t("portfolio.upload")}
          </Button>
          <input
            ref={input}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            hidden
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              event.target.value = "";
              void upload(files.map((file) => ({ blob: async () => file, name: file.name })));
            }}
          />
        </div>
      </div>
      <p className={styles.hint}>{t("portfolio.photosHint")}</p>
      {progress && (
        <p className={styles.hint} role="status">
          {t("portfolio.uploading", progress)}
        </p>
      )}
      {entry.photos.length === 0 ? (
        <p className={styles.empty}>{t("portfolio.noPhotosYet")}</p>
      ) : (
        <ol className={styles.photos}>
          {entry.photos.map((photo, index) => (
            <li key={photo.id} className={styles.photo}>
              <img src={`${photo.url}?size=card`} alt={t("portfolio.photoAlt", { n: index + 1 })} loading="lazy" />
              {index === 0 && <span className={styles.coverTag}>{t("portfolio.cover")}</span>}
              <span className={styles.photoTools}>
                <IconButton
                  label={t("portfolio.movePhotoLeft")}
                  isDisabled={index === 0 || change.isPending}
                  onPress={() => move(index, -1)}
                >
                  ←
                </IconButton>
                <IconButton
                  label={t("portfolio.movePhotoRight")}
                  isDisabled={index === entry.photos.length - 1 || change.isPending}
                  onPress={() => move(index, 1)}
                >
                  →
                </IconButton>
                <IconButton
                  label={t("portfolio.removePhoto")}
                  isDisabled={remove.isPending}
                  onPress={() =>
                    remove.mutate(photo.id, {
                      onSuccess: () => toast(t("portfolio.photoRemoved")),
                      onError: (failure) => toastError(failure),
                    })
                  }
                >
                  ×
                </IconButton>
              </span>
            </li>
          ))}
        </ol>
      )}
      {picking && (
        <ProjectPhotos
          entry={entry}
          room={room}
          onClose={() => setPicking(false)}
          onAdd={(slug, files) => {
            setPicking(false);
            void upload(
              files.map((file) => ({
                name: file.name,
                blob: async () => {
                  const response = await fetch(fileSource.address(slug, file.key, "file")!);
                  if (!response.ok) throw new Error("download");
                  return response.blob();
                },
              })),
            );
          }}
        />
      )}
    </section>
  );
}

type ImageFile = { key: string; name: string };

/** A project's images to pick: the work's own project first, or any other. */
function ProjectPhotos({
  entry,
  room,
  onClose,
  onAdd,
}: {
  entry: Entry;
  room: number;
  onClose: () => void;
  onAdd: (slug: string, files: ImageFile[]) => void;
}) {
  const projects = useProjects();
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [choosing, setChoosing] = useState(false);
  const shown = project ?? projects.data?.find((item) => item.id === entry.project_id) ?? null;
  if (!projects.data) return null;
  if (choosing || !shown) {
    return (
      <ProjectChoice
        taken={new Set()}
        busy={false}
        onChoose={(chosen) => {
          setProject(chosen);
          setChoosing(false);
        }}
        onClose={onClose}
      />
    );
  }
  return (
    <ImagePicker
      key={shown.id}
      project={shown}
      room={room}
      onOtherProject={() => setChoosing(true)}
      onClose={onClose}
      onAdd={(files) => onAdd(shown.slug, files)}
    />
  );
}

function ImagePicker({
  project,
  room,
  onOtherProject,
  onClose,
  onAdd,
}: {
  project: ProjectSummary;
  room: number;
  onOtherProject: () => void;
  onClose: () => void;
  onAdd: (files: ImageFile[]) => void;
}) {
  const { t } = useTranslation();
  const files = useQuery({
    queryKey: ["page-files", project.slug],
    queryFn: () => call(api.GET("/api/pages/{slug}/files", { params: { path: { slug: project.slug } } })),
  });
  const images: ImageFile[] = (files.data?.stages ?? []).flatMap((stage) =>
    stage.groups.flatMap((group) => group.files.filter((file) => file.kind === "image")),
  );
  const [chosen, setChosen] = useState<string[]>([]);
  const toggle = (key: string) =>
    setChosen((keys) => (keys.includes(key) ? keys.filter((item) => item !== key) : [...keys, key]));
  return (
    <DialogFrame title={t("portfolio.pickTitle", { name: project.name })} onClose={onClose}>
      <div className={styles.dialogBody}>
        <p className={styles.hint}>{t("portfolio.pickHint")}</p>
        {files.error ? (
          <ErrorNotice error={files.error} />
        ) : !files.data ? (
          <p className={styles.hint}>{t("app.loading")}</p>
        ) : images.length === 0 ? (
          <p className={styles.hint}>{t("portfolio.pickNone")}</p>
        ) : (
          <ul className={styles.pickGrid}>
            {images.map((file) => {
              const on = chosen.includes(file.key);
              return (
                <li key={file.key}>
                  <label className={styles.pick} data-on={on || undefined}>
                    <input
                      type="checkbox"
                      checked={on}
                      disabled={!on && chosen.length >= room}
                      onChange={() => toggle(file.key)}
                    />
                    <img
                      src={fileSource.address(project.slug, file.key, "thumb") ?? undefined}
                      alt=""
                      loading="lazy"
                      // No preview from storage (a local folder has none): the image itself.
                      onError={(event) => {
                        const full = fileSource.address(project.slug, file.key, "inline");
                        if (full && !event.currentTarget.src.endsWith(full)) event.currentTarget.src = full;
                      }}
                    />
                    <span className={styles.pickName}>{file.name}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
        <div className={styles.dialogActions}>
          <Button size="small" variant="ghost" onPress={onOtherProject}>
            {t("portfolio.pickProject")}
          </Button>
          <Button
            variant="primary"
            isDisabled={chosen.length === 0}
            onPress={() => onAdd(images.filter((file) => chosen.includes(file.key)))}
          >
            {chosen.length ? t("portfolio.pickAdd", { count: chosen.length }) : t("portfolio.pickAddNone")}
          </Button>
        </div>
      </div>
    </DialogFrame>
  );
}
