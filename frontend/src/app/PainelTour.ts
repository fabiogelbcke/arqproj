// The painel's tour (Driver.js), from the account menu or the phone's drawer
// only: Primeiros passos, "Novo projeto", a project's card, Configurações; its last step opens the
// example project, whose own tour then starts (plan section 16). A step whose
// part isn't on the screen (no projects yet, the menu on a phone) is left out.
// It stores nothing. Loaded only when it runs.
import { driver, type DriveStep } from "driver.js";
import type { TFunction } from "i18next";

import { EXAMPLE_SLUG } from "../client/example/address";
import "../ui/tour.css";

const at = (name: string) => `[data-tour="${name}"]`;

export function startPainelTour({ t, openExample }: { t: TFunction; openExample?: () => void }) {
  const visible = (selector: string) => {
    const element = document.querySelector<HTMLElement>(selector);
    return !!element && element.getClientRects().length > 0;
  };
  const step = (name: string): DriveStep => ({
    element: at(name),
    popover: { title: t(`painelTour.${name}Title`), description: t(`painelTour.${name}`) },
  });
  const go = openExample ?? (() => window.location.assign(`/${EXAMPLE_SLUG}`));
  const steps: DriveStep[] = [
    ...["first-steps", "new-project", "project-card", "settings"].map(step).filter((s) => visible(s.element as string)),
    {
      // No element: the popover in the middle of the screen.
      popover: {
        title: t("painelTour.exampleTitle"),
        description: t("painelTour.example"),
        doneBtnText: t("painelTour.exampleAction"),
        onNextClick: () => {
          tour.destroy();
          go();
        },
      },
    },
  ];
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
  });
  tour.drive();
}
