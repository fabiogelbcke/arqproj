import { api, call } from "../api/client";
import posthog from "../posthog";
import { toastError } from "../ui/Toast";

/** "Sair" from a project page's header menu: the session ends and the page shows
 *  as clients see it; a failure says so instead. */
export function signOut(): void {
  void call(api.DELETE("/api/session")).then(() => {
    posthog.reset();
    window.location.reload();
  }, toastError);
}
