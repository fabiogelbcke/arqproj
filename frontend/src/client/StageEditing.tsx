// Edit mode, part 2: "Editar etapa" (name, notes, remove), the prototype's
// "Adicionar etapa" and its progress rail (advance, back, complete, reopen).
// Every change carries the page's row version; folders follow in Drive.
import { Suspense, lazy, useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api, call, type Schemas } from "../api/client";
import { LIMITS } from "../api/limits";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { TextInput } from "../ui/TextInput";
import { toast, toastError } from "../ui/Toast";
import type { Page } from "./format";

// The reorder list (and its drag library) loads only when staff open it.
const StageOrder = lazy(() => import("./StageOrder"));

type Staff = NonNullable<Page["staff"]>;
const pad = (n: number) => String(n).padStart(2, "0");

/** `locked`: a change was saved and the page hasn't reloaded yet, so another
 * click would carry the old row version and be refused as "changed meanwhile". */
export function useChange(onChanged: () => void, locked: boolean) {
  const { t } = useTranslation();
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
        toastError(failure);
        return false;
      } finally {
        setBusy(false);
      }
    },
  };
}

const path = (staff: Staff) => ({ project_id: staff.project_id });

/** A stage's parts in "Editar etapa", for the stage to lay out where they belong:
 *  the name where its title was, Cancelar and Salvar beside it (they save the
 *  whole stage), the notes above its files, and "Remover etapa" at its end. */
export type StageEditParts = { name: ReactNode; actions: ReactNode; notes: ReactNode; remove: ReactNode };

/** "Editar etapa": Salvar saves the name and the notes (files save as they go). The
 *  form takes no room of its own, so the stage keeps its layout. */
