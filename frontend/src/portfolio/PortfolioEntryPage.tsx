// One work of the portfolio: /painel/portfolio/:entryId. Its texts, its
// photos in order (the first is its cover): sent from the computer, or picked
// from a project's images. Either way the browser shrinks each to a JPEG of at
// most 2400 px and uploads it; the portfolio keeps its own copy. And its videos,
// sent from the computer straight to the office's storage.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { api, ApiError, call } from "../api/client";
import { LIMITS as FIELD_LIMITS } from "../api/limits";
import { ActionMenu } from "../ui/ActionMenu";
import { fileSource } from "../client/format";
import { useProjects, type ProjectSummary } from "../projects/projects";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { DialogFrame } from "../ui/DialogFrame";
import { ErrorNotice } from "../ui/ErrorNotice";
import { BeforeAfter } from "../ui/BeforeAfter";
import { IconButton } from "../ui/IconButton";
import { Panel } from "../ui/Panel";
import { SelectField } from "../ui/SelectField";
import { TextAreaField, TextField } from "../ui/TextField";
import { toast, toastError, toastProblem } from "../ui/Toast";
import {
  LIMITS,
  PORTFOLIO,
  SUGGESTED_LINES,
  VIDEO_TYPES,
  moved,
  parsedArea,
  resized,
  sendVideo,
  useAddPhoto,
  useChangeEntry,
  useComparePhoto,
  useDetailTypes,
  usePortfolio,
  useRemovePhoto,
  useRemoveVideo,
  useSplitEntry,
  videoPoster,
  type Entry,
  type Section,
  type SheetLine,
} from "./portfolio";
import { useFeature } from "../session/session";
import { ProjectChoice, SeePortfolio } from "./PortfolioPage";
import styles from "./portfolio.module.css";
import ui from "../ui/ui.module.css";

export function PortfolioEntryPage() {
  const { t } = useTranslation();
  const { entryId } = useParams();
  const portfolio = usePortfolio();
  const entry = portfolio.data?.entries.find((item) => item.id === entryId);
  return (
    <div className={styles.page}>
      <div className={styles.head}>
        <div className={styles.headText}>
          <p className={styles.crumbs}>
            <Link to="/portfolio">{t("portfolio.title")}</Link> /
          </p>
          <h1 className={styles.title}>{entry ? entry.title || t("portfolio.untitled") : t("portfolio.title")}</h1>
        </div>
        {portfolio.data && entry && (
          <div className={styles.actions}>
            {entry.photos.length > 1 && <Ungroup entry={entry} />}
            {/* A work without photos isn't on the page: nothing to see yet. */}
            {entry.photos.length > 0 && <SeePortfolio published={portfolio.data.published} work={entry.id} />}
          </div>
        )}
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
        <div className={styles.editor}>
          <div className={styles.media}>
            <Photos entry={entry} />
            <Videos entry={entry} />
          </div>
          <Details key={entry.id} entry={entry} sections={portfolio.data.sections} />
        </div>
      )}
    </div>
  );
}

/** "Desfazer projeto": its images after the first become pieces of their own,
 *  back in the tab, in the same section; this one keeps its words and videos. */
function Ungroup({ entry }: { entry: Entry }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const split = useSplitEntry();
  const [asking, setAsking] = useState(false);
  return (
    <>
      <Button onPress={() => setAsking(true)}>{t("portfolio.ungroup")}</Button>
      {asking && (
        <ConfirmDialog
          title={t("portfolio.ungroupTitle")}
          text={t("portfolio.ungroupText", { count: entry.photos.length - 1 })}
          confirm={t("portfolio.ungroup")}
          busy={split.isPending}
          onConfirm={() =>
            split.mutate(entry.id, {
              onSuccess: () => {
                toast(t("portfolio.ungrouped"));
                void navigate("/portfolio");
              },
              onError: (failure) => toastError(failure),
            })
          }
          onCancel={() => setAsking(false)}
        />
      )}
    </>
  );
}

/** The work's words, beside its photos and videos: its title, the one text
 *  the portfolio needs, and the rest folded under "Mais informações", open when
 *  anything there is filled in: one sheet of rows, a name and its value, as the
 *  public page shows them (type, place, year, the details, the description,
 *  the credits). */
