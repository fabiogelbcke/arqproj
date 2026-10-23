// Edit mode, part 2: "Editar etapa" (name, notes, remove), "Adicionar etapa",
// "Reordenar etapas", and moving the project along from its stages (finish the
// current one, reopen the last finished, reopen a finished project).
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
    if (!title.trim()) return; // Salvar is off: a stage needs a name
    const renamed = title.trim() !== stage.title;
    // The server keeps notes trimmed and leaves them be when that's all that changed.
    const noted = notes.trim() !== stage.notes;
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
          try {
            await call(
              api.PUT("/api/projects/{project_id}/stages/{position}/notes", {
                params: { path: { ...path(staff), position } },
                body: { row_version: version, notes },
              }),
            );
          } catch (failure) {
            // The rename is in: the page reloads with it, so trying again saves the notes alone.
            if (renamed) onChanged();
            throw failure;
          }
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
            <button className="b b--small b--primary" type="submit" disabled={change.busy || !title.trim()}>
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

// The dropdown's last option: a stage of the office's own, named below it.
const CUSTOM_STAGE = "custom";

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
  const [naming, setNaming] = useState(false); // "Etapa personalizada…" chosen
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
          setNaming(false);
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
        {/* One list: the built-in stages the project doesn't have, then "Etapa
            personalizada…", which asks for its name (Fabio, 23 Oct 2026). */}
        <label className="field">
          <span>{t("edit.stageToAdd")}</span>
          <select
            className="select"
            value={naming ? CUSTOM_STAGE : ""}
            disabled={change.busy}
            onChange={(e) => {
              const value = e.target.value;
              if (value === CUSTOM_STAGE) setNaming(true);
              else if (value) void add({ builtin_key: value });
            }}
          >
            <option value="">{t("edit.chooseStage")}</option>
            {options
              .filter((option) => !used.has(option.title))
              .map((option) => (
                <option key={option.key} value={option.key}>
                  {option.title}
                </option>
              ))}
            <option value={CUSTOM_STAGE}>{t("edit.customStage")}</option>
          </select>
        </label>
        {naming && (
          <form
            className="field"
            onSubmit={(event) => {
              event.preventDefault();
              if (custom.trim()) void add({ title: custom.trim() });
            }}
          >
            <label htmlFor="custom-stage">{t("edit.customStageName")}</label>
            <div className="add-stage__row">
              <TextInput className="input" id="custom-stage" value={custom} maxLength={LIMITS.stageTitle} autoFocus onChange={(e) => setCustom(e.target.value)} />
              <button className="b b--primary" type="submit" disabled={change.busy || !custom.trim()}>
                {t("edit.add")}
              </button>
            </div>
          </form>
        )}
        <p className="hint">{t("edit.addStageHint")}</p>
        <div className="editor__actions">
          <button
            className="b"
            type="button"
            onClick={() => {
              setOpen(false);
              setNaming(false);
            }}
          >
            {t("projectSettings.cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}

/** "Reordenar etapas": every stage on one list to drag into a new order. Beside
 *  "Adicionar etapa", at the end of the stages. */
export function ReorderStages({
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
  const [ordering, setOrdering] = useState(false);
  if (page.stages.length < 2) return null;
  return (
    <>
      <button className="b b--small" type="button" disabled={locked} onClick={() => setOrdering(true)}>
        {t("edit.reorderStages")}
      </button>
      {ordering && (
        <Suspense fallback={null}>
          <StageOrder page={page} staff={staff} onClose={() => setOrdering(false)} onChanged={onChanged} onReordered={onReordered} />
        </Suspense>
      )}
    </>
  );
}

/** Moving the project along, from its stages (Fabio, 22 Oct 2026; it was a rail
 *  of its own): the current stage's "Marcar etapa como concluída" (on the last
 *  stage it completes the project), "Reabrir etapa" on the one finished last,
 *  and "Reabrir projeto" on a finished project's last stage. Each asks first,
 *  except reopening a finished project. Nothing on the other stages. */
export function StageProgress({
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
  const change = useChange(onChanged, locked);
  const [confirming, setConfirming] = useState<"advance" | "complete" | "back" | null>(null);
  const send = (action: "advance" | "back" | "complete" | "reopen") =>
    call(
      api.POST("/api/projects/{project_id}/progress", {
        params: { path: path(staff) },
        body: { row_version: staff.row_version, action },
      }),
    );
  const last = index === page.stages.length - 1;
  if (page.completed)
    return last ? (
      <button
        className="b b--small"
        type="button"
        disabled={change.busy}
        onClick={() => void change.run(() => send("reopen"), t("edit.reopened"))}
      >
        {t("edit.reopenProject")}
      </button>
    ) : null;
  const current = Math.max(1, page.current_position ?? 1);
  const here = page.stages[current - 1];
  const next = page.stages[current];
  const previous = page.stages[current - 2];
  const isCurrent = index === current - 1;
  const isJustDone = index === current - 2;
  // Only an active project can be completed.
  if (!(isCurrent && (next || staff.status === "active")) && !isJustDone) return null;
  const confirmations = {
    advance: {
      title: t("edit.completeStageAsk", { title: here?.title }),
      text: t("edit.completeStageMeans", { from: here?.title, title: next?.title }),
      confirm: t("edit.completeStageConfirm"),
      done: t("edit.advanced", { title: next?.title }),
    },
    complete: {
      title: t("edit.completeAsk"),
      text: t("edit.completeMeans"),
      confirm: t("edit.complete"),
      done: t("edit.completed"),
    },
    back: {
      title: t("edit.reopenStageAsk", { title: previous?.title }),
      text: t("edit.backMeans", { title: previous?.title }),
      confirm: t("edit.reopenStage"),
      done: undefined,
    },
  };
  return (
    <>
      {isCurrent ? (
        <button
          className="b b--small b--primary stage-progress"
          type="button"
          data-tour="stage"
          disabled={change.busy}
          onClick={() => setConfirming(next ? "advance" : "complete")}
        >
          {t("edit.completeStage")}
        </button>
      ) : (
        <button className="b b--small stage-progress" type="button" disabled={change.busy} onClick={() => setConfirming("back")}>
          {t("edit.reopenStage")}
        </button>
      )}
      {confirming && (
        <ConfirmDialog
          {...confirmations[confirming]}
          // Finishing a stage or the project emails whoever gets the project's updates (A32).
          note={
            confirming !== "back" && staff.recipients?.some((recipient) => recipient.subscribed)
              ? t("edit.clientsNotified")
              : undefined
          }
          busy={change.busy}
          onCancel={() => setConfirming(null)}
          onConfirm={() =>
            void change.run(() => send(confirming), confirmations[confirming].done).then(() => setConfirming(null))
          }
        />
      )}
    </>
  );
}
