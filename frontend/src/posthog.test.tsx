import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Me } from "./api/client";
import { fakeApi, ME, notSignedIn, TENANT } from "./test/render";

// The real SDK would reach PostHog's servers: here, what it is asked to do.
const sdk = vi.hoisted(() => {
  let optedOut = false;
  return {
    init: vi.fn(),
    identify: vi.fn(),
    group: vi.fn(),
    register: vi.fn(),
    capture: vi.fn(),
    reset: vi.fn(),
    opt_out_capturing: vi.fn(() => void (optedOut = true)),
    opt_in_capturing: vi.fn(() => void (optedOut = false)),
    has_opted_out_capturing: () => optedOut,
  };
});
vi.mock("posthog-js/full/no-external", () => ({ default: sdk }));

const ANALYTICS = {
  token: "phc_test",
  host: "https://us.i.posthog.com",
  user_id: "6f1c1d1e-0000-4000-8000-000000000001",
  tenant_id: "6f1c1d1e-0000-4000-8000-0000000000aa",
};

const VISITOR = { token: "phc_test", host: "https://us.i.posthog.com", tenant_id: ANALYTICS.tenant_id };
const PROJECT_ID = "6f1c1d1e-0000-4000-8000-0000000000b1";

beforeEach(() => {
  vi.clearAllMocks();
  vi.resetModules(); // each test starts with PostHog not yet started
});