function Details({ entry, sections }: { entry: Entry; sections: Section[] }) {
  const { t } = useTranslation();
  const change = useChangeEntry();
  const hasMore =
    !!entry.place || !!entry.year || !!entry.description || !!entry.section_id || !!entry.credits || entry.details.length > 0;
  const [title, setTitle] = useState(entry.title);
  const [place, setPlace] = useState(entry.place);
  const [year, setYear] = useState(entry.year ? String(entry.year) : "");
  const [description, setDescription] = useState(entry.description);
  const [kind, setKind] = useState(entry.section_id ?? "");
  const [sheet, setSheet] = useState<SheetLine[]>(entry.details);
  const [credits, setCredits] = useState(entry.credits);
  const yearNumber = year.trim() ? Number(year.trim()) : null;
  const yearOk = yearNumber === null || (Number.isInteger(yearNumber) && yearNumber >= 1900 && yearNumber <= 2100);
  const lines = sheet.map(sentLine);
  const sheetOk = lines.every((line) => line !== null);
  const changed =
    title.trim() !== entry.title ||
    place.trim() !== entry.place ||
    yearNumber !== entry.year ||
    description.trim() !== entry.description ||
    kind !== (entry.section_id ?? "") ||
    JSON.stringify(lines) !== JSON.stringify(entry.details.map(sentLine)) ||
    credits.trim() !== entry.credits;
  return (
    <Panel className={`${styles.section} ${styles.words}`} aria-labelledby="portfolio-details">
      <h2 id="portfolio-details">{t("portfolio.details")}</h2>
      {entry.project_name && <p className={styles.hint}>{t("portfolio.linked", { name: entry.project_name })}</p>}
      <TextField
        label={t("portfolio.titleLabel")}
        description={t("portfolio.titleHint")}
        placeholder={t("portfolio.titleOptional")}
        value={title}
        onChange={setTitle}
        maxLength={LIMITS.title}
      />
      <details className={styles.more} open={hasMore}>
        <summary>
          <span>{t("portfolio.more")}</span>
          <span className={styles.hint}>{t("portfolio.moreHint")}</span>
        </summary>
        <div className={styles.moreBody}>
          <Row label={t("portfolio.section")}>
            <SelectField
              label={t("portfolio.section")}
              labelHidden
              className={styles.rowSelect}
              value={kind}
              options={[
                { value: "", label: t("portfolio.typeNone") },
                ...sections.map((section) => ({ value: section.id, label: section.name })),
              ]}
              onChange={setKind}
            />
          </Row>
          <Row label={t("portfolio.place")}>
            <TextField
              label={t("portfolio.place")}
              labelHidden
              placeholder={t("portfolio.placePlaceholder")}
              value={place}
              onChange={setPlace}
              maxLength={LIMITS.place}
            />
          </Row>
          <Row label={t("portfolio.year")}>
            <TextField
              label={t("portfolio.year")}
              labelHidden
              className={styles.short}
              placeholder="2025"
              inputMode="numeric"
              value={year}
              onChange={setYear}
              isInvalid={!yearOk}
              validate={() => (yearOk ? null : t("portfolio.yearInvalid"))}
              validationBehavior="aria"
            />
          </Row>
          <Sheet lines={sheet} onChange={setSheet} />
          <Row label={t("portfolio.description")} top>
            <TextAreaField
              label={t("portfolio.description")}
              labelHidden
              value={description}
              onChange={setDescription}
              maxLength={LIMITS.description}
              rows={4}
            />
          </Row>
          <Row label={t("portfolio.credits")}>
            <TextField
              label={t("portfolio.credits")}
              labelHidden
              placeholder={t("portfolio.creditsPlaceholder")}
              value={credits}
              onChange={setCredits}
              maxLength={LIMITS.credits}
            />
          </Row>
        </div>
      </details>
      <Button
        size="small"
        className={styles.save}
        isDisabled={!changed || !yearOk || !sheetOk || change.isPending}
        onPress={() =>
          change.mutate(
            {
              id: entry.id,
              title: title.trim(),
              place,
              year: yearNumber,
              description,
              section_id: kind || null,
              details: lines.filter((line) => line !== null),
              credits,
            },
            { onSuccess: () => toast(t("portfolio.saved")), onError: (failure) => toastError(failure) },
          )
        }
      >
        {t("portfolio.save")}
      </Button>
    </Panel>
  );
}

/** A line of the sheet as the server takes it: a built-in detail's key, or the
 *  office's own label, with the value as typed (an area as a plain number); null
 *  when it can't be sent yet: no value, no name on an own line, or an area that
 *  isn't one. */
