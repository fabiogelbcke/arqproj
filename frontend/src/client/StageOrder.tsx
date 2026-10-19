// Edit mode: "Reordenar etapas", every stage on one short list (no files) to drag
// into a new order, or move with the arrows (phones, keyboards). Saved at once on
// "Salvar": one change, its folders renumbered; the current stage stays the same.
// Loaded only when staff open it.
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
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

function Row({
  position,
  index,
  title,
  current,
  count,
  onMove,
}: {
  position: number; // the stage's place now, its id here
  index: number; // its place in the new order
  title: string;
  current: boolean;
  count: number;
  onMove: (to: number) => void;
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
    >
      <button
        ref={setActivatorNodeRef}
        type="button"
        className="stage-order__handle"
        aria-label={t("edit.dragStage", { title })}
        {...attributes}
        {...listeners}
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
        {current && <small>{t("edit.currentStage")}</small>}
      </span>
      <button
        type="button"
        className="iconbtn"
        aria-label={t("edit.moveUp", { title })}
        disabled={index === 0}
        onClick={() => onMove(index - 1)}
      >
        ↑
      </button>
      <button
        type="button"
        className="iconbtn"
        aria-label={t("edit.moveDown", { title })}
        disabled={index === count - 1}
        onClick={() => onMove(index + 1)}
      >
        ↓
      </button>
    </li>
  );
}

export default function StageOrder({
  page,
  staff,
  onClose,
  onChanged,
}: {
  page: Page;
  staff: Staff;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const change = useChange(onChanged, false);
  // The stages' present positions, in the order being made.
  const [order, setOrder] = useState(() => page.stages.map((stage) => stage.position));
  const byPosition = new Map(page.stages.map((stage) => [stage.position, stage]));
  const changed = order.some((position, i) => position !== page.stages[i]!.position);
  const sensors = useSensors(
    // A small move before a drag starts, so a tap on the handle stays a tap.
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
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
    if (saved) onClose();
  };
  return (
    <ModalOverlay className="stage-order__overlay" isDismissable isOpen onOpenChange={(open) => !open && onClose()}>
      <Modal className="stage-order__modal">
        <Dialog className="stage-order">
          <Heading slot="title" className="stage-order__heading">
            {t("edit.reorderStages")}
          </Heading>
          <p className="stage-order__hint">{t("edit.reorderHint")}</p>
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={dragged}>
            <SortableContext items={order} strategy={verticalListSortingStrategy}>
              <ol className="stage-order__list">
                {order.map((position, index) => (
                  <Row
                    key={position}
                    position={position}
                    index={index}
                    title={byPosition.get(position)!.title}
                    current={!page.completed && position === page.current_position}
                    count={order.length}
                    onMove={(to) => setOrder((now) => arrayMove(now, index, to))}
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
