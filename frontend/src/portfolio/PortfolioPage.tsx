// The Portfólio tab: /painel/portfolio, for every office (A45).
// Whether the office's address shows the portfolio, its format and opening
// text, the images in sections by type (as the project page's file manager:
// each section a card with its drop area, its projects then its loose photos),
// and the office's social networks. Every image is a piece of the portfolio, on
// its own or inside a project; a drop opens one dialog to say where they go.
import { useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";

import { capture } from "../posthog";
import { plain, useCreationOptions, useProjects, type ProjectSummary } from "../projects/projects";
import { useMe } from "../session/session";
import { ActionMenu } from "../ui/ActionMenu";
import { Button } from "../ui/Button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { DialogFrame } from "../ui/DialogFrame";
import { ErrorNotice } from "../ui/ErrorNotice";
import { IconButton } from "../ui/IconButton";
import { LinkButton } from "../ui/LinkButton";
import { NameDialog } from "../ui/NameDialog";
import { Panel } from "../ui/Panel";
import { SearchBox } from "../ui/SearchBox";
import { SelectField } from "../ui/SelectField";
import { TextAreaField, TextField } from "../ui/TextField";
import { toast, toastError, toastProblem } from "../ui/Toast";
import { ToggleSwitch } from "../ui/ToggleSwitch";
import {
  FORMATS,
  LIMITS,
  NETWORKS,
  isProject,
  resized,
  useAddEntry,
  useAddLoosePhoto,
  useAddPhoto,
  useAddSection,
  useChangeEntry,
  useMergeEntries,
  useOrderEntries,
  useOrderSections,
  usePortfolio,
  useRemoveEntry,
  useRemoveSection,
  useRenameSection,
  useSavePortfolio,
  useSplitEntry,
  type Entry,
  type Portfolio,
  type Section,
} from "./portfolio";
import styles from "./portfolio.module.css";
import ui from "../ui/ui.module.css";

/** The office's address as visitors type it: this page's own host. */
export const officeAddress = () => window.location.host;

type Translate = ReturnType<typeof useTranslation>["t"];

/** A section's link, or the portfolio's: `/?tipo=<slug>`, the address the
 *  public menu itself moves to. */
export const sectionLink = (section: Section | null) => (section ? `/?tipo=${section.slug}` : "/");

export function PortfolioPage() {
  const { t } = useTranslation();
  const me = useMe();
  const portfolio = usePortfolio();
  return (
    <div className={styles.page}>
      <div className={styles.head}>
        <div className={styles.headText}>
          <p className={styles.kicker}>
            {me.data?.tenant_name} / {t("portfolio.kicker")}
          </p>
          <h1 className={styles.title}>{t("portfolio.title")}</h1>
        </div>
        {portfolio.data && (
          <div className={styles.actions}>
            <ShareButton section={null} />
            <SeePortfolio published={portfolio.data.published} />
          </div>
        )}
      </div>
      {portfolio.error ? (
        <ErrorNotice error={portfolio.error} />
      ) : !portfolio.data ? (
        <p className={styles.hint}>{t("app.loading")}</p>
      ) : (
        <>
          <Publishing portfolio={portfolio.data} />
          <Sections portfolio={portfolio.data} />
          <Social portfolio={portfolio.data} />
        </>
      )}
    </div>
  );
}

// A small drawing of how a format lays the page out: the gallery's covers in
// one landscape frame, in rows; the mosaic's images in their own shapes, in
// columns.
function FormatSketch({ format }: { format: Portfolio["format"] }) {
  const blocks =
    format === "gallery"
      ? [
          [6, 6, 34, 26],
          [43, 6, 34, 26],
          [80, 6, 34, 26],
          [6, 36, 34, 26],
          [43, 36, 34, 26],
          [80, 36, 34, 26],
          [6, 66, 34, 8],
          [43, 66, 34, 8],
          [80, 66, 34, 8],
        ]
      : [
          [6, 6, 34, 26],
          [6, 36, 34, 38],
          [43, 6, 34, 34],
          [43, 44, 34, 30],
          [80, 6, 34, 20],
          [80, 30, 34, 44],
        ];
  return (
    <svg className={styles.sketch} viewBox="0 0 120 80" aria-hidden="true">
      {blocks.map(([x, y, width, height]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width={width} height={height} rx="1.5" />
      ))}
    </svg>
  );
}

/** The way to the portfolio itself, at the top of the tab and of a work's
 *  editor: the published page, or its preview while unpublished (staff only);
 *  `work` opens one work. In a new tab, so the painel stays. */
export function SeePortfolio({ published, work }: { published: boolean; work?: string }) {
  const { t } = useTranslation();
  const query = [work && `projeto=${work}`, !published && "previa=1"].filter(Boolean).join("&");
  return (
    <LinkButton variant="primary" href={query ? `/?${query}` : "/"} target="_blank" rel="noreferrer">
      {t(work ? "portfolio.viewWork" : published ? "portfolio.view" : "portfolio.preview")} <span aria-hidden="true">↗</span>
    </LinkButton>
  );
}

/** "Compartilhar": the portfolio's address, or a section's, on the clipboard;
 *  on a phone, the system's share sheet. */
export async function shareLink(section: Section | null, t: Translate) {
  const url = new URL(sectionLink(section), window.location.origin).toString();
  capture("portfolio_link_shared", { section: section !== null });
  if (navigator.share && window.matchMedia?.("(pointer: coarse)").matches) {
    await navigator.share({ url, title: section?.name }).catch(() => undefined); // closed: nothing to say
    return;
  }
  try {
    await navigator.clipboard.writeText(url);
    toast(t("portfolio.linkCopied"));
  } catch {
    toastProblem(t("portfolio.copyFailed", { url }));
  }
}

function ShareIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="12" cy="3.5" r="1.8" />
      <circle cx="4" cy="8" r="1.8" />
      <circle cx="12" cy="12.5" r="1.8" />
      <path d="M5.6 7.1l4.8-2.7M5.6 8.9l4.8 2.7" />
    </svg>
  );
}

