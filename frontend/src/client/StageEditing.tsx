// Edit mode, part 2: the prototype's stage controls (rename, move, remove), its
// "Adicionar etapa" and its progress rail (advance, back, complete, reopen).
// Every change carries the page's row version; folders follow in Drive.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api, call, type Schemas } from "../api/client";
import { toast } from "../ui/Toast";
import type { Page } from "./format";

type Staff = NonNullable<Page["staff"]>;
const pad = (n: number) => String(n).padStart(2, "0");

/** `locked`: a change was saved and the page hasn't reloaded yet, so another
 * click would carry the old row version and be refused as "changed meanwhile". */
function useChange(onChanged: () => void, locked: boolean) {
  const { t, i18n } = useTranslation();
  const [busy, setBusy] = useState(false);
  return {
    busy: busy || locked,
    run: async (work: () => Promise<unknown>, done?: string, undo?: () => void) => {
      setBusy(true);
      try {
        await work();
        toast(done ?? t("projectSettings.saved"), undo);
        onChanged();
        return true;
      } catch (failure) {
        const error = failure instanceof ApiError ? failure : new ApiError("unexpected");
        const message = i18n.exists(`errors.${error.code}`) ? t(`errors.${error.code}`) : t("errors.unexpected");
        toast(error.requestId ? `${message} ${t("errors.reference", { id: error.requestId })}` : message);
        return false;
      } finally {
        setBusy(false);
      }
    },
  };
}

const path = (staff: Staff) => ({ project_id: staff.project_id });

/** Rename, move up or down, remove: on each stage's title row in edit mode. */
export function StageControls({
  page,
  staff,
  index,
  onChanged,
  locked = false,
}: {
  page: Page;
  staff: Staff;
  index: number;
  onChanged: () => void;
  locked?: boolean;
}) {
  const { t } = useTranslation();
  const stage = page.stages[index]!;
  const [mode, setMode] = useState<"idle" | "rename" | "remove">("idle");
  const [title, setTitle] = useState(stage.title);
  const change = useChange(onChanged, locked);
  const position = stage.position;

  const rename = () =>
    change
      .run(() =>
        call(
          api.PATCH("/api/projects/{project_id}/stages/{position}", {
            params: { path: { ...path(staff), position } },
            body: { row_version: staff.row_version, title },
          }),
        ),
      )
      .then((ok) => ok && setMode("idle"));
  const move = (direction: -1 | 1) =>
    change.run(() =>
      call(
        api.POST("/api/projects/{project_id}/stages/{position}/move", {
          params: { path: { ...path(staff), position } },
          body: { row_version: staff.row_version, direction },
        }),
      ),
    );
  const remove = () =>
    change.run(
      () =>
        call(
          api.DELETE("/api/projects/{project_id}/stages/{position}", {
            params: { path: { ...path(staff), position }, query: { row_version: staff.row_version } },
          }),
        ),
      t("edit.stageRemoved", { title: stage.title }),
    ).then((ok) => ok && setMode("idle")); // this row shows the next stage now

  if (mode === "rename")
    return (
      <form
        className="stage-rename"
        onSubmit={(event) => {
          event.preventDefault();
          void rename();
        }}
      >
        <label className="sr" htmlFor={`rn-${index}`}>
          {t("edit.stageName")}
        </label>
        <input
          id={`rn-${index}`}
          value={title}
          maxLength={80}
          autoFocus
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Escape" && setMode("idle")}
        />
        <button className="b b--small" type="button" onClick={() => setMode("idle")}>
          {t("projectSettings.cancel")}
        </button>
        <button className="b b--small b--primary" type="submit" disabled={change.busy || !title.trim()}>
          {t("projectSettings.save")}
        </button>
      </form>
    );
  if (mode === "remove")
    return (
      <div className="stage-confirm" role="group" aria-label={t("edit.removeStage", { title: stage.title })}>
        <p>{t("edit.removeStageConfirm", { title: stage.title })}</p>
        <button className="b b--small" type="button" onClick={() => setMode("idle")}>
          {t("projectSettings.cancel")}
        </button>
        <button className="b b--small b--danger" type="button" disabled={change.busy} onClick={() => void remove()}>
          {t("edit.remove")}
        </button>
      </div>
    );
  return (
    <span className="stagectl">
      <button
        className="iconbtn"
        type="button"
        aria-label={t("edit.renameStage", { title: stage.title })}
        onClick={() => {
          setTitle(stage.title); // this row's stage now: rows stay put while stages move
          setMode("rename");
        }}
      >
        ✎
      </button>
      <button
        className="iconbtn"
        type="button"
        aria-label={t("edit.moveUp", { title: stage.title })}
        disabled={index === 0 || change.busy}
        onClick={() => void move(-1)}
      >
        ↑
      </button>
      <button
        className="iconbtn"
        type="button"
        aria-label={t("edit.moveDown", { title: stage.title })}
        disabled={index === page.stages.length - 1 || change.busy}
        onClick={() => void move(1)}
      >
        ↓
      </button>
      <button className="iconbtn" type="button" aria-label={t("edit.removeStage", { title: stage.title })} onClick={() => setMode("remove")}>
        ×
      </button>
    </span>
  );
}