function sentLine(line: SheetLine): { key?: string; label?: string; value: string } | null {
  const value = line.value.trim();
  if (!value || (!line.key && !line.label.trim())) return null;
  if (line.type === "area") {
    const area = parsedArea(value);
    return typeof area === "number" ? { key: line.key ?? undefined, value: String(area) } : null;
  }
  return line.key ? { key: line.key, value } : { label: line.label.trim(), value };
}

/** The work's sheet: the built-in details the project page offers (each once,
 *  typed: an area in m², a date, text) and lines with the office's own label
 *  ("Fotografia", "Construtora"), in the order added. */
/** One row of the sheet: its name on the left (or, for a line of the office's
 *  own, the field for the name), the value on the right, and, for a line that
 *  can go, its × at the end. Every row shares the same columns, so the fold
 *  reads as one sheet. `top`: the name level with the top of a tall field. */
function Row({
  label,
  name,
  remove,
  top,
  children,
}: {
  label: string;
  name?: ReactNode;
  remove?: ReactNode;
  top?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={styles.row} data-top={top || undefined}>
      {name ?? (
        <span className={styles.rowLabel} aria-hidden="true">
          {label}
        </span>
      )}
      <div className={styles.rowField}>{children}</div>
      {remove ?? <span />}
    </div>
  );
}