function ShareButton({ section }: { section: Section | null }) {
  const { t } = useTranslation();
  if (section) {
    return (
      <IconButton label={t("portfolio.shareSection", { name: section.name })} onPress={() => void shareLink(section, t)}>
        <ShareIcon />
      </IconButton>
    );
  }
  return (
    <Button onPress={() => void shareLink(null, t)}>
      <ShareIcon /> {t("portfolio.share")}
    </Button>
  );
}

function Publishing({ portfolio }: { portfolio: Portfolio }) {
  const { t } = useTranslation();
  const save = useSavePortfolio();
  const [intro, setIntro] = useState(portfolio.intro);
  const shown = portfolio.entries.some((entry) => entry.photos.length > 0);
  const change = (body: { published?: boolean; intro?: string; format?: Portfolio["format"] }, done: string) =>
    save.mutate(body, { onSuccess: () => toast(done), onError: (failure) => toastError(failure) });
  return (
    <Panel className={styles.section} aria-labelledby="portfolio-publishing">
      <h2 id="portfolio-publishing" className="sr-only">
        {t("portfolio.publishing")}
      </h2>
      <ToggleSwitch
        label={t("portfolio.publish", { address: officeAddress() })}
        isSelected={portfolio.published}
        isDisabled={save.isPending}
        onChange={(on) => change({ published: on }, t(on ? "portfolio.publishedDone" : "portfolio.unpublishedDone"))}
      >
        <span className={styles.switchLabel}>{t("portfolio.publish", { address: officeAddress() })}</span>
      </ToggleSwitch>
      {portfolio.published && !shown && <p className={styles.warning}>{t("portfolio.nothingShown")}</p>}
      <div className={styles.format} role="radiogroup" aria-labelledby="portfolio-format">
        <span id="portfolio-format" className={styles.switchLabel}>
          {t("portfolio.format")}
        </span>
        <div className={styles.formats}>
          {FORMATS.map((format) => (
            <label key={format} className={styles.formatCard} data-on={portfolio.format === format || undefined}>
              <input
                type="radio"
                name="portfolio-format"
                value={format}
                className="sr-only"
                checked={portfolio.format === format}
                disabled={save.isPending}
                onChange={() => change({ format }, t("portfolio.saved"))}
              />
              <FormatSketch format={format} />
              <span className={styles.formatName}>{t(`portfolio.formats.${format}`)}</span>
              <span className={styles.hint}>{t(`portfolio.formatHint.${format}`)}</span>
            </label>
          ))}
        </div>
      </div>
      <TextAreaField
        label={t("portfolio.intro")}
        description={t("portfolio.introHint")}
        placeholder={t("portfolio.introPlaceholder")}
        value={intro}
        onChange={setIntro}
        maxLength={LIMITS.intro}
        rows={3}
      />
      <Button
        size="small"
        className={styles.save}
        isDisabled={save.isPending || intro.trim() === portfolio.intro}
        onPress={() => change({ intro }, t("portfolio.saved"))}
      >
        {t("portfolio.save")}
      </Button>
    </Panel>
  );
}

function Social({ portfolio }: { portfolio: Portfolio }) {
  const { t } = useTranslation();
  const save = useSavePortfolio();
  const [links, setLinks] = useState<Record<string, string>>(portfolio.links);
  const changed = NETWORKS.some((network) => (links[network] ?? "").trim() !== (portfolio.links[network] ?? ""));
  return (
    <Panel className={styles.section} aria-labelledby="portfolio-social">
      <h2 id="portfolio-social">{t("portfolio.links")}</h2>
      <p className={styles.hint}>{t("portfolio.linksHint")}</p>
      <div className={styles.networks}>
        {NETWORKS.map((network) => (
          <TextField
            key={network}
            label={t(`portfolio.networks.${network}`)}
            placeholder={network === "linkedin" ? "https://www.linkedin.com/company/…" : "@"}
            value={links[network] ?? ""}
            onChange={(value) => setLinks({ ...links, [network]: value })}
            maxLength={LIMITS.link}
          />
        ))}
      </div>
      <Button
        size="small"
        className={styles.save}
        isDisabled={save.isPending || !changed}
        onPress={() =>
          save.mutate(
            { links },
            {
              // As the server wrote them: "@alinea" becomes the profile's address.
              onSuccess: (saved) => {
                setLinks(saved.links);
                toast(t("portfolio.saved"));
              },
              onError: (failure) => toastError(failure),
            },
          )
        }
      >
        {t("portfolio.save")}
      </Button>
    </Panel>
  );
}

// ---- The images, in sections ----

/** A drop of photos being reviewed: the files, the section they were dropped
 *  on, and whether they were sent as one project. */
type Drop = { files: File[]; section: Section | null; asProject: boolean };

/** What a piece is called where a name is needed: its title, else its kind. */
function nameOf(entry: Entry, t: Translate): string {
  return entry.title || (entry.photos.length > 1 ? t("portfolio.untitledProject") : t("portfolio.photo"));
}

