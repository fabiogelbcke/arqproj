// Cloud Logging's console, opened on this service's logs with a search filled in:
// the operator reads the detail there, signed in with their own Google account
// (the app itself is given no access to the logs).

export type LogsTarget = { project: string; service: string };

function url({ project, service }: LogsTarget, query: string): string {
  const full = `resource.type="cloud_run_revision"\nresource.labels.service_name="${service}"\n${query}`;
  return `https://console.cloud.google.com/logs/query;query=${encodeURIComponent(full)};duration=P7D?project=${encodeURIComponent(project)}`;
}

/** A support code from an error screen: the request ID every log line of that
 *  request carries (backend/web/request_id.py), also its trace. */
export function supportCodeUrl(target: LogsTarget, code: string): string {
  const id = code.trim().toLowerCase();
  return url(target, `("${id}" OR trace="projects/${target.project}/traces/${id}")`);
}

/** An office's errors. Lines name their office by slug ("tenant=alinea",
 *  "… for alinea") or, in uploads and emails, by its ID: either matches. */
export function officeErrorsUrl(target: LogsTarget, office: { slug: string; id: string }): string {
  return url(target, `severity>=ERROR\n("${office.slug}" OR "${office.id}")`);
}

/** A request ID: 32 hexadecimal characters (Cloud Run's trace, or our own). */
export const SUPPORT_CODE = /^[0-9a-f]{32}$/i;
