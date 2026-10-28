// Product analytics (A39), in the browser. Signed-in staff are identified by
// account id, role and office, with the key the server gives them for this
// environment (/api/me's `analytics`). A project page's other visitors get
// PostHog's cookieless mode (`startVisitorAnalytics`, from /api/tenant's
// `analytics`): nothing stored in the browser, no person profiles, a daily hash
// made on PostHog's side. So one build serves staging and production, each with
// its own key or none, and the SDK is fetched only once one of them starts.
// It is PostHog's self-contained build, which loads no scripts from PostHog's
// servers, so the site's Content Security Policy only lets events out
// (backend/web/painel.py). Until it starts, `capture` and `resetAnalytics` do
// nothing.
import type { PostHog } from "posthog-js";

import type { Me, Schemas } from "./api/client";

type VisitorAnalytics = Schemas["VisitorAnalyticsOut"] & { slug: string };

let client: PostHog | null = null;
let loading: Promise<PostHog> | null = null;
// Each sign-out ends a sign-in: a start still loading when it does stops there.
let signIns = 0;

/** Starts PostHog for this signed-in person: their id and role, never their email
 *  or name (Fabio, 26 Oct 2026), and their office as the `tenant` group, as the
 *  server sends them. The SDK is set up once per page; the person is identified
 *  on every sign-in, as signing out and back in keeps the page. */
export async function startAnalytics(me: Me): Promise<void> {
  const analytics = me.analytics;
  if (!analytics) return;
  const mine = signIns;
  loading ??= import("posthog-js/full/no-external").then(
    ({ default: posthog }) => {
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
    },
  );
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

/** A project page's visitor who isn't signed-in staff: page views, where they
 *  came from, clicks without their text and the page's named events, counted
 *  without cookies or a person. Not started where the server has no key. */
export async function startVisitorAnalytics(
  analytics: VisitorAnalytics | null | undefined,
): Promise<void> {
  if (!analytics || loading) return; // staff analytics, or a visitor's, already started
  const mine = signIns;
  loading = import("posthog-js/full/no-external").then(
    ({ default: posthog }) => {
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
        capture_exceptions: {
          capture_unhandled_errors: true,
          capture_unhandled_rejections: true,
          capture_console_errors: false,
        },
      });
      posthog.register({
        $groups: { tenant: analytics.tenant_id },
        tenant: analytics.slug,
        viewer: "visitor",
      });
      return posthog;
    },
  );
  const posthog = await loading;
  if (mine === signIns) client = posthog;
}

/** An event, if analytics has started for this person or visitor. */
export function capture(
  event: string,
  properties?: Record<string, unknown>,
): void {
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
