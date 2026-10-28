// Edit mode: dragging a file card onto another stage, or into a section, moves
// it there, as "Mover para…" does (A34). Our own type on the drag tells a card
// apart from files dragged in from the computer, which upload instead.
import type { DragEvent } from "react";

const FILE_DRAG = "application/x-unio-file";

/** The card being dragged: which file, and where it is now. */
export type DraggedFile = { key: string; name: string; position: number; folder: string | null };

/** Where a card can go: a stage (from 1) and one of its sections, or none. */
export type DropPlace = { position: number; section: string | null };

export const placeId = (place: DropPlace) => `${place.position}/${place.section ?? ""}`;

export function startDrag(event: DragEvent, file: DraggedFile) {
  event.dataTransfer.setData(FILE_DRAG, JSON.stringify(file));
  event.dataTransfer.effectAllowed = "move";
}

const carries = (event: DragEvent) => [...event.dataTransfer.types].includes(FILE_DRAG);

/** A drop target's handlers. Only the innermost target under the pointer takes
 *  the drag (a section, not its stage around it): `onOver` names it, for the
 *  page to mark it, and `onLeave` when the pointer leaves it. */
export function dropTarget(
  place: DropPlace,
  { onOver, onLeave, onDrop }: { onOver: (id: string) => void; onLeave: (id: string) => void; onDrop: (file: DraggedFile, to: DropPlace) => void },
) {
  const id = placeId(place);
  return {
    onDragOver: (event: DragEvent) => {
      if (!carries(event)) return; // files from the computer: the drop areas upload them
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = "move";
      onOver(id);
    },
    onDragLeave: (event: DragEvent) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) onLeave(id);
    },
    onDrop: (event: DragEvent) => {
      if (!carries(event)) return;
      event.preventDefault();
      event.stopPropagation();
      onLeave(id);
      const file = JSON.parse(event.dataTransfer.getData(FILE_DRAG)) as DraggedFile;
      if (file.position !== place.position || file.folder !== place.section) onDrop(file, place);
    },
  };
}
