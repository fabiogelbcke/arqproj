// "Compartilhar arquivos" (A37): pick files from any stages and get a link to send,
// say to a supplier. The link serves the exact versions picked. Staff see every
// link of the project; a client sees the ones made on this device, whose owner
// keys (and addresses) this browser keeps.
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, call, type Schemas } from "../api/client";
import { LIMITS } from "../api/limits";
import { Button } from "../ui/Button";
import { ChipGroup } from "../ui/ChipGroup";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { DialogFrame } from "../ui/DialogFrame";
import { ErrorNotice } from "../ui/ErrorNotice";
import { TextField } from "../ui/TextField";
import { toast, toastError } from "../ui/Toast";
import { fileSize } from "./FileTools";
import { day, type Page } from "./format";

type Share = Schemas["ShareOut"];
type StageFiles = Schemas["StageFilesOut"];
type Expiry = Schemas["ShareExpiry"];
type Owned = { id: string; owner: string; url: string };

const pad = (n: number) => String(n).padStart(2, "0");
const storageKey = (slug: string) => `shares:${slug}`;

/** The links this device made on the project. Storage off: none remembered. */
export function readOwned(slug: string): Owned[] {
  try {
    const found = JSON.parse(localStorage.getItem(storageKey(slug)) ?? "[]");
    return Array.isArray(found) ? (found as Owned[]) : [];
  } catch {
    return [];
  }
}

function keepOwned(slug: string, owned: Owned) {
  try {
    localStorage.setItem(storageKey(slug), JSON.stringify([owned, ...readOwned(slug)]));
  } catch {
    // Not remembered on this device: the link still works, but can't be managed here.
  }
}

async function copy(text: string, t: (key: string) => string) {
  try {
    await navigator.clipboard.writeText(text);
    toast(t("share.copied"));
  } catch {
    toast(t("share.copyFailed")); // the link stays on screen to copy by hand
  }
}

