// The support code people send us when something fails: the request's ID
// (backend/web/request_id.py), also in the X-Request-ID header and every log line.

/** A request ID: 32 hexadecimal characters (Cloud Run's trace, or our own). */
export const SUPPORT_CODE = /^[0-9a-f]{32}$/i;

/** A support code brought in the address (?ref=…, after a redirect), only when
 *  it is one: anyone can put text in a link, and the page would show it as ours. */
export function supportCode(value: string | null): string | null {
  return value && SUPPORT_CODE.test(value) ? value : null;
}
