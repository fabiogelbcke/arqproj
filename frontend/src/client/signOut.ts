import { api, call } from "../api/client";
import { toastError } from "../ui/Toast";

/** "Sair" from a project page's header menu: the session ends and the page shows
 *  as clients see it; a failure says so instead. */
export function signOut(): void {
  void call(api.DELETE("/api/session")).then(() => window.location.reload(), toastError);
}
