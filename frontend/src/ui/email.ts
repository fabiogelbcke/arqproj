// Email addresses as people type them: tidied, checked with the server's rule
// (backend/identity/emails.py), and a likely typo in the domain pointed out
// ("gmial.com" → "gmail.com"), so a misspelt address is caught while it's typed
// rather than when an email bounces.
import { LIMITS } from "../api/limits";

const LOCAL = /^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*$/;
const LABEL = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/;

/** Trimmed and lowercase, without what comes along when one is pasted from an
 *  email program ("<ana@x.com>", "mailto:ana@x.com"). */
export function tidyEmail(raw: string): string {
  return raw
    .trim()
    .replace(/^mailto:/i, "")
    .replace(/^<(.*)>$/, "$1")
    .trim()
    .toLowerCase();
}

/** The server's rule: a name, "@", and a domain of at least two parts ending in
 *  letters ("ana@escritorio.com.br"), with no spaces or doubled dots. */
export function isEmail(email: string): boolean {
  if (email.length > LIMITS.email) return false;
  const at = email.lastIndexOf("@");
  if (at <= 0 || at > 64) return false;
  const local = email.slice(0, at);
  const labels = email.slice(at + 1).split(".");
  return (
    LOCAL.test(local) &&
    labels.length >= 2 &&
    labels.every((label) => label.length <= 63 && LABEL.test(label)) &&
    /^[a-z]{2,}$/.test(labels.at(-1)!)
  );
}

// The domains most of an office's clients use, in Brazil and elsewhere.
const COMMON = [
  "gmail.com",
  "hotmail.com",
  "hotmail.com.br",
  "outlook.com",
  "outlook.com.br",
  "live.com",
  "yahoo.com",
  "yahoo.com.br",
  "icloud.com",
  "me.com",
  "uol.com.br",
  "bol.com.br",
  "terra.com.br",
  "ig.com.br",
  "globo.com",
  "msn.com",
  "mail.com",
  "aol.com",
  "protonmail.com",
];
// Endings typed for ".com" or ".com.br".
const ENDINGS: Record<string, string> = {
  con: "com",
  cmo: "com",
  ocm: "com",
  vom: "com",
  xom: "com",
  comm: "com",
  coom: "com",
  cpm: "com",
  "com.bt": "com.br",
  "com.vr": "com.br",
  "com.be": "com.br",
  "con.br": "com.br",
  "cpm.br": "com.br",
};

/** Edits (a letter added, removed, changed, or two swapped) from one word to another. */
function distance(a: string, b: string): number {
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array<number>(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0]![j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i]![j] = Math.min(d[i - 1]![j]! + 1, d[i]![j - 1]! + 1, d[i - 1]![j - 1]! + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1])
        d[i]![j] = Math.min(d[i]![j]!, d[i - 2]![j - 2]! + 1);
    }
  return d[a.length]![b.length]!;
}

/** The address the person probably meant, when its domain looks like a typo of a
 *  common one or of ".com"/".com.br"; otherwise null. */
export function emailSuggestion(email: string): string | null {
  const at = email.lastIndexOf("@");
  if (at <= 0) return null;
  const local = email.slice(0, at);
  const domain = email.slice(at + 1);
  if (!domain || COMMON.includes(domain)) return null;
  let best: string | null = null;
  let bestDistance = Infinity;
  for (const common of COMMON) {
    const d = distance(domain, common);
    // One slip for a short name; two for a longer one ("hotmial.com.br").
    if (d < bestDistance && d <= (common.length > 10 ? 2 : 1)) [best, bestDistance] = [common, d];
  }
  if (!best) {
    for (const [typed, meant] of Object.entries(ENDINGS))
      if (domain.endsWith(`.${typed}`)) {
        best = domain.slice(0, -typed.length) + meant;
        break;
      }
  }
  return best ? `${local}@${best}` : null;
}

/** Several addresses typed or pasted at once, split on commas, semicolons, spaces
 *  or new lines; each tidied, the empty ones dropped. */
export function splitEmails(text: string): string[] {
  return text
    .split(/[,;\s]+/)
    .map(tidyEmail)
    .filter(Boolean);
}