export function SharePanel({
  page,
  slug,
  stages,
  from,
  staff,
  onClose,
}: {
  page: Page;
  slug: string;
  stages: StageFiles[] | null; // null: the files couldn't be read
  from: number | null; // the stage it was opened from (by row): its files ticked
  staff: boolean; // signed-in staff, with the session's CSRF token in hand
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation();
  const id = useId();
  const files = (index: number) => stages?.find((s) => s.position === index + 1)?.groups.flatMap((g) => g.files) ?? [];
  const [picked, setPicked] = useState<ReadonlySet<string>>(
    () => new Set(from === null ? [] : files(from).map((file) => file.key)),
  );
  const [open, setOpen] = useState<ReadonlySet<number>>(() => new Set(from === null ? [] : [from]));
  const [label, setLabel] = useState("");
  const [expiry, setExpiry] = useState<Expiry>("30d");
  const [state, setState] = useState<"picking" | "making">("picking");
  const [made, setMade] = useState<Schemas["ShareMadeOut"] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [links, setLinks] = useState<Share[] | null>(null);
  const [owned, setOwned] = useState(() => readOwned(slug));

  useEffect(() => {
    const request = staff
      ? call(api.GET("/api/pages/{slug}/shares", { params: { path: { slug } } }))
      : owned.length
        ? call(api.POST("/api/pages/{slug}/shares/mine", { params: { path: { slug } }, body: { owners: owned.map((o) => o.owner) } }))
        : Promise.resolve([]);
    request.then(setLinks, () => setLinks([]));
  }, [slug, staff, owned]);

  const all = page.stages.flatMap((_, i) => files(i));
  const chosen = all.filter((file) => picked.has(file.key));
  const bytes = chosen.reduce((sum, file) => sum + (file.size ?? 0), 0);
  const tooLarge = bytes > LIMITS.shareBytes;
  const toggle = (keys: string[], on: boolean) =>
    setPicked((was) => {
      const next = new Set(was);
      for (const key of keys) {
        if (on) next.add(key);
        else next.delete(key);
      }
      return next;
    });

  const make = async () => {
    setError(null);
    setState("making");
    try {
      const result = await call(
        api.POST("/api/pages/{slug}/shares", {
          params: { path: { slug } },
          body: { files: chosen.map((file) => file.key), label: label.trim() || null, expiry },
        }),
      );
      keepOwned(slug, { id: result.link.id, owner: result.owner, url: result.url });
      setMade(result);
      setOwned(readOwned(slug));
    } catch (failure) {
      setError(failure);
    } finally {
      setState("picking");
    }
  };

  if (made)
    return (
      <DialogFrame title={t("share.ready")} onClose={onClose}>
        <div className="share-panel">
          <p>{t("share.readyHint")}</p>
          <label className="sr" htmlFor={`${id}-url`}>
            {t("share.link")}
          </label>
          <input
            id={`${id}-url`}
            className="share-url"
            readOnly
            value={made.url}
            onFocus={(event) => event.currentTarget.select()}
          />
          <p className="share-meta">
            {made.link.expires_at
              ? t("share.validUntil", { date: day(made.link.expires_at, i18n.language, page.timezone) })
              : t("share.noExpiry")}
          </p>
          <div className="share-actions">
            {typeof navigator.share === "function" && (
              <Button onPress={() => void navigator.share({ url: made.url, title: page.name }).catch(() => undefined)}>
                {t("share.shareSheet")}
              </Button>
            )}
            <Button onPress={() => void copy(made.url, t)}>{t("share.copy")}</Button>
            <Button variant="primary" onPress={onClose}>
              {t("share.done")}
            </Button>
          </div>
        </div>
      </DialogFrame>
    );

  return (
    <DialogFrame title={t("share.open")} onClose={onClose}>
      <div className="share-panel">
        <p>{t("share.intro")}</p>
        {stages === null ? (
          <p role="alert">{t("share.filesUnavailable")}</p>
        ) : all.length === 0 ? (
          <p>{t("share.noFiles")}</p>
        ) : (
          <div className="share-stages">
            {page.stages.map((stage, index) => {
              const own = files(index);
              if (!own.length) return null;
              const count = own.filter((file) => picked.has(file.key)).length;
              const title = `${pad(index + 1)} ${stage.title}`;
              return (
                <details
                  key={index}
                  className="share-stage"
                  open={open.has(index)}
                  onToggle={(event) => {
                    const isOpen = event.currentTarget.open;
                    setOpen((was) => {
                      const next = new Set(was);
                      if (isOpen) next.add(index);
                      else next.delete(index);
                      return next;
                    });
                  }}
                >
                  <summary>
                    <span>{title}</span>
                    <span className="share-count">{t("share.stageCount", { picked: count, count: own.length })}</span>
                  </summary>
                  <label className="share-file share-file--all">
                    <input
                      type="checkbox"
                      checked={count === own.length}
                      ref={(box) => {
                        if (box) box.indeterminate = count > 0 && count < own.length;
                      }}
                      onChange={(event) => toggle(own.map((file) => file.key), event.currentTarget.checked)}
                    />
                    <span>{t("share.pickStage", { title })}</span>
                  </label>
                  {own.map((file) => (
                    <label key={file.key} className="share-file">
                      <input
                        type="checkbox"
                        checked={picked.has(file.key)}
                        onChange={(event) => toggle([file.key], event.currentTarget.checked)}
                      />
                      <span className="share-file__name">{file.name}</span>
                      {file.version != null && (
                        <span className="file__version">{t("files.version", { version: file.version })}</span>
                      )}
                      <span className="share-file__size">{fileSize(file.size, i18n.language)}</span>
                    </label>
                  ))}
                </details>
              );
            })}
          </div>
        )}
        <TextField
          label={t("share.label")}
          description={t("share.labelHint")}
          value={label}
          onChange={setLabel}
          maxLength={LIMITS.shareLabel}
        />
        <div className="share-expiry">
          <span id={`${id}-expiry`}>{t("share.expiry")}</span>
          <ChipGroup
            label={t("share.expiry")}
            value={expiry}
            onChange={(value) => setExpiry(value as Expiry)}
            chips={[
              { id: "7d", label: t("share.expiry7d") },
              { id: "30d", label: t("share.expiry30d") },
              { id: "never", label: t("share.expiryNever") },
            ]}
          />
        </div>
        <p className={`share-summary${tooLarge ? " is-over" : ""}`} role="status">
          {chosen.length
            ? t("share.summary", { count: chosen.length, size: fileSize(bytes, i18n.language) })
            : t("share.none")}
        </p>
        {tooLarge && <p className="share-over">{t("errors.share_too_large")}</p>}
        <ErrorNotice error={error} />
        <div className="share-actions">
          <Button onPress={onClose}>{t("confirm.cancel")}</Button>
          <Button
            variant="primary"
            isDisabled={!chosen.length || tooLarge || state === "making"}
            onPress={() => void make()}
          >
            {state === "making" ? t("share.making") : t("share.make")}
          </Button>
        </div>
        <ShareLinks
          page={page}
          slug={slug}
          staff={staff}
          links={links}
          owned={owned}
          onChanged={(changed) => setLinks((was) => was?.map((link) => (link.id === changed.id ? changed : link)) ?? null)}
        />
      </div>
    </DialogFrame>
  );
}

/** The project's links (staff) or this device's (a client): who it's for, what
 *  it still serves, and the way to update or turn it off. */
function ShareLinks({
  page,
  slug,
  staff,
  links,
  owned,
  onChanged,
}: {
  page: Page;
  slug: string;
  staff: boolean;
  links: Share[] | null;
  owned: Owned[];
  onChanged: (link: Share) => void;
}) {
  const { t, i18n } = useTranslation();
  const [disabling, setDisabling] = useState<Share | null>(null);
  const [busy, setBusy] = useState(false);
  if (links === null || (!staff && !links.length)) return null;
  const date = (value: string) => day(value, i18n.language, page.timezone);
  const ownerOf = (link: Share) => owned.find((o) => o.id === link.id);
  const act = async (link: Share, action: "disable" | "refresh") => {
    setBusy(true);
    try {
      const path = { slug, link_id: link.id };
      const body = { owner: ownerOf(link)?.owner ?? null };
      const changed = await call(
        action === "disable"
          ? api.POST("/api/pages/{slug}/shares/{link_id}/disable", { params: { path }, body })
          : api.POST("/api/pages/{slug}/shares/{link_id}/refresh", { params: { path }, body }),
      );
      onChanged(changed);
      toast(t(action === "disable" ? "share.disabledDone" : "share.refreshed"));
    } catch (failure) {
      toastError(failure);
    } finally {
      setBusy(false);
      setDisabling(null);
    }
  };
  return (
    <section className="share-links" aria-label={t(staff ? "share.linksStaff" : "share.linksMine")}>
      <h3>{t(staff ? "share.linksStaff" : "share.linksMine")}</h3>
      {!links.length && <p>{t("share.noLinks")}</p>}
      <ul>
        {links.map((link) => {
          const live = !link.disabled && !link.expired;
          const url = ownerOf(link)?.url;
          return (
            <li key={link.id} className={live ? undefined : "is-off"}>
              <div className="share-link__head">
                <strong>{link.label ?? t("share.noLabel")}</strong>
                {link.disabled ? (
                  <span className="pill">{t("share.disabled")}</span>
                ) : (
                  link.expired && <span className="pill">{t("share.expired")}</span>
                )}
              </div>
              <p className="share-meta">
                {[
                  staff ? (link.made_by ?? t("share.madeByClient")) : null,
                  link.available === null
                    ? t("share.checkFailed")
                    : t("share.available", { available: link.available, count: link.files }),
                  t("share.downloads", { count: link.downloads }),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              <p className="share-meta">
                {t("share.created", { date: date(link.created_at) })}
                {link.expires_at && ` · ${t("share.expires", { date: date(link.expires_at) })}`}
              </p>
              {live && !!link.newer && <p className="share-newer">{t("share.newer", { count: link.newer })}</p>}
              {live && (
                <div className="share-actions share-actions--row">
                  {url && (
                    <Button size="small" onPress={() => void copy(url, t)}>
                      {t("share.copy")}
                    </Button>
                  )}
                  {!!link.newer && (
                    <Button size="small" isDisabled={busy} onPress={() => void act(link, "refresh")}>
                      {t("share.refresh")}
                    </Button>
                  )}
                  <Button size="small" isDisabled={busy} onPress={() => setDisabling(link)}>
                    {t("share.disable")}
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {disabling && (
        <ConfirmDialog
          title={t("share.disableTitle")}
          text={t("share.disableText")}
          confirm={t("share.disable")}
          danger
          busy={busy}
          onConfirm={() => void act(disabling, "disable")}
          onCancel={() => setDisabling(null)}
        />
      )}
    </section>
  );
}