export function StageEditForm({
  page,
  staff,
  index,
  onDone,
  onChanged,
  locked = false,
  layout,
}: {
  page: Page;
  staff: Staff;
  index: number;
  onDone: (removed?: boolean) => void;
  onChanged: () => void;
  locked?: boolean;
  layout: (parts: StageEditParts) => ReactNode;
}) {
  const { t } = useTranslation();
  const stage = page.stages[index]!;
  const position = stage.position;
  const change = useChange(onChanged, locked);
  const [title, setTitle] = useState(stage.title);
  const [notes, setNotes] = useState(stage.notes);
  const [removing, setRemoving] = useState(false);
  const save = () => {
    const renamed = title.trim() !== "" && title.trim() !== stage.title;
    const noted = notes !== stage.notes;
    if (!renamed && !noted) return onDone();
    void change
      .run(async () => {
        // Each change moves the row version on by one, so the notes, saved
        // after a rename, carry the next one.
        let version = staff.row_version;
        if (renamed) {
          await call(
            api.PATCH("/api/projects/{project_id}/stages/{position}", {
              params: { path: { ...path(staff), position } },
              body: { row_version: version, title: title.trim() },
            }),
          );
          version += 1;
        }
        if (noted)
          await call(
            api.PUT("/api/projects/{project_id}/stages/{position}/notes", {
              params: { path: { ...path(staff), position } },
              body: { row_version: version, notes },
            }),
          );
      })
      .then((ok) => ok && onDone());
  };
  const remove = () =>
    change
      .run(
        () =>
          call(
            api.DELETE("/api/projects/{project_id}/stages/{position}", {
              params: { path: { ...path(staff), position }, query: { row_version: staff.row_version } },
            }),
          ),
        t("edit.stageRemoved", { title: stage.title }),
      )
      .then((ok) => {
        setRemoving(false);
        if (ok) onDone(true); // this row shows the next stage now
      });
  return (
    <form
      className="stage-edit"
      aria-label={t("edit.editStageOf", { title: stage.title })}
      onSubmit={(event) => {
        event.preventDefault();
        save();
      }}
      // Escape leaves it (the remove question keeps its own Escape to itself).
      onKeyDown={(event) => event.key === "Escape" && onDone()}
    >
      {layout({
        name: (
          <div className="stage-name-field">
            <TextInput
              aria-label={t("edit.stageName")}
              value={title}
              maxLength={LIMITS.stageTitle}
              required
              autoFocus
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
        ),
        actions: (
          <div className="stage-edit__actions">
            <button className="b b--small" type="button" onClick={() => onDone()}>
              {t("projectSettings.cancel")}
            </button>
            <button className="b b--small b--primary" type="submit" disabled={change.busy}>
              {t("projectSettings.save")}
            </button>
          </div>
        ),
        notes: (
          <div className="field stage-edit__notes">
            <label htmlFor={`ed-notes-${index}`}>{t("edit.notes")}</label>
            <TextInput
              className="input"
              id={`ed-notes-${index}`}
              value={notes}
              maxLength={LIMITS.stageNotes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t("edit.notesPlaceholder")}
            />
          </div>
        ),
        remove: (
          <div className="stage-edit__remove">
            <button className="b b--ghost b--danger b--small" type="button" disabled={change.busy} onClick={() => setRemoving(true)}>
              {t("edit.removeStageShort")}
            </button>
            {removing && (
              <ConfirmDialog
                title={t("edit.removeStage", { title: stage.title })}
                text={t("edit.removeStageConfirm", { title: stage.title })}
                confirm={t("edit.remove")}
                danger
                busy={change.busy}
                onCancel={() => setRemoving(false)}
                onConfirm={() => void remove()}
              />
            )}
          </div>
        ),
      })}
    </form>
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
            <TextInput className="input" id="custom-stage" value={custom} maxLength={LIMITS.stageTitle} onChange={(e) => setCustom(e.target.value)} />
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
  onReordered,
  locked = false,
}: {
  page: Page;
  staff: Staff;
  onChanged: () => void;
  onReordered?: (order: number[]) => void;
  locked?: boolean;
}) {
  const { t } = useTranslation();
  const change = useChange(onChanged, locked);
  const [ordering, setOrdering] = useState(false);
  // Advancing, completing and going back ask first; reopening doesn't.
  const [confirming, setConfirming] = useState<"advance" | "complete" | "back" | null>(null);
  // "Reordenar etapas": every stage on one list to drag into a new order.
  const reorder = page.stages.length > 1 && (
    <>
      <button className="b b--ghost b--small" type="button" disabled={change.busy} onClick={() => setOrdering(true)}>
        {t("edit.reorderStages")}
      </button>
      {ordering && (
        <Suspense fallback={null}>
          <StageOrder
            page={page}
            staff={staff}
            onClose={() => setOrdering(false)}
            onChanged={onChanged}
            onReordered={onReordered}
          />
        </Suspense>
      )}
    </>
  );
  const send = (action: "advance" | "back" | "complete" | "reopen", version = staff.row_version) =>
    call(
      api.POST("/api/projects/{project_id}/progress", {
        params: { path: path(staff) },
        body: { row_version: version, action },
      }),
    );
  if (!page.stages.length) return <div className="rail" data-tour="stage"><div className="rail__now"><p>{t("edit.noStagesYet")}</p></div></div>;
  if (page.completed)
    return (
      <div className="rail" data-tour="stage">
        <div className="rail__now">
          <span className="big">✓</span>
          <p>
            {t("page.allDone")}
            <small>{t("edit.allDoneNote")}</small>
          </p>
        </div>
        {reorder}
        <button className="b b--small" type="button" disabled={change.busy} onClick={() => void change.run(() => send("reopen"), t("edit.reopened"))}>
          {t("edit.reopen")}
        </button>
      </div>
    );
  const current = Math.max(1, page.current_position ?? 1);
  const here = page.stages[current - 1];
  const next = page.stages[current];
  const previous = page.stages[current - 2];
  const confirmations = {
    advance: {
      title: t("edit.advanceAsk", { title: next?.title }),
      text: t("edit.advanceMeans", { from: here?.title, title: next?.title }),
      confirm: t("edit.advance"),
      done: t("edit.advanced", { title: next?.title }),
    },
    complete: {
      title: t("edit.completeAsk"),
      text: t("edit.completeMeans"),
      confirm: t("edit.complete"),
      done: t("edit.completed"),
    },
    back: {
      title: t("edit.backAsk", { title: previous?.title }),
      text: t("edit.backMeans", { title: previous?.title }),
      confirm: t("edit.back"),
      done: undefined,
    },
  };
  return (
    <div className="rail" data-tour="stage">
      <div className="rail__now">
        <span className="big tnum">{pad(current)}</span>
        <p>
          <small className="rail__label">{t("edit.currentStage")}</small>
          {here?.title}
        </p>
      </div>
      {reorder}
      {current > 1 && (
        <button className="b b--ghost b--small" type="button" disabled={change.busy} onClick={() => setConfirming("back")}>
          {t("edit.back")}
        </button>
      )}
      {/* Only an active project can be completed. */}
      {(next || staff.status === "active") && (
        <button
          className="b b--primary"
          type="button"
          disabled={change.busy}
          onClick={() => setConfirming(next ? "advance" : "complete")}
        >
          {next ? t("edit.advanceTo", { n: pad(current + 1), title: next.title }) : t("edit.complete")}
        </button>
      )}
      {confirming && (
        <ConfirmDialog
          {...confirmations[confirming]}
          // Advancing and completing email whoever gets the project's updates (A32).
          note={
            confirming !== "back" && staff.recipients?.some((recipient) => recipient.subscribed)
              ? t("edit.clientsNotified")
              : undefined
          }
          busy={change.busy}
          onCancel={() => setConfirming(null)}
          onConfirm={() => void change.run(() => send(confirming), confirmations[confirming].done).then(() => setConfirming(null))}
        />
      )}
    </div>
  );
}