describe("product analytics in the browser (A39)", () => {
  it("starts for signed-in staff with the server's key: their id, role and office, never email or name", async () => {
    const { capture, startAnalytics } = await import("./posthog");
    capture("too_early"); // before it starts: nothing
    await startAnalytics({ ...ME, analytics: ANALYTICS } as unknown as Me);
    expect(sdk.init).toHaveBeenCalledWith(
      "phc_test",
      expect.objectContaining({
        api_host: "https://us.i.posthog.com",
        disable_session_recording: true,
        mask_all_text: true,
        capture_heatmaps: false,
        capture_performance: false,
      }),
    );
    expect(sdk.identify).toHaveBeenCalledWith(ANALYTICS.user_id, { role: "owner" });
    expect(sdk.group).toHaveBeenCalledWith("tenant", ANALYTICS.tenant_id, { slug: "alinea" });
    expect(JSON.stringify(sdk.identify.mock.calls)).not.toContain(ME.email);
    await startAnalytics({ ...ME, analytics: ANALYTICS } as unknown as Me);
    expect(sdk.init).toHaveBeenCalledTimes(1); // set up once per page
    capture("files_uploaded", { file_count: 2 });
    expect(sdk.capture.mock.calls).toEqual([["files_uploaded", { file_count: 2 }]]);
  });

  it("collects nothing between a sign-out and the next sign-in, who is identified anew", async () => {
    const { capture, resetAnalytics, startAnalytics } = await import("./posthog");
    await startAnalytics({ ...ME, analytics: ANALYTICS } as unknown as Me);
    resetAnalytics();
    expect(sdk.opt_out_capturing).toHaveBeenCalled(); // no clicks, pages or errors from the sign-in screen
    capture("files_uploaded");
    expect(sdk.capture).not.toHaveBeenCalled();
    const other = { ...ANALYTICS, user_id: "6f1c1d1e-0000-4000-8000-000000000002" };
    await startAnalytics({ ...ME, role: "member", analytics: other } as unknown as Me);
    expect(sdk.init).toHaveBeenCalledTimes(1);
    expect(sdk.reset).toHaveBeenCalledTimes(1);
    expect(sdk.opt_in_capturing).toHaveBeenCalledTimes(1);
    expect(sdk.identify).toHaveBeenLastCalledWith(other.user_id, { role: "member" });
  });

  it("a sign-out while PostHog is still loading leaves it off", async () => {
    const { capture, resetAnalytics, startAnalytics } = await import("./posthog");
    const starting = startAnalytics({ ...ME, analytics: ANALYTICS } as unknown as Me);
    resetAnalytics(); // before the SDK has arrived
    await starting;
    expect(sdk.init).toHaveBeenCalledWith("phc_test", expect.objectContaining({ opt_out_capturing_by_default: true }));
    expect(sdk.opt_in_capturing).not.toHaveBeenCalled();
    expect(sdk.identify).not.toHaveBeenCalled();
    capture("files_uploaded");
    expect(sdk.capture).not.toHaveBeenCalled();
  });

  it("stops collecting when the session turns out to have ended (signed out in another tab)", async () => {
    let signedIn = true;
    fakeApi({
      "GET /api/me": () => (signedIn ? { body: { ...ME, analytics: ANALYTICS } } : notSignedIn),
    });
    const { useMe } = await import("./session/session");
    const queries = new QueryClient();
    const { result } = renderHook(() => useMe(), {
      wrapper: ({ children }) => <QueryClientProvider client={queries}>{children}</QueryClientProvider>,
    });
    await waitFor(() => expect(sdk.identify).toHaveBeenCalled());
    signedIn = false;
    await queries.invalidateQueries();
    await waitFor(() => expect(result.current.data).toBeNull());
    expect(sdk.opt_out_capturing).toHaveBeenCalled();
  });

  it("stops when the session becomes an operator's support session in this browser (A43)", async () => {
    const { capture, startAnalytics } = await import("./posthog");
    await startAnalytics({ ...ME, analytics: ANALYTICS } as unknown as Me);
    // Another tab entered support: this tab's next /api/me has no key.
    await startAnalytics({ ...ME, name: "Suporte Unio", analytics: null, support_until: "2026-10-30T15:30:00Z" } as unknown as Me);
    expect(sdk.opt_out_capturing).toHaveBeenCalled();
    capture("team_member_invited");
    expect(sdk.capture).not.toHaveBeenCalled();
  });

  it("a support session that overtakes a start still loading leaves it off", async () => {
    const { startAnalytics } = await import("./posthog");
    const starting = startAnalytics({ ...ME, analytics: ANALYTICS } as unknown as Me);
    await startAnalytics({ ...ME, analytics: null } as unknown as Me);
    await starting;
    expect(sdk.opt_in_capturing).not.toHaveBeenCalled();
    expect(sdk.identify).not.toHaveBeenCalled();
  });

  it("stays off where the server has no key (staging, local runs)", async () => {
    const { startAnalytics } = await import("./posthog");
    await startAnalytics({ ...ME, analytics: null } as unknown as Me);
    expect(sdk.init).not.toHaveBeenCalled();
  });

  it("counts a project page's visitor without cookies or a person, where the server has a key", async () => {
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: { ...TENANT, analytics: VISITOR } }),
      "GET /api/me": () => notSignedIn,
      "GET /api/pages/casa-jardim": () => ({ status: 404, body: { error: "page_not_found" } }),
    });
    const { ClientApp } = await import("./client/ClientApp");
    render(<ClientApp />);
    await waitFor(() => expect(sdk.init).toHaveBeenCalled());
    expect(sdk.init).toHaveBeenCalledWith(
      "phc_test",
      expect.objectContaining({
        cookieless_mode: "always",
        person_profiles: "never",
        disable_session_recording: true,
        mask_all_text: true,
        capture_heatmaps: false, // they send the address unscrubbed
        capture_performance: false,
      }),
    );
    expect(sdk.identify).not.toHaveBeenCalled(); // nobody, only counted
  });

  it("starts nothing for a visitor where the server has no key", async () => {
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: TENANT }),
      "GET /api/me": () => notSignedIn,
      "GET /api/pages/casa-jardim": () => ({ status: 404, body: { error: "page_not_found" } }),
    });
    const { ClientApp } = await import("./client/ClientApp");
    render(<ClientApp />);
    await waitFor(() => expect(document.body.textContent).not.toBe(""));
    expect(sdk.init).not.toHaveBeenCalled();
  });

  it("staff on a project page are counted as themselves, not as a visitor", async () => {
    window.history.pushState({}, "", "/casa-jardim");
    fakeApi({
      "GET /api/tenant": () => ({ body: { ...TENANT, analytics: VISITOR } }),
      "GET /api/me": () => ({ body: { ...ME, analytics: ANALYTICS } }),
      "GET /api/pages/casa-jardim": () => ({ status: 404, body: { error: "page_not_found" } }),
    });
    const { ClientApp } = await import("./client/ClientApp");
    render(<ClientApp />);
    await waitFor(() => expect(sdk.identify).toHaveBeenCalled());
    expect(sdk.init).toHaveBeenCalledTimes(1);
    expect(sdk.init.mock.calls[0]![1]).not.toHaveProperty("cookieless_mode");
  });

  it("sends no project name, file name or token: the project by its id, only where a visit came from", async () => {
    const { analyticsProject, startVisitorAnalytics } = await import("./posthog");
    analyticsProject("casa-silva", PROJECT_ID);
    await startVisitorAnalytics({ ...VISITOR, slug: "alinea" });
    const scrub = sdk.init.mock.calls[0]![1].before_send;
    const here = window.location.origin;
    const event = scrub({
      event: "$pageview",
      properties: {
        title: "Casa Silva · Alinea",
        $current_url: `${here}/casa-silva?etapa=3&pasta=Renders&arquivo=Fachada%20Silva.jpg&utm_source=email#topo`,
        $pathname: "/casa-silva",
        $referrer: "https://www.google.com/search?q=casa+silva",
        file_count: 2,
      },
      $set_once: { $initial_current_url: `${here}/casa-silva?arquivo=x.pdf`, $initial_pathname: "/casa-silva" },
    });
    expect(event.properties).toEqual({
      $current_url: `${here}/projeto?utm_source=email`,
      $pathname: "/projeto",
      $referrer: "https://www.google.com/search",
      file_count: 2,
      project_id: PROJECT_ID,
    });
    expect(event.$set_once).toEqual({ $initial_current_url: `${here}/projeto`, $initial_pathname: "/projeto" });
    expect(JSON.stringify(event)).not.toMatch(/silva|fachada|renders/i);
  });

  it("hides the project's address before its page has loaded, and from signed-in staff's events too", async () => {
    const { analyticsProject, startAnalytics } = await import("./posthog");
    analyticsProject("casa-silva", null); // the page hasn't answered yet
    await startAnalytics({ ...ME, analytics: ANALYTICS } as unknown as Me);
    const scrub = sdk.init.mock.calls[0]![1].before_send;
    const here = window.location.origin;
    const event = scrub({
      event: "$pageview",
      properties: { title: "Casa Silva · Alinea", $current_url: `${here}/casa-silva?arquivo=Planta.pdf`, $pathname: "/casa-silva" },
    });
    expect(event.properties).toEqual({ $current_url: `${here}/projeto`, $pathname: "/projeto" });
  });
});