function Sections({ portfolio }: { portfolio: Portfolio }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const add = useAddEntry();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [drop, setDrop] = useState<Drop | null>(null);
  const [sheet, setSheet] = useState<string | null>(null); // a photo opened
  const [naming, setNaming] = useState<"new" | Section | null>(null);
  const [choosing, setChoosing] = useState(false); // "Adicionar de um projeto"
  const dragging = useRef<string | null>(null);
  const byId = useMemo(() => new Map(portfolio.entries.map((entry) => [entry.id, entry])), [portfolio.entries]);
  const chosen = [...selected].map((id) => byId.get(id)).filter((entry): entry is Entry => !!entry);
  const total = portfolio.entries.reduce((n, entry) => n + entry.photos.length, 0);
  const toggle = (id: string) =>
    setSelected((before) => {
      const after = new Set(before);
      if (after.has(id)) after.delete(id);
      else after.add(id);
      return after;
    });
  const fold = (key: string) =>
    setClosed((before) => {
      const after = new Set(before);
      if (after.has(key)) after.delete(key);
      else after.add(key);
      return after;
    });
  // A new work from a project opens in its editor, to pick its photos.
  const fromProject = (project: ProjectSummary) =>
    add.mutate(
      { title: project.name.slice(0, LIMITS.title), place: "", description: "", project_id: project.id },
      {
        onSuccess: (after) => {
          const made = after.entries.find((entry) => !byId.has(entry.id));
          setChoosing(false);
          if (made) void navigate(`/portfolio/${made.id}?fotos=projeto`);
        },
        onError: (failure) => toastError(failure),
      },
    );
  const open = (entry: Entry) => {
    if (isProject(entry)) void navigate(`/portfolio/${entry.id}`);
    else setSheet(entry.id);
  };
  const sections: (Section | null)[] = [...portfolio.sections, null];
  return (
    <section className={styles.section} aria-labelledby="portfolio-works">
      <div className={styles.sectionHead}>
        <h2 id="portfolio-works">
          {t("portfolio.images")} <span className={styles.count}>{total}</span>
        </h2>
        <div className={styles.actions}>
          <Button size="small" onPress={() => setChoosing(true)}>
            {t("portfolio.addFromProject")}
          </Button>
        </div>
      </div>
      {sections.map((section) => (
        <SectionCard
          key={section?.id ?? "none"}
          section={section}
          sections={portfolio.sections}
          entries={portfolio.entries.filter((entry) => (entry.section_id ?? null) === (section?.id ?? null))}
          all={portfolio.entries}
          selected={selected}
          open={!closed.has(section?.id ?? "none")}
          dragging={dragging}
          onFold={() => fold(section?.id ?? "none")}
          onToggle={toggle}
          onOpen={open}
          onDrop={(files, asProject) => setDrop({ files, section, asProject })}
          onRename={() => section && setNaming(section)}
          onSelect={(ids) => setSelected(new Set(ids))}
        />
      ))}
      <div className={styles.actions}>
        <Button onPress={() => setNaming("new")}>+ {t("portfolio.newSection")}</Button>
      </div>
      {chosen.length > 0 && (
        <SelectionBar
          chosen={chosen}
          portfolio={portfolio}
          onClear={() => setSelected(new Set())}
          onOpen={(entry) => {
            setSelected(new Set());
            open(entry);
          }}
        />
      )}
      {drop && (
        <ReviewDialog
          drop={drop}
          sections={portfolio.sections}
          projects={portfolio.entries.filter(isProject)}
          known={new Set(portfolio.entries.map((entry) => entry.id))}
          onClose={() => setDrop(null)}
        />
      )}
      {sheet && byId.get(sheet) && (
        <PhotoSheet entry={byId.get(sheet)!} sections={portfolio.sections} onClose={() => setSheet(null)} />
      )}
      {naming === "new" && <NewSectionDialog sections={portfolio.sections} onClose={() => setNaming(null)} />}
      {naming && naming !== "new" && <RenameSectionDialog section={naming} onClose={() => setNaming(null)} />}
      {choosing && (
        <ProjectChoice
          taken={new Set(portfolio.entries.map((entry) => entry.project_id).filter(Boolean) as string[])}
          busy={add.isPending}
          onChoose={fromProject}
          onClose={() => setChoosing(false)}
        />
      )}
    </section>
  );
}

function Chevron() {
  return (
    <svg className={styles.chevron} width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M3 6l5 5 5-5" />
    </svg>
  );
}

/** One section, as a stage on the project page: its name and counts, the
 *  controls, and, open, its drop area, its projects and its loose photos. The
 *  last "section", with no `section`, is "Sem tipo". */
