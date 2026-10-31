// The example project's "explore" tour (plan section 16): where things appear for
// the client, in the client's view. It starts on every visit, can be skipped (×,
// Esc, "Pular"), and stores nothing. A step whose part isn't on the page (on a
// phone, say) is left out. The setup tour for real projects is ../Tour.ts.
import { driver, type DriveStep } from "driver.js";
import "../../ui/tour.css";
import type { TFunction } from "i18next";

let running = false; // one tour at a time, however often it is asked for

const shown = (selector: string) => {
  const element = document.querySelector(selector);
  return element !== null && !element.closest(".mobile-view-hidden, [hidden]");
};

/** Until the current stage's files are on the page: at most 3 s. */
async function filesShown(): Promise<void> {
  for (let i = 0; i < 60 && !document.querySelector(".stage.is-expanded .file"); i++)
    await new Promise((resolve) => setTimeout(resolve, 50));
}

export async function startExploreTour(t: TFunction) {
  if (running) return;
  running = true;
  // The client's view: back from edit mode, if staff were trying it.
  if (document.querySelector(".client.editing"))
    document.querySelector<HTMLButtonElement>('[data-tour="mode"] button[aria-pressed="false"]')?.click();
  await filesShown();
  const step = (element: string | undefined, key: string): DriveStep => ({
    element,
    popover: { title: t(`exploreTour.${key}Title`), description: t(`exploreTour.${key}`) },
  });
  const back = '.dock a[href="/painel/"]'; // staff: the way back to Primeiros passos
  const steps = [
    step(".project-heading", "title"),
    step(".project-layout__desc .desc", "description"),
    step(".project-layout__side .details-list", "details"),
    step(".mobile-project-summary", "summary"), // phones: the description and details
    step(".meeting", "meeting"),
    step(".stage-steps", "timeline"),
    step(".stage.is-expanded .files", "files"),
    step(".client-notifications", "updates"),
    step('[data-tour="mode"]', "edit"),
  ].filter((s) => shown(s.element as string));
  // Staff end on their way back to Primeiros passos; a visitor (from Unio's home)
  // has no painel to go to.
  if (shown(back)) steps.push(step(back, "end"));
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
    // "Pular", beside Voltar/Próximo, on every step but the last.
    onPopoverRender: (popover, { state }) => {
      if (state.activeIndex === steps.length - 1) return;
      const skip = document.createElement("button");
      skip.type = "button";
      skip.className = "explore-skip";
      skip.textContent = t("exploreTour.skip");
      skip.addEventListener("click", () => tour.destroy());
      popover.footer.prepend(skip);
    },
    // Every way out comes here first (as in ../Tour.ts); nothing is stored.
    onDestroyStarted: () => {
      running = false;
      tour.destroy();
    },
  });
  tour.drive();
}
