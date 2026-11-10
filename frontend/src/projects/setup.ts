// A new project's setup steps (trial, Fabio, 1 Nov 2026), without their styles:
// the client page's own bundle reads the address's query from here.

/** The page address's query that opens a new project's setup steps. */
export const SETUP_PARAM = "configurar";

/** A new project's personalisation on its page, after creating it in the painel
 *  (which is quick on purpose, so it isn't counted as a step). No cover step
 *  (3 Nov 2026): a new project already has a stock photo, and an office may have
 *  no photos of its own yet; the cover is changed from the "⋯" or edit mode. */
export const SETUP_STEPS = ["stages", "details", "emails"] as const;
export type SetupStep = (typeof SETUP_STEPS)[number];