function SectionCard({
  section,
  sections,
  entries,
  all,
  selected,
  open,
  dragging,
  onFold,
  onToggle,
  onOpen,
  onDrop,
  onRename,
  onSelect,
}: {
  section: Section | null;
  sections: Section[];
  entries: Entry[];
  all: Entry[];
  selected: Set<string>;
  open: boolean;
  dragging: { current: string | null };
  onFold: () => void;
  onToggle: (id: string) => void;
  onOpen: (entry: Entry) => void;
  onDrop: (files: File[], asProject: boolean) => void;
  onRename: () => void;
  onSelect: (ids: string[]) => void;
}) {
  const { t } = useTranslation();
  const order = useOrderSections();
  const remove = useRemoveSection();
  const change = useChangeEntry();
  const merge = useMergeEntries();
  const reorder = useOrderEntries();
  const [over, setOver] = useState(false);
  const projects = entries.filter(isProject);
  const photos = entries.filter((entry) => !isProject(entry));
  const images = entries.reduce((n, entry) => n + entry.photos.length, 0);
  const index = section ? sections.findIndex((item) => item.id === section.id) : -1;
  const name = section?.name ?? t("portfolio.typeNone");
  const key = section?.id ?? "none";
  const move = (step: number) => {
    const ids = sections.map((item) => item.id);
    const target = index + step;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target]!, ids[index]!];
    order.mutate(ids, { onError: (failure) => toastError(failure) });
  };
  /** The pieces a drag carries: the one dragged, with the selection when it is in it. */
  const carried = () => {
    const id = dragging.current;
    if (!id) return [];
    return selected.has(id) ? [id, ...[...selected].filter((other) => other !== id)] : [id];
  };
  // A piece dropped on the head moves to this section.
  const moveHere = async (ids: string[]) => {
    try {
      for (const id of ids) await change.mutateAsync({ id, section_id: section?.id ?? null });
      toast(t("portfolio.movedTo", { section: name }));
      onSelect([]);
    } catch (failure) {
      toastError(failure);
    }
  };
  /** Dropped on another piece: in its middle, they join; at its edge, the order changes. */
  const dropOn = async (target: Entry, where: "before" | "after" | "into") => {
    const ids = carried().filter((id) => id !== target.id);
    if (!ids.length) return;
    try {
      if (where === "into") {
        await merge.mutateAsync({ into: target.id, entries: ids });
        toast(t(target.photos.length > 1 ? "portfolio.addedTo" : "portfolio.grouped", { title: nameOf(target, t) }));
        onSelect([]);
        return;
      }
      const moving = new Set(ids);
      const rest = all.map((entry) => entry.id).filter((id) => !moving.has(id));
      const at = rest.indexOf(target.id) + (where === "after" ? 1 : 0);
      rest.splice(at, 0, ...ids);
      // Into this section too, when it comes from another.
      for (const id of ids) {
        const piece = all.find((entry) => entry.id === id);
        if (piece && (piece.section_id ?? null) !== (section?.id ?? null)) {
          await change.mutateAsync({ id, section_id: section?.id ?? null });
        }
      }
      await reorder.mutateAsync(rest);
    } catch (failure) {
      toastError(failure);
    }
  };
  const menu = [
    ...(section && !section.project_type ? [{ id: "rename", label: t("portfolio.renameSection") }] : []),
    ...(section && entries.length === 0 ? [{ id: "remove", label: t("portfolio.removeSection"), danger: true }] : []),
  ];
  return (
    <section
      className={styles.bucket}
      data-over={over || undefined}
      data-closed={!open || undefined}
      aria-labelledby={`section-${key}`}
    >
      <div
        className={styles.bucketHead}
        onClick={(event) => {
          if (!(event.target as Element).closest("button, a, [role=menu]")) onFold();
        }}
        onDragOver={(event) => {
          if (!dragging.current) return;
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          if (!dragging.current) return;
          event.preventDefault();
          setOver(false);
          void moveHere(carried());
        }}
      >
        <div className={styles.bucketName}>
          <h3 id={`section-${key}`}>{name}</h3>
          <span className={styles.bucketMeta}>
            {entries.length === 0
              ? t("portfolio.noPhotosYet")
              : [
                  t("portfolio.photoCount", { count: images }),
                  projects.length ? t("portfolio.projectCount", { count: projects.length }) : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
          </span>
        </div>
        <div className={styles.actions}>
          {section && <ShareButton section={section} />}
          {section && (
            <>
              <IconButton label={t("portfolio.moveUp")} isDisabled={index === 0 || order.isPending} onPress={() => move(-1)}>
                ↑
              </IconButton>
              <IconButton
                label={t("portfolio.moveDown")}
                isDisabled={index === sections.length - 1 || order.isPending}
                onPress={() => move(1)}
              >
                ↓
              </IconButton>
            </>
          )}
          {menu.length > 0 && (
            <ActionMenu
              label={t("portfolio.sectionActions", { name })}
              className={`${ui.button} ${ui.ghost} ${ui.small}`}
              placement="bottom end"
              items={menu}
              onAction={(id) => {
                if (id === "rename") onRename();
                if (id === "remove" && section)
                  remove.mutate(section.id, {
                    onSuccess: () => toast(t("portfolio.sectionRemoved")),
                    onError: (failure) => toastError(failure),
                  });
              }}
            >
              ⋯
            </ActionMenu>
          )}
          <IconButton label={t(open ? "portfolio.fold" : "portfolio.unfold", { name })} aria-expanded={open} onPress={onFold}>
            <Chevron />
          </IconButton>
        </div>
      </div>
      {open && (
        <div className={styles.bucketBody}>
          <DropArea section={section} onFiles={onDrop} />
          {entries.length === 0 ? (
            <p className={styles.hint}>{t(section ? "portfolio.sectionEmpty" : "portfolio.noSectionEmpty")}</p>
          ) : (
            <>
              {projects.length > 0 && (
                <Group title={t("portfolio.projects")} count={projects.length}>
                  <Tiles entries={projects} selected={selected} dragging={dragging} onToggle={onToggle} onOpen={onOpen} onDrop={dropOn} />
                </Group>
              )}
              {photos.length > 0 && (
                <Group title={t("portfolio.photos")} count={photos.length}>
                  <Tiles entries={photos} selected={selected} dragging={dragging} onToggle={onToggle} onOpen={onOpen} onDrop={dropOn} />
                </Group>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

function Group({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <div className={styles.group}>
      <h4 className={styles.groupTitle}>
        {title} <span className={styles.count}>{count}</span>
      </h4>
      {children}
    </div>
  );
}

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <path d="M12 16V4M7 9l5-5 5 5" />
      <path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" />
    </svg>
  );
}

/** "Solte fotos aqui ou escolha no computador", as the project page's: files
 *  dropped or chosen go to the dialog; "envie um projeto inteiro" too, as one
 *  project. */
function DropArea({ section, onFiles }: { section: Section | null; onFiles: (files: File[], asProject: boolean) => void }) {
  const { t } = useTranslation();
  const [over, setOver] = useState(false);
  const photos = useRef<HTMLInputElement>(null);
  const project = useRef<HTMLInputElement>(null);
  const images = (list: FileList | null) => [...(list ?? [])].filter((file) => file.type.startsWith("image/"));
  return (
    <div
      className={styles.drop}
      data-over={over || undefined}
      onClick={(event) => {
        if (!(event.target as Element).closest("label, input")) photos.current?.click();
      }}
      onDragOver={(event) => {
        if (![...event.dataTransfer.types].includes("Files")) return;
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        if (![...event.dataTransfer.types].includes("Files")) return;
        event.preventDefault();
        setOver(false);
        const files = images(event.dataTransfer.files);
        if (files.length) onFiles(files, false);
      }}
    >
      <UploadIcon />
      <span>{t("portfolio.dropPhotos")}</span>
      <label>
        {t("portfolio.chooseOnComputer")}
        <input
          ref={photos}
          type="file"
          accept="image/*"
          multiple
          className="sr-only"
          aria-label={t("portfolio.sendToSection", { section: section?.name ?? t("portfolio.typeNone") })}
          onChange={(event) => {
            const files = images(event.target.files);
            event.target.value = "";
            if (files.length) onFiles(files, false);
          }}
        />
      </label>
      <span>{t("portfolio.or")}</span>
      <label>
        {t("portfolio.sendProject")}
        <input
          ref={project}
          type="file"
          accept="image/*"
          multiple
          className="sr-only"
          aria-label={t("portfolio.sendProjectTo", { section: section?.name ?? t("portfolio.typeNone") })}
          onChange={(event) => {
            const files = images(event.target.files);
            event.target.value = "";
            if (files.length) onFiles(files, true);
          }}
        />
      </label>
      <small>{section ? t("portfolio.dropNoteSection", { section: section.name }) : t("portfolio.dropNoteNone")}</small>
    </div>
  );
}

function StackMark({ count }: { count: number }) {
  return (
    <span className={styles.stack} aria-hidden="true">
      <svg width="16" height="16" viewBox="0 0 16 16">
        <rect x="5" y="1.5" width="9.5" height="9.5" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <rect x="1.5" y="5" width="9.5" height="9.5" rx="1.5" fill="currentColor" />
      </svg>
      {count}
    </span>
  );
}

/** The pieces of a group as tiles: the cover, the stack mark of a project, the
 *  title over it, and the circle that selects. A click opens the piece; a drag
 *  reorders it, or joins it to the piece it is dropped on. */
function Tiles({
  entries,
  selected,
  dragging,
  onToggle,
  onOpen,
  onDrop,
}: {
  entries: Entry[];
  selected: Set<string>;
  dragging: { current: string | null };
  onToggle: (id: string) => void;
  onOpen: (entry: Entry) => void;
  onDrop: (target: Entry, where: "before" | "after" | "into") => void;
}) {
  const { t } = useTranslation();
  const [over, setOver] = useState<{ id: string; where: "before" | "after" | "into" } | null>(null);
  const place = (event: DragEvent<HTMLElement>): "before" | "after" | "into" => {
    const box = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width;
    return x < 0.25 ? "before" : x > 0.75 ? "after" : "into";
  };
  return (
    <ul className={styles.tiles} data-selecting={selected.size > 0 || undefined}>
      {entries.map((entry) => {
        // The first photo the page shows: a comparison's "after" isn't shown on its own (A46).
        const afters = new Set(entry.photos.flatMap((photo) => (photo.comparison ? [photo.comparison.after] : [])));
        const cover = entry.photos.find((photo) => !afters.has(photo.id)) ?? entry.photos[0];
        const name = nameOf(entry, t);
        const on = selected.has(entry.id);
        return (
          <li
            key={entry.id}
            className={styles.tile}
            data-on={on || undefined}
            data-over={over?.id === entry.id ? over.where : undefined}
            draggable
            onDragStart={(event) => {
              dragging.current = entry.id;
              event.dataTransfer.effectAllowed = "move";
            }}
            onDragEnd={() => {
              dragging.current = null;
              setOver(null);
            }}
            onDragOver={(event) => {
              if (!dragging.current || dragging.current === entry.id) return;
              event.preventDefault();
              setOver({ id: entry.id, where: place(event) });
            }}
            onDragLeave={() => setOver(null)}
            onDrop={(event) => {
              if (!dragging.current || dragging.current === entry.id) return;
              event.preventDefault();
              const where = place(event);
              setOver(null);
              onDrop(entry, where);
            }}
          >
            <button
              type="button"
              className={styles.tileOpen}
              aria-label={t(isProject(entry) ? "portfolio.openProject" : "portfolio.openPhoto", { name })}
              onClick={() => (selected.size ? onToggle(entry.id) : onOpen(entry))}
            >
              {cover ? (
                <img src={`${cover.url}?size=card`} alt="" loading="lazy" />
              ) : (
                <span className={styles.noCover}>{t("portfolio.noPhotos")}</span>
              )}
              {entry.photos.length > 1 && <StackMark count={entry.photos.length} />}
              {entry.title && <span className={styles.cap}>{entry.title}</span>}
              {!isProject(entry) && !entry.title && (
                <span className={styles.edit} aria-hidden="true">
                  {t("portfolio.caption")}
                </span>
              )}
            </button>
            <input
              type="checkbox"
              className={styles.check}
              checked={on}
              aria-label={t("portfolio.select", { name })}
              onChange={() => onToggle(entry.id)}
            />
          </li>
        );
      })}
    </ul>
  );
}

/** The bar at the bottom while pieces are selected, the project page's dock:
 *  what can be done with them together. */
function SelectionBar({
  chosen,
  portfolio,
  onClear,
  onOpen,
}: {
  chosen: Entry[];
  portfolio: Portfolio;
  onClear: () => void;
  onOpen: (entry: Entry) => void;
}) {
  const { t } = useTranslation();
  const merge = useMergeEntries();
  const split = useSplitEntry();
  const change = useChangeEntry();
  const remove = useRemoveEntry();
  const [removing, setRemoving] = useState(false);
  const ids = chosen.map((entry) => entry.id);
  const images = chosen.reduce((n, entry) => n + entry.photos.length, 0);
  const busy = merge.isPending || split.isPending || change.isPending || remove.isPending;
  const others = portfolio.entries.filter((entry) => isProject(entry) && !ids.includes(entry.id));
  const one = chosen.length === 1 ? chosen[0]! : null;
  const group = () => {
    const [first, ...rest] = chosen;
    merge.mutate(
      { into: first!.id, entries: rest.map((entry) => entry.id) },
      {
        onSuccess: () => {
          toast(t("portfolio.grouped"));
          onClear();
        },
        onError: (failure) => toastError(failure),
      },
    );
  };
  const addTo = (target: Entry) =>
    merge.mutate(
      { into: target.id, entries: ids },
      {
        onSuccess: () => {
          toast(t("portfolio.addedTo", { title: nameOf(target, t) }));
          onClear();
        },
        onError: (failure) => toastError(failure),
      },
    );
  const moveTo = async (section: Section | null) => {
    try {
      for (const id of ids) await change.mutateAsync({ id, section_id: section?.id ?? null });
      toast(t("portfolio.movedTo", { section: section?.name ?? t("portfolio.typeNone") }));
      onClear();
    } catch (failure) {
      toastError(failure);
    }
  };
  const removeAll = async () => {
    try {
      for (const id of ids) await remove.mutateAsync(id);
      toast(t("portfolio.removedMany", { count: chosen.length }));
      setRemoving(false);
      onClear();
    } catch (failure) {
      toastError(failure);
    }
  };
  return (
    <div className={styles.dock} role="toolbar" aria-label={t("portfolio.selectionBar")}>
      <span className={styles.dockCount}>
        {t("portfolio.selectedCount", { count: chosen.length })}
        {images !== chosen.length && <span className={styles.dockMeta}> · {t("portfolio.photoCount", { count: images })}</span>}
      </span>
      <Button size="small" variant="primary" isDisabled={busy || chosen.length < 2} onPress={group}>
        {t("portfolio.group")}
      </Button>
      {others.length > 0 && (
        <SelectField
          label={t("portfolio.addToProject")}
          labelHidden
          className={styles.dockSelect}
          value=""
          options={[
            { value: "", label: t("portfolio.addToProject") },
            ...others.map((entry) => ({ value: entry.id, label: `${nameOf(entry, t)} (${entry.photos.length})` })),
          ]}
          onChange={(value) => {
            const target = others.find((entry) => entry.id === value);
            if (target) addTo(target);
          }}
        />
      )}
      <SelectField
        label={t("portfolio.moveTo")}
        labelHidden
        className={styles.dockSelect}
        value=""
        options={[
          { value: "", label: t("portfolio.moveTo") },
          ...portfolio.sections.map((section) => ({ value: section.id, label: section.name })),
          { value: "none", label: t("portfolio.typeNone") },
        ]}
        onChange={(value) => {
          if (value) void moveTo(portfolio.sections.find((section) => section.id === value) ?? null);
        }}
      />
      {one && one.photos.length > 1 && (
        <Button
          size="small"
          isDisabled={busy}
          onPress={() =>
            split.mutate(one.id, {
              onSuccess: () => {
                toast(t("portfolio.ungrouped"));
                onClear();
              },
              onError: (failure) => toastError(failure),
            })
          }
        >
          {t("portfolio.ungroup")}
        </Button>
      )}
      {one && (
        <Button size="small" onPress={() => onOpen(one)}>
          {t(isProject(one) ? "portfolio.open" : "portfolio.caption")}
        </Button>
      )}
      <Button size="small" variant="ghost" className={styles.dockDanger} isDisabled={busy} onPress={() => setRemoving(true)}>
        {t("portfolio.remove")}
      </Button>
      <IconButton label={t("portfolio.clearSelection")} onPress={onClear}>
        ×
      </IconButton>
      {removing && (
        <ConfirmDialog
          title={t("portfolio.removeManyTitle", { count: chosen.length })}
          text={t("portfolio.removeManyText")}
          confirm={t("portfolio.remove")}
          danger
          busy={remove.isPending}
          onConfirm={() => void removeAll()}
          onCancel={() => setRemoving(false)}
        />
      )}
    </div>
  );
}

/** After a drop: the photos that arrived, a caption for each, a type for all,
 *  and where they go. Everything optional: "Adicionar" with nothing filled in
 *  simply adds them. The photos are shrunk and sent one at a time, last to
 *  first, so they land in the order dropped. */
function ReviewDialog({
  drop,
  sections,
  projects,
  known,
  onClose,
}: {
  drop: Drop;
  sections: Section[];
  projects: Entry[];
  known: Set<string>; // every piece there is: the one made for a new project is the other
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const addLoose = useAddLoosePhoto();
  const addEntry = useAddEntry();
  const addPhoto = useAddPhoto();
  const [captions, setCaptions] = useState<string[]>(() => drop.files.map(() => ""));
  const [section, setSection] = useState(drop.section?.id ?? "");
  const [where, setWhere] = useState<"loose" | "new" | "existing">(drop.asProject ? "new" : "loose");
  const [title, setTitle] = useState("");
  const [project, setProject] = useState(projects[0]?.id ?? "");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const previews = useMemo(() => drop.files.map((file) => URL.createObjectURL(file)), [drop.files]);
  // The previews point at the originals: let the browser drop them with the dialog.
  useEffect(() => () => previews.forEach((url) => URL.revokeObjectURL(url)), [previews]);
  const count = drop.files.length;
  const sectionId = section || null;
  // What an attempt already did, so that trying again after a failure goes on
  // from there instead of sending the whole drop twice: the photos sent (by
  // their place in the drop) and the project made for them.
  const sent = useRef(new Set<number>());
  const made = useRef<string | null>(null);
  const [failed, setFailed] = useState(false);

  async function send() {
    setProgress({ done: sent.current.size, total: count });
    setFailed(false);
    if (!sent.current.size) capture("portfolio_photos_dropped", { count, where, as_project: drop.asProject });
    try {
      // Loose photos go last to first: each lands first in its section, so the
      // first dropped ends first. A project's go in order, after its own.
      const order = [...drop.files.keys()].filter((index) => !sent.current.has(index));
      if (where === "loose") order.reverse();
      let target = project;
      if (where === "new") {
        if (!made.current) {
          const after = await addEntry.mutateAsync({ title: title.trim().slice(0, LIMITS.title), place: "", description: "", section_id: sectionId });
          made.current = after.entries.find((entry) => !known.has(entry.id))!.id;
        }
        target = made.current;
      }
      for (const index of order) {
        const file = await resized(drop.files[index]!, drop.files[index]!.name);
        if (where === "loose") {
          await addLoose.mutateAsync({ file, section: sectionId, title: captions[index]!.trim().slice(0, LIMITS.title) });
        } else {
          await addPhoto.mutateAsync({ entry: target, file });
        }
        sent.current.add(index);
        setProgress({ done: sent.current.size, total: count });
      }
      toast(where === "new" ? t("portfolio.projectCreated") : t("portfolio.photosAdded", { count }));
      onClose();
    } catch (failure) {
      toastError(failure);
      setProgress(null);
      setFailed(true);
    }
  }
  const started = sent.current.size > 0 || made.current !== null;

  return (
    <DialogFrame title={t("portfolio.arrived", { count })} onClose={progress ? undefined : onClose} outsideCloses={false}>
      <div className={styles.dialogBody}>
        <p className={styles.hint}>{t(where === "loose" ? "portfolio.reviewHint" : "portfolio.reviewHintProject")}</p>
        <ul className={styles.arrived}>
          {drop.files.map((file, index) => (
            <li key={`${file.name}-${index}`} data-sent={sent.current.has(index) || undefined}>
              <img src={previews[index]} alt="" />
              {/* A caption is a loose photo's; a project's photos have none. */}
              {where === "loose" && (
                <TextField
                  label={t("portfolio.captionOf", { n: index + 1 })}
                  labelHidden
                  placeholder={t("portfolio.caption")}
                  value={captions[index] ?? ""}
                  onChange={(value) => setCaptions(captions.map((caption, at) => (at === index ? value : caption)))}
                  maxLength={LIMITS.title}
                  isDisabled={started}
                />
              )}
            </li>
          ))}
        </ul>
        <div className={styles.forAll}>
          <h3>{t("portfolio.forAll")}</h3>
          <div className={styles.typeRow}>
            {/* Into an existing project, the photos take its section; once the
                upload began, the section stays what the first photos got. */}
            <SelectField
              label={t("portfolio.section")}
              value={where === "existing" ? (projects.find((entry) => entry.id === project)?.section_id ?? "") : section}
              options={[
                { value: "", label: t("portfolio.typeNone") },
                ...sections.map((item) => ({ value: item.id, label: item.name })),
              ]}
              onChange={setSection}
              disabled={where === "existing" || started}
            />
          </div>
          <div className={styles.where} role="radiogroup" aria-label={t("portfolio.where")}>
            <label>
              <input type="radio" name="where" value="loose" checked={where === "loose"} disabled={started} onChange={() => setWhere("loose")} />
              {t("portfolio.whereLoose")}
            </label>
            <div className={styles.whereRow}>
              <label>
                <input type="radio" name="where" value="new" checked={where === "new"} disabled={started} onChange={() => setWhere("new")} />
                {t("portfolio.whereNew")}
              </label>
              <TextField
                label={t("portfolio.projectTitle")}
                labelHidden
                placeholder={t("portfolio.titleOptional")}
                value={title}
                onChange={setTitle}
                onFocus={() => setWhere("new")}
                maxLength={LIMITS.title}
                isDisabled={started}
              />
            </div>
            {projects.length > 0 && (
              <div className={styles.whereRow}>
                <label>
                  <input type="radio" name="where" value="existing" checked={where === "existing"} disabled={started} onChange={() => setWhere("existing")} />
                  {t("portfolio.whereExisting")}
                </label>
                <SelectField
                  label={t("portfolio.whereExisting")}
                  labelHidden
                  value={project}
                  options={projects.map((entry) => ({ value: entry.id, label: `${nameOf(entry, t)} (${entry.photos.length})` }))}
                  onChange={(value) => {
                    if (started) return;
                    setProject(value);
                    setWhere("existing");
                  }}
                />
              </div>
            )}
          </div>
        </div>
        <div className={styles.dialogActions}>
          {progress && (
            <span className={styles.hint} aria-live="polite">
              {t("portfolio.uploading", { done: progress.done, total: progress.total })}
            </span>
          )}
          {failed && (
            <span className={styles.warning} role="status">
              {t("portfolio.uploadStopped", { done: sent.current.size, total: count })}
            </span>
          )}
          <Button variant="ghost" isDisabled={!!progress} onPress={onClose}>
            {t(started ? "portfolio.close" : "portfolio.cancel")}
          </Button>
          <Button variant="primary" isDisabled={!!progress} onPress={() => void send()}>
            {t(failed ? "portfolio.tryAgain" : "portfolio.create")}
          </Button>
        </div>
      </div>
    </DialogFrame>
  );
}

/** One photo's sheet: its caption and section, and the way out of the portfolio. */
function PhotoSheet({ entry, sections, onClose }: { entry: Entry; sections: Section[]; onClose: () => void }) {
  const { t } = useTranslation();
  const change = useChangeEntry();
  const remove = useRemoveEntry();
  const [title, setTitle] = useState(entry.title);
  const [section, setSection] = useState(entry.section_id ?? "");
  const [removing, setRemoving] = useState(false);
  const cover = entry.photos[0];
  return (
    <DialogFrame title={t("portfolio.photo")} onClose={onClose}>
      <div className={styles.dialogBody}>
        <p className={styles.hint}>{t("portfolio.captionHint")}</p>
        {cover && <img className={styles.sheetImage} src={`${cover.url}?size=card`} alt="" />}
        <TextField
          label={t("portfolio.caption")}
          placeholder={t("portfolio.titleOptional")}
          value={title}
          onChange={setTitle}
          maxLength={LIMITS.title}
        />
        <SelectField
          label={t("portfolio.section")}
          value={section}
          options={[{ value: "", label: t("portfolio.typeNone") }, ...sections.map((item) => ({ value: item.id, label: item.name }))]}
          onChange={setSection}
        />
        <p className={styles.hint}>
          <Link to={`/portfolio/${entry.id}`}>{t("portfolio.moreInEditor")}</Link>
        </p>
        <div className={styles.dialogActions}>
          <Button variant="ghost" className={styles.dockDanger} onPress={() => setRemoving(true)}>
            {t("portfolio.removeFromPortfolio")}
          </Button>
          <span className={styles.grow} />
          <Button variant="ghost" onPress={onClose}>
            {t("portfolio.cancel")}
          </Button>
          <Button
            variant="primary"
            isDisabled={change.isPending}
            onPress={() =>
              change.mutate(
                { id: entry.id, title: title.trim(), section_id: section || null },
                {
                  onSuccess: () => {
                    toast(t("portfolio.saved"));
                    onClose();
                  },
                  onError: (failure) => toastError(failure),
                },
              )
            }
          >
            {t("portfolio.save")}
          </Button>
        </div>
      </div>
      {removing && (
        <ConfirmDialog
          title={t("portfolio.removeManyTitle", { count: 1 })}
          text={t("portfolio.removeManyText")}
          confirm={t("portfolio.remove")}
          danger
          busy={remove.isPending}
          onConfirm={() =>
            remove.mutate(entry.id, {
              onSuccess: () => {
                toast(t("portfolio.removedMany", { count: 1 }));
                onClose();
              },
              onError: (failure) => toastError(failure),
            })
          }
          onCancel={() => setRemoving(false)}
        />
      )}
    </DialogFrame>
  );
}

/** "Nova seção": one of the site's types the office hasn't yet, or a name of its own. */
function NewSectionDialog({ sections, onClose }: { sections: Section[]; onClose: () => void }) {
  const { t } = useTranslation();
  const add = useAddSection();
  const [label, setLabel] = useState("");
  const used = new Set(sections.map((section) => section.project_type).filter(Boolean));
  const types = (useCreationOptions().data?.types ?? []).filter((type) => !used.has(type.key));
  const create = (body: { project_type?: string; label?: string }, name: string) =>
    add.mutate(body, {
      onSuccess: () => {
        toast(t("portfolio.sectionCreated", { name }));
        onClose();
      },
      onError: (failure) => toastError(failure),
    });
  return (
    <DialogFrame title={t("portfolio.newSection")} onClose={onClose}>
      <div className={styles.dialogBody}>
        <TextField
          label={t("portfolio.sectionName")}
          placeholder={t("portfolio.sectionPlaceholder")}
          value={label}
          onChange={setLabel}
          maxLength={LIMITS.section}
          autoFocus
        />
        {types.length > 0 && (
          <div className={styles.quickPicks}>
            <span className={styles.hint}>{t("portfolio.orSiteType")}</span>
            <div className={styles.actions}>
              {types.map((type) => {
                const name = t(`portfolio.types.${type.key}`, type.label);
                return (
                  <Button key={type.key} size="small" isDisabled={add.isPending} onPress={() => create({ project_type: type.key }, name)}>
                    {name}
                  </Button>
                );
              })}
            </div>
          </div>
        )}
        <div className={styles.dialogActions}>
          <Button variant="ghost" onPress={onClose}>
            {t("portfolio.cancel")}
          </Button>
          <Button variant="primary" isDisabled={!label.trim() || add.isPending} onPress={() => create({ label: label.trim() }, label.trim())}>
            {t("portfolio.createSection")}
          </Button>
        </div>
      </div>
    </DialogFrame>
  );
}

function RenameSectionDialog({ section, onClose }: { section: Section; onClose: () => void }) {
  const { t } = useTranslation();
  const rename = useRenameSection();
  return (
    <NameDialog
      title={t("portfolio.renameSection")}
      label={t("portfolio.sectionName")}
      initial={section.name}
      confirm={t("portfolio.save")}
      maxLength={LIMITS.section}
      busy={rename.isPending}
      onConfirm={(label) =>
        rename.mutate(
          { id: section.id, label },
          {
            onSuccess: () => {
              toast(t("portfolio.sectionRenamed", { name: label }));
              onClose();
            },
            onError: (failure) => toastError(failure),
          },
        )
      }
      onCancel={onClose}
    />
  );
}

/** The office's projects to draw a work from; those already in it say so. */
export function ProjectChoice({
  taken,
  busy,
  onChoose,
  onClose,
  title,
}: {
  taken: Set<string>;
  busy: boolean;
  onChoose: (project: ProjectSummary) => void;
  onClose: () => void;
  title?: string;
}) {
  const { t } = useTranslation();
  const projects = useProjects(true); // archived ones too: finished work
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const words = plain(query).trim().split(/\s+/).filter(Boolean);
    return (projects.data ?? []).filter((project) => {
      const haystack = plain(`${project.name} ${project.client_name}`);
      return words.every((word) => haystack.includes(word));
    });
  }, [projects.data, query]);
  return (
    <DialogFrame title={title ?? t("portfolio.chooseProject")} onClose={onClose}>
      <div className={styles.dialogBody}>
        <SearchBox
          label={t("portfolio.searchProjects")}
          placeholder={t("portfolio.searchPlaceholder")}
          value={query}
          onChange={setQuery}
        />
        {projects.error ? (
          <ErrorNotice error={projects.error} />
        ) : !projects.data ? (
          <p className={styles.hint}>{t("app.loading")}</p>
        ) : shown.length === 0 ? (
          <p className={styles.hint}>{t("portfolio.noProjects")}</p>
        ) : (
          <ul className={styles.choices}>
            {shown.map((project) => (
              <li key={project.id}>
                <button
                  type="button"
                  className={styles.choice}
                  disabled={busy}
                  onClick={() => onChoose(project)}
                >
                  {project.cover_url ? (
                    <img className={styles.choiceThumb} src={project.cover_url} alt="" loading="lazy" />
                  ) : (
                    <span className={styles.choiceThumb} aria-hidden="true" />
                  )}
                  <span className={styles.workText}>
                    <span className={styles.workTitle}>{project.name}</span>
                    <span className={styles.workMeta}>
                      {project.client_name}
                      {project.status === "archived" ? ` · ${t("projectStatus.archived")}` : ""}
                      {taken.has(project.id) ? ` · ${t("portfolio.alreadyIn")}` : ""}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </DialogFrame>
  );
}
