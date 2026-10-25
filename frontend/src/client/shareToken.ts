/** `/share/AbC…` (A37): the link's token, or null for any other address. Apart
 *  from the supplier's page, so the page's bundle can tell without loading it. */
export function shareToken(path: string): string | null {
  const found = /^\/share\/([A-Za-z0-9_-]+)\/?$/.exec(path);
  return found ? found[1]! : null;
}