function Sheet({ lines, onChange }: { lines: SheetLine[]; onChange: (lines: SheetLine[]) => void }) {
  const { t } = useTranslation();
  const types = useDetailTypes().data ?? [];
  const unused = types.filter((type) => !lines.some((line) => line.key === type.key));
  const suggested = SUGGESTED_LINES.map((id) => ({ id: `suggest:${id}`, label: t(`portfolio.suggested.${id}`) })).filter(
    (item) => !lines.some((line) => !line.key && line.label.trim() === item.label),
  );
  const set = (index: number, change: Partial<SheetLine>) =>
    onChange(lines.map((line, i) => (i === index ? { ...line, ...change } : line)));
  return (
    <div className={styles.sheet} role="group" aria-label={t("portfolio.sheet")}>
      {lines.map((line, index) => {
        const name = line.key ? line.label : line.label.trim() || t("portfolio.ownLabel");
        const area = line.type === "area";
        const areaOk = !area || !line.value.trim() || typeof parsedArea(line.value) === "number";
        return (
          <Row
            key={line.key ?? `own-${index}`}
            label={line.label}
            name={
              line.key ? undefined : (
                <TextField
                  label={t("portfolio.ownLabel")}
                  labelHidden
                  placeholder={t("portfolio.ownLabelPlaceholder")}
                  value={line.label}
                  onChange={(label) => set(index, { label })}
                  maxLength={LIMITS.label}
                />
              )
            }
            remove={
              <IconButton
                label={t("portfolio.removeDetail", { name })}
                onPress={() => onChange(lines.filter((_, i) => i !== index))}
              >
                ×
              </IconButton>
            }
          >
            <TextField
              label={line.key ? line.label : t("portfolio.detailValue")}
              labelHidden
              type={line.type === "date" ? "date" : "text"}
              inputMode={area ? "decimal" : undefined}
              suffix={area ? "m²" : undefined}
              value={line.value}
              onChange={(value) => set(index, { value })}
              maxLength={line.type === "text" ? LIMITS.detail : undefined}
              isInvalid={!areaOk}
              validate={() => (areaOk ? null : t("portfolio.areaInvalid"))}
              validationBehavior="aria"
            />
          </Row>
        );
      })}
      <div className={styles.row}>
        <span />
        {lines.length >= LIMITS.details ? (
          <p className={styles.hint}>{t("portfolio.detailsFull", { count: LIMITS.details })}</p>
        ) : (
          <ActionMenu
            label={t("portfolio.addDetail")}
            className={`${ui.button} ${ui.secondary} ${ui.small} ${styles.addDetail}`}
            placement="bottom start"
            items={[
              ...unused.map((type) => ({ id: type.key, label: type.label })),
              ...suggested,
              { id: "own", label: t("portfolio.ownDetail") },
            ]}
            onAction={(id) => {
              const type = types.find((candidate) => candidate.key === id);
              const suggestion = suggested.find((item) => item.id === id);
              onChange([
                ...lines,
                type
                  ? { key: type.key, label: type.label, type: type.type, value: "" }
                  : { key: null, label: suggestion?.label ?? "", type: "text", value: "" },
              ]);
            }}
          >
            + {t("portfolio.addDetail")}
          </ActionMenu>
        )}
      </div>
    </div>
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
  const compares = useFeature("before_after"); // "Antes e depois" (A40, A46)
  // Each comparison's "after" photo, by its id: the "before" photo it goes with.
  const afterOf = new Map(entry.photos.flatMap((photo) => (photo.comparison ? [[photo.comparison.after, photo.id]] : [])));
  const [comparing, setComparing] = useState<string | null>(null); // the "before" photo being paired
  const cover = entry.photos.find((photo) => !afterOf.has(photo.id))?.id;
  // Another photo still free to be this one's "after": in no comparison yet.
  const free = (id: string) =>
    entry.photos.some((other) => other.id !== id && !other.comparison && !afterOf.has(other.id));

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
              {/* The first photo the page shows: an "after" photo never is (A46). */}
              {photo.id === cover && <span className={styles.coverTag}>{t("portfolio.cover")}</span>}
              {/* A comparison (A46): its "before" photo says so; its "after" which one it goes with. */}
              {photo.comparison && <span className={styles.compareTag}>{t("portfolio.compareTag")}</span>}
              {afterOf.has(photo.id) && (
                <span className={styles.compareTag}>
                  {t("portfolio.afterOf", { n: entry.photos.findIndex((p) => p.id === afterOf.get(photo.id)) + 1 })}
                </span>
              )}
              <span className={styles.photoTools}>
                {compares && !afterOf.has(photo.id) && (photo.comparison || free(photo.id)) && (
                  <IconButton label={t("portfolio.compare")} onPress={() => setComparing(photo.id)}>
                    ⇄
                  </IconButton>
                )}
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
      {comparing && <ComparePhotos entry={entry} before={comparing} onClose={() => setComparing(null)} />}
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

function Videos({ entry }: { entry: Entry }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const change = useChangeEntry();
  const remove = useRemoveVideo();
  const input = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<{ n: number; total: number; percent: number } | null>(null);
  const room = LIMITS.videos - entry.videos.length;

  /** Each in turn: its poster first, which also shows the browser can play it. */
  async function upload(files: File[]) {
    const chosen = files.slice(0, Math.max(0, room));
    let added = 0;
    try {
      for (const [index, file] of chosen.entries()) {
        if (!VIDEO_TYPES.includes(file.type) || file.size > LIMITS.videoMb * 1024 * 1024) {
          throw new ApiError("portfolio_video_refused");
        }
        setProgress({ n: index + 1, total: chosen.length, percent: 0 });
        const poster = await videoPoster(file).catch(() => null);
        if (!poster) {
          toastProblem(t("portfolio.videoUnreadable", { name: file.name }));
          break;
        }
        const portfolio = await sendVideo(entry.id, file, poster, (fraction) =>
          setProgress({ n: index + 1, total: chosen.length, percent: Math.round(fraction * 100) }),
        );
        client.setQueryData(PORTFOLIO, portfolio);
        added += 1;
      }
      if (added) toast(t("portfolio.videosAdded", { count: added }));
      if (files.length > chosen.length) toast(t("portfolio.tooManyVideos", { count: LIMITS.videos }));
    } catch (failure) {
      toastError(failure);
    } finally {
      setProgress(null);
    }
  }

  const move = (index: number, step: number) =>
    change.mutate({ id: entry.id, videos: moved(entry.videos, index, step) }, { onError: (failure) => toastError(failure) });

  return (
    <section className={styles.section} aria-labelledby="portfolio-videos">
      <div className={styles.sectionHead}>
        <h2 id="portfolio-videos">
          {t("portfolio.videos")} <span className={styles.count}>{entry.videos.length}</span>
        </h2>
        <div className={styles.actions}>
          <Button size="small" isDisabled={!!progress || room <= 0} onPress={() => input.current?.click()}>
            {t("portfolio.uploadVideos")}
          </Button>
          <input
            ref={input}
            type="file"
            accept={VIDEO_TYPES.join(",")}
            multiple
            hidden
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              event.target.value = "";
              void upload(files);
            }}
          />
        </div>
      </div>
      <p className={styles.hint}>{t("portfolio.videosHint")}</p>
      {progress && (
        <p className={styles.hint} role="status">
          {t("portfolio.videoUploading", progress)}
        </p>
      )}
      {entry.videos.length === 0 ? (
        <p className={styles.empty}>{t("portfolio.noVideosYet")}</p>
      ) : (
        <ol className={styles.photos}>
          {entry.videos.map((video, index) => (
            <li key={video.id} className={styles.photo}>
              {/* Whole, not cropped: a 9:16 story stays recognisable. */}
              <img
                className={styles.poster}
                src={video.poster_url}
                alt={t("portfolio.videoAlt", { n: index + 1 })}
                loading="lazy"
              />
              <span className={styles.playTag} aria-hidden="true">
                ▶
              </span>
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
                  isDisabled={index === entry.videos.length - 1 || change.isPending}
                  onPress={() => move(index, 1)}
                >
                  →
                </IconButton>
                <IconButton
                  label={t("portfolio.removeVideo")}
                  isDisabled={remove.isPending}
                  onPress={() =>
                    remove.mutate(video.id, {
                      onSuccess: () => toast(t("portfolio.videoRemoved")),
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
    </section>
  );
}

type ImageFile = { key: string; name: string };

/** "Antes e depois" (A46): this photo, the "before", with another of the work's
 *  photos as its "after", and the slider's words; a preview of the slider. The
 *  public page shows the two as one, on the slider. */
function ComparePhotos({ entry, before, onClose }: { entry: Entry; before: string; onClose: () => void }) {
  const { t } = useTranslation();
  const compare = useComparePhoto();
  const photo = entry.photos.find((candidate) => candidate.id === before)!;
  const [after, setAfter] = useState<string | null>(photo.comparison?.after ?? null);
  const [labels, setLabels] = useState({ before: photo.comparison?.before_label ?? "", after: photo.comparison?.after_label ?? "" });
  // In another comparison already, as either side: not offered.
  const taken = new Set(
    entry.photos.flatMap((other) => (other.id === before || !other.comparison ? [] : [other.id, other.comparison.after])),
  );
  const offered = entry.photos.filter((other) => other.id !== before && !taken.has(other.id));
  const chosen = entry.photos.find((other) => other.id === after);
  const words = { before: t("compare.before"), after: t("compare.after") };
  const save = (wanted: string | null) =>
    compare.mutate(
      { photo: before, after: wanted, before_label: labels.before.trim() || null, after_label: labels.after.trim() || null },
      {
        onSuccess: () => {
          toast(wanted ? t("portfolio.compared") : t("portfolio.uncompared"));
          onClose();
        },
        onError: (failure: unknown) => toastError(failure),
      },
    );
  return (
    <DialogFrame title={t("portfolio.compareTitle")} onClose={onClose}>
      <div className={styles.dialogBody}>
        <p className={styles.hint}>{t("portfolio.compareHint")}</p>
        <div role="radiogroup" aria-label={t("portfolio.chooseAfter")} className={styles.pickGrid}>
          {offered.map((other) => (
            <button
              key={other.id}
              type="button"
              role="radio"
              aria-checked={other.id === after}
              aria-label={t("portfolio.photoAlt", { n: entry.photos.indexOf(other) + 1 })}
              className={styles.pick}
              data-on={other.id === after || undefined}
              onClick={() => setAfter(other.id)}
            >
              <img src={`${other.url}?size=card`} alt="" loading="lazy" />
            </button>
          ))}
        </div>
        <div className={styles.compareLabels}>
          {(["before", "after"] as const).map((side) => (
            <TextField
              key={side}
              label={t("compare.label", { side: words[side] })}
              placeholder={words[side]}
              value={labels[side]}
              onChange={(label) => setLabels({ ...labels, [side]: label })}
              maxLength={FIELD_LIMITS.comparisonLabel}
            />
          ))}
        </div>
        {chosen && (
          <div className={styles.comparePreview}>
            <BeforeAfter
              title={entry.title}
              before={{ src: `${photo.url}?size=full`, label: labels.before.trim() || words.before }}
              after={{ src: `${chosen.url}?size=full`, label: labels.after.trim() || words.after }}
            />
          </div>
        )}
        <div className={ui.confirmActions}>
          {photo.comparison && (
            <Button isDisabled={compare.isPending} onPress={() => save(null)}>
              {t("portfolio.uncompare")}
            </Button>
          )}
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button variant="primary" isDisabled={!after || compare.isPending} onPress={() => save(after)}>
            {t("projectSettings.save")}
          </Button>
        </div>
      </div>
    </DialogFrame>
  );
}

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
  const projects = useProjects(true); // archived ones too: finished work
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
  // A before-and-after comparison's card (A46) is two images: each offered on its own.
  const images: ImageFile[] = (files.data?.stages ?? []).flatMap((stage) =>
    stage.groups.flatMap((group) =>
      group.files
        .flatMap((file) =>
          file.comparison ? [{ ...file, name: file.comparison.before_name }, file.comparison.after] : [file],
        )
        .filter((file) => file.kind === "image"),
    ),
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
