import i18next from "i18next";

import { toast, toastProblem } from "./Toast";

/** "Copiar link": puts the text on the clipboard and says how it went, the same
 *  way everywhere. Copied: "Link copiado." Not copied (a browser without the
 *  clipboard, as on a page not served over HTTPS, or one that refuses it): a
 *  problem toast, never a ✓, by default giving the link to copy by hand; where
 *  the link is on screen already, `failed` can say to select it there instead.
 *  Resolves to whether it was copied. */
export async function copyText(text: string, messages: { copied?: string; failed?: string } = {}): Promise<boolean> {
  const copied = await (navigator.clipboard?.writeText(text).then(
    () => true,
    () => false,
  ) ?? false);
  if (copied) toast(messages.copied ?? i18next.t("copy.copied"));
  else toastProblem(messages.failed ?? i18next.t("copy.failedLink", { link: text }));
  return copied;
}
