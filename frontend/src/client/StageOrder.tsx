// Edit mode: "Reordenar etapas", every stage on one short list (no files) to drag
// into a new order: by the whole row, or by its handle (with a keyboard: space,
// the arrows, space). On a phone the row lifts only after a press-and-hold, so a
// swipe scrolls and a tap moves nothing; the handle drags at once (Fabio, 25 Oct
// 2026: people didn't find the handle). Saved at once on "Salvar": one change,
// its folders renumbered; each stage keeps its completion. Loaded only when staff
// open it.
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useState } from "react";
import { Dialog, Heading, Modal, ModalOverlay } from "react-aria-components";
import { useTranslation } from "react-i18next";

import { api, call } from "../api/client";
import type { Page } from "./format";
import { useChange } from "./StageEditing";

type Staff = NonNullable<Page["staff"]>;
const pad = (n: number) => String(n).padStart(2, "0");

/** A press-and-hold on a phone before the row lifts: long enough that a swipe
 *  to scroll or a tap never moves a stage. */
const HOLD_MS = 300;
const onHandle = (event: Event) => (event.target as Element | null)?.closest?.("[data-drag-handle]") != null;

/** The handle: a drag starts at once, a phone's finger too (no hold). */
class HandleSensor extends PointerSensor {
  static activators: typeof PointerSensor.activators = [
    {
      eventName: "onPointerDown",
      handler: (event, options) =>
        onHandle(event.nativeEvent) && PointerSensor.activators[0]!.handler(event, options),
    },
  ];
}

/** The rest of the row, with a mouse or pen: a small move starts it. */
class RowMouseSensor extends PointerSensor {
  static activators: typeof PointerSensor.activators = [
    {
      eventName: "onPointerDown",
      handler: (event, options) =>
        event.nativeEvent.pointerType !== "touch" &&
        !onHandle(event.nativeEvent) &&
        PointerSensor.activators[0]!.handler(event, options),
    },
  ];
}

/** The rest of the row, with a finger: only after holding it still. */
class RowTouchSensor extends TouchSensor {
  static activators: typeof TouchSensor.activators = [
    {
      eventName: "onTouchStart",
      handler: (event, options) =>
        !onHandle(event.nativeEvent) && TouchSensor.activators[0]!.handler(event, options),
    },
  ];
}

function Row({
  position,
  index,
  title,
  done,
}: {
  position: number; // the stage's place now, its id here
  index: number; // its place in the new order
  title: string;
  done: boolean;
}) {
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: position,
  });
  return (
    <li
      ref={setNodeRef}
      className={`stage-order__row${isDragging ? " is-dragging" : ""}`}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      // The whole row drags; the keyboard goes through the handle, focused.
      {...listeners}
    >
      <button
        ref={setActivatorNodeRef}
        type="button"
        className="stage-order__handle"
        data-drag-handle
        aria-label={t("edit.dragStage", { title })}
        {...attributes}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="9" cy="6" r="1.4" /><circle cx="15" cy="6" r="1.4" />
          <circle cx="9" cy="12" r="1.4" /><circle cx="15" cy="12" r="1.4" />
          <circle cx="9" cy="18" r="1.4" /><circle cx="15" cy="18" r="1.4" />
        </svg>
      </button>
      <span className="stage-order__n">{pad(index + 1)}</span>
      <span className="stage-order__title">
        {title}
        {done && <small>{t("page.stageDone")}</small>}
      </span>
    </li>
  );
}

export default function StageOrder({
  page,
  staff,
  onClose,
  onChanged,
  onReordered,
}: {
  page: Page;
  staff: Staff;
  onClose: () => void;
  onChanged: () => void;
  onReordered?: (order: number[]) => void; // the old positions, in their new order
}) {
  const { t } = useTranslation();
  const change = useChange(onChanged, false);
  // The stages' present positions, in the order being made.
  const [order, setOrder] = useState(() => page.stages.map((stage) => stage.position));
  const byPosition = new Map(page.stages.map((stage) => [stage.position, stage]));
  const changed = order.some((position, i) => position !== page.stages[i]!.position);
  const sensors = useSensors(
    useSensor(HandleSensor),
    // A small move before a drag starts, so a click on the row stays a click.
    useSensor(RowMouseSensor, { activationConstraint: { distance: 4 } }),
    // Still for a moment (a little wobble allowed): a swipe scrolls instead.
    useSensor(RowTouchSensor, { activationConstraint: { delay: HOLD_MS, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  // The hold has worked: a short buzz on phones that can, as the row lifts.
  const started = ({ activatorEvent }: DragStartEvent) => {
    if (typeof TouchEvent !== "undefined" && activatorEvent instanceof TouchEvent) navigator.vibrate?.(10);
  };
  const dragged = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    setOrder((now) => arrayMove(now, now.indexOf(Number(active.id)), now.indexOf(Number(over.id))));
  };
  const save = async () => {
    const saved = await change.run(
      () =>
        call(
          api.PUT("/api/projects/{project_id}/stages/order", {
            params: { path: { project_id: staff.project_id } },
            body: { row_version: staff.row_version, order },
          }),
        ),
      t("edit.orderSaved"),
    );
    if (saved) {
      onReordered?.(order);
      onClose();
    }
  };
  return (
    <ModalOverlay className="stage-order__overlay" isDismissable isOpen onOpenChange={(open) => !open && onClose()}>
      <Modal className="stage-order__modal">
        <Dialog className="stage-order">
          <Heading slot="title" className="stage-order__heading">
            {t("edit.reorderStages")}
          </Heading>
          <p className="stage-order__hint">{t("edit.reorderHint")}</p>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={started}
            onDragEnd={dragged}
            // Read out on a handle, in the office's language: how to move it by keyboard.
            accessibility={{ screenReaderInstructions: { draggable: t("edit.reorderKeys") } }}
          >
            <SortableContext items={order} strategy={verticalListSortingStrategy}>
              <ol className="stage-order__list">
                {order.map((position, index) => (
                  <Row
                    key={position}
                    position={position}
                    index={index}
                    title={byPosition.get(position)!.title}
                    done={byPosition.get(position)!.completed}
                  />
                ))}
              </ol>
            </SortableContext>
          </DndContext>
          <div className="editor__actions">
            <button className="b b--ghost" type="button" onClick={onClose}>
              {t("projectSettings.cancel")}
            </button>
            <button className="b b--primary" type="button" disabled={!changed || change.busy} onClick={() => void save()}>
              {t("projectSettings.save")}
            </button>
          </div>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
