// The project page's guided tour for staff (Driver.js), in edit mode: the
// view/edit switch, the pencils, the current stage, uploading files and the
// page's link. Once per account (POST /api/me/tour-seen when it ends, however it
// ends); "Ajuda" in the account menu replays it. A step whose
// part isn't on this page (no stages yet, say) is left out. Loaded only when it runs.
import { driver, type DriveStep } from "driver.js";
import "../ui/tour.css";
import type { TFunction } from "i18next";

import { api, call } from "../api/client";

const at = (name: string) => `[data-tour="${name}"]`;

// One tour at a time, however often the page asks (it may mount again while
// loading): taken at once, before waiting for edit mode.
let running = false;

/** Until the edit mode's parts, each loaded on demand and separately, are on the
 *  page: the stage controls and, with a stage open, its upload area. At
 *  most 3 s, then the tour goes on with what is there. */
async function editingShown(): Promise<void> {
  const ready = () =>
    document.querySelector(at("stage")) &&
    (document.querySelector(at("upload")) || !document.querySelector(".stage.is-expanded"));
  for (let i = 0; i < 60 && !ready(); i++) await new Promise((resolve) => setTimeout(resolve, 50));
}

export async function startTour({
  t,
  enterEdit,
  markSeen,
}: {
  t: TFunction;
  enterEdit: () => void;
  markSeen: boolean;
}) {
  if (running) return;
  running = true;
  // In edit mode from the start, so every step's part is on the page; the first
  // step explains the switch between it and the client's view.
  enterEdit();
  await editingShown();
  const step = (element: string, key: string): DriveStep => ({
    element,
    popover: { title: t(`tour.${key}Title`), description: t(`tour.${key}`) },
  });
  const steps = [
    step(at("mode"), "mode"),
    step(".project-heading .editbtn", "pencils"),
    step(at("stage"), "stage"),
    step(at("upload"), "upload"),
    step(at("link"), "link"),
  ].filter((s) => document.querySelector(s.element as string)); // e.g. no stages yet
  const tour = driver({
    showProgress: true,
    allowClose: true,
    overlayOpacity: 0.55,
    stagePadding: 6,
    stageRadius: 4,
    nextBtnText: t("tour.next"),
    prevBtnText: t("tour.back"),
    doneBtnText: t("tour.done"),
    progressText: t("tour.progress", { current: "{{current}}", total: "{{total}}" }),
    steps,
    // Every way out (Concluir, ×, Esc, a click outside) comes here first; Driver.js
    // leaves the closing to us. (Its onDestroyed isn't called on every way out.)
    onDestroyStarted: () => {
      running = false;
      // Finished or closed: not offered again to this account, on any device.
      if (markSeen) void call(api.POST("/api/me/tour-seen")).catch(() => undefined);
      tour.destroy();
    },
  });
  tour.drive();
}
