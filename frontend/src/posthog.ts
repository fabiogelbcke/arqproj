// Product analytics (A39), in the browser. Signed-in staff are identified by account
// id, role and office, with the key the server gives them for this environment
// (/api/me's `analytics`). A project page's other visitors get PostHog's cookieless
// mode (`startVisitorAnalytics`, from /api/tenant's `analytics`): nothing stored in
// the browser, no person profiles, a daily hash made on PostHog's side. So one build
// serves staging and production, each with its own key or none, and the SDK is
// fetched only once one of them starts. No event carries a project's name: not in
// the page's title, its address (`/casa-silva` becomes `/projeto`, with the
// project's id alongside) or the address's query (`scrub`).
// It is PostHog's self-contained build, which loads no scripts from PostHog's
// servers, so the site's Content Security Policy only lets events out
// (backend/web/painel.py). Until it starts, `capture` and `resetAnalytics` do
// nothing.
import type { CaptureResult, PostHog } from "posthog-js";

import type { Me, Schemas } from "./api/client";

type VisitorAnalytics = Schemas["VisitorAnalyticsOut"] & { slug: string };

let client: PostHog | null = null;
// The project page this is, if any (`analyticsProject`): its address, hidden from
// analytics, and its id, sent instead.
let project: { path: string; id: string | null } | null = null;
const PROJECT_PATH = "/projeto";

/** On a project page (`/casa-silva`): events name the project by its id instead
 *  of its address, which is made from its name. The id comes once the page loads. */
export function analyticsProject(slug: string, id: string | null): void {
  project = { path: `/${slug}`, id };
}

/** A URL as analytics may see it: the project's address replaced and only the
 *  query's `utm_` campaign tags kept. The rest of a query can name a client's file
 *  (`?pasta=Renders&arquivo=Fachada.jpg`) or carry a sign-in link's token, and
 *  masking text and attributes leaves URLs alone. */
export function withoutPrivateParts(value: string): string {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return value; // not a URL
  }
  for (const key of [...url.searchParams.keys()]) {
    if (!key.startsWith("utm_")) url.searchParams.delete(key);
  }
  url.hash = "";
  if (project && url.origin === window.location.origin && url.pathname === project.path) url.pathname = PROJECT_PATH;
  return url.toString();
}

/** Every event on its way out: no page title (a project page's is its name), every
 *  URL through `withoutPrivateParts` ($current_url, $referrer, their $initial_
 *  copies and any others), the project's address hidden from paths, and the
 *  project's id added. */
function scrub(event: CaptureResult | null): CaptureResult | null {
  if (!event) return event;
  delete event.properties.title;
  delete event.properties.$title;
  for (const bag of [event.properties, event.$set, event.$set_once]) {
    if (!bag) continue;
    for (const [key, value] of Object.entries(bag)) {
      if (typeof value !== "string") continue;
      if (/^https?:\/\//.test(value)) bag[key] = withoutPrivateParts(value);
      else if (project && key.endsWith("pathname") && value === project.path) bag[key] = PROJECT_PATH;
    }
  }
  if (project?.id) event.properties.project_id = project.id;
  return event;
}
let loading: Promise<PostHog> | null = null;
// Each sign-out ends a sign-in: a start still loading when it does stops there.
let signIns = 0;

/** Starts PostHog for this signed-in person: their id and role, never their email
 *  or name (Fabio, 26 Oct 2026), and their office as the `tenant` group, as the
 *  server sends them. The SDK is set up once per page; the person is identified
 *  on every sign-in, as signing out and back in keeps the page. */
export async function startAnalytics(me: Me): Promise<void> {
  const analytics = me.analytics;
  if (!analytics) {
    // No key: this server has none, or the session is now an operator's support
    // session (A43), which replaced a staff member's in every tab. Whatever was
    // collecting for them, or still starting, stops.
    resetAnalytics();
    return;
  }
  const mine = signIns;
  loading ??= import("posthog-js/full/no-external").then(({ default: posthog }) => {
    posthog.init(analytics.token, {
      api_host: analytics.host,
      defaults: "2026-01-30",
      person_profiles: "identified_only",
      // Clients' names, project names and files show on these screens: clicks are
      // counted without their text, and screens are never recorded.
      mask_all_text: true,
      mask_all_element_attributes: true,
      disable_session_recording: true,
      disable_surveys: true,
      before_send: scrub,
      // Both send the full address outside `scrub`'s reach: off here, whatever PostHog's settings say.
      capture_heatmaps: false,
      capture_performance: false,
      // Nothing is sent until a sign-in turns it on (below), so a start that a
      // sign-out overtook sends nothing either.
      opt_out_capturing_by_default: true,
      capture_exceptions: {
        capture_unhandled_errors: true,
        capture_unhandled_rejections: true,
        capture_console_errors: false,
      },
    });
    return posthog;
  });
  const posthog = await loading;
  if (mine !== signIns) {
    posthog.opt_out_capturing(); // signed out while it loaded
    return;
  }
  if (posthog.has_opted_out_capturing()) posthog.opt_in_capturing();
  posthog.identify(analytics.user_id, { role: me.role });
  posthog.group("tenant", analytics.tenant_id, { slug: me.tenant_slug });
  client = posthog;
}

/** A project page's visitor who isn't signed-in staff: page views, where they came
 *  from, clicks without their text and the page's named events, counted without
 *  cookies or a person. Not started where the server has no key. */
export async function startVisitorAnalytics(analytics: VisitorAnalytics | null | undefined): Promise<void> {
  if (!analytics || loading) return; // staff analytics, or a visitor's, already started
  const mine = signIns;
  loading = import("posthog-js/full/no-external").then(({ default: posthog }) => {
    posthog.init(analytics.token, {
      api_host: analytics.host,
      defaults: "2026-01-30",
      cookieless_mode: "always",
      person_profiles: "never",
      advanced_disable_flags: true, // no feature flags here: one request fewer
      mask_all_text: true,
      mask_all_element_attributes: true,
      disable_session_recording: true,
      disable_surveys: true,
      before_send: scrub,
      // Both send the full address outside `scrub`'s reach: off here, whatever PostHog's settings say.
      capture_heatmaps: false,
      capture_performance: false,
      capture_exceptions: {
        capture_unhandled_errors: true,
        capture_unhandled_rejections: true,
        capture_console_errors: false,
      },
    });
    posthog.register({ $groups: { tenant: analytics.tenant_id }, tenant: analytics.slug, viewer: "visitor" });
    return posthog;
  });
  const posthog = await loading;
  if (mine === signIns) client = posthog;
}

/** An event, if analytics has started for this person or visitor. */
export function capture(event: string, properties?: Record<string, unknown>): void {
  client?.capture(event, properties);
}

/** Signing out: nothing more is collected (no clicks, pages or errors from the
 *  sign-in screen) until someone signs in again, who starts afresh. */
export function resetAnalytics(): void {
  signIns += 1;
  client?.opt_out_capturing();
  client?.reset();
  client = null;
}