/** "Adicionar etapa": a built-in stage the project doesn't have yet, or the office's own. */
export function AddStage({
  page,
  staff,
  onChanged,
  locked = false,
}: {
  page: Page;
  staff: Staff;
  onChanged: () => void;
  locked?: boolean;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<Schemas["StageOption"][]>([]);
  const [custom, setCustom] = useState("");
  const change = useChange(onChanged, locked);
  useEffect(() => {
    if (open) call(api.GET("/api/project-types")).then((found) => setOptions(found.stages), () => setOptions([]));
  }, [open]);
  const used = new Set(page.stages.map((stage) => stage.title));
  const add = (body: { builtin_key?: string; title?: string }) =>
    change
      .run(() =>
        call(
          api.POST("/api/projects/{project_id}/stages", {
            params: { path: path(staff) },
            body: { row_version: staff.row_version, ...body },
          }),
        ),
      )
      .then((ok) => {
        if (ok) {
          setOpen(false);
          setCustom("");
        }
      });
  if (!open)
    return (
      <div className="addstage">
        <button className="ghostline" type="button" onClick={() => setOpen(true)}>
          + {t("edit.addStage")}
        </button>
      </div>
    );
  return (
    <div className="addstage">
      <div className="editor add-stage">
        <h3>{t("edit.addStage")}</h3>
        <label className="field">
          <span>{t("edit.builtInStage")}</span>
          <select className="select" value="" disabled={change.busy} onChange={(e) => e.target.value && void add({ builtin_key: e.target.value })}>
            <option value="">{t("edit.chooseStage")}</option>
            {options
              .filter((option) => !used.has(option.title))
              .map((option) => (
                <option key={option.key} value={option.key}>
                  {option.title}
                </option>
              ))}
          </select>
        </label>
        <form
          className="field"
          onSubmit={(event) => {
            event.preventDefault();
            if (custom.trim()) void add({ title: custom.trim() });
          }}
        >
          <label htmlFor="custom-stage">{t("edit.ownStage")}</label>
          <div className="add-stage__row">
            <input className="input" id="custom-stage" value={custom} maxLength={80} onChange={(e) => setCustom(e.target.value)} />
            <button className="b b--primary" type="submit" disabled={change.busy || !custom.trim()}>
              {t("edit.add")}
            </button>
          </div>
        </form>
        <p className="hint">{t("edit.addStageHint")}</p>
        <div className="editor__actions">
          <button className="b" type="button" onClick={() => setOpen(false)}>
            {t("projectSettings.cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}

/** The prototype's rail: where the project is, and the next step. */
export function ProgressRail({
  page,
  staff,
  onChanged,
  locked = false,
}: {
  page: Page;
  staff: Staff;
  onChanged: () => void;
  locked?: boolean;
}) {
  const { t } = useTranslation();
  const change = useChange(onChanged, locked);
  const send = (action: "advance" | "back" | "complete" | "reopen", version = staff.row_version) =>
    call(
      api.POST("/api/projects/{project_id}/progress", {
        params: { path: path(staff) },
        body: { row_version: version, action },
      }),
    );
  if (!page.stages.length) return <div className="rail"><div className="rail__now"><p>{t("edit.noStagesYet")}</p></div></div>;
  if (page.completed)
    return (
      <div className="rail">
        <div className="rail__now">
          <span className="big">✓</span>
          <p>
            {t("page.allDone")}
            <small>{t("edit.allDoneNote")}</small>
          </p>
        </div>
        <button className="b b--small" type="button" disabled={change.busy} onClick={() => void change.run(() => send("reopen"), t("edit.reopened"))}>
          {t("edit.reopen")}
        </button>
      </div>
    );
  const current = Math.max(1, page.current_position ?? 1);
  const here = page.stages[current - 1];
  const next = page.stages[current];
  return (
    <div className="rail">
      <div className="rail__now">
        <span className="big tnum">{pad(current)}</span>
        <p>
          {here?.title}
          <small>{t("edit.currentNote")}</small>
        </p>
      </div>
      {current > 1 && (
        <button className="b b--ghost b--small" type="button" disabled={change.busy} onClick={() => void change.run(() => send("back"))}>
          {t("edit.back")}
        </button>
      )}
      {/* Only an active project can be completed. */}
      {(next || staff.status === "active") && (
        <button
          className="b b--primary"
          type="button"
          disabled={change.busy}
          onClick={() =>
            void change.run(
              () => send(next ? "advance" : "complete"),
              next ? t("edit.advanced", { title: next.title }) : t("edit.completed"),
            )
          }
        >
          {next ? t("edit.advanceTo", { n: pad(current + 1), title: next.title }) : t("edit.complete")}
        </button>
      )}
    </div>
  );
}
