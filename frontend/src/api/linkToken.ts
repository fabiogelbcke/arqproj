/** A link's token is in the fragment (#token=…), which browsers never send to
 * servers. Read it once, then take it out of the address bar and history. */
export function takeToken(): string {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
  if (token) window.history.replaceState(window.history.state, "", window.location.pathname);
  return token;
}
