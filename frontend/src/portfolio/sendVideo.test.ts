import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { sendFile, UploadBroke } from "../client/StageUploads";
import { fakeApi } from "../test/render";
import { sendVideo } from "./portfolio";

// The bytes go straight to the storage; the test's document can't send them.
vi.mock("../client/StageUploads", async (original) => ({
  ...(await original<typeof import("../client/StageUploads")>()),
  sendFile: vi.fn(),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(sendFile).mockReset();
});

describe("sendVideo", () => {
  const video = new File(["mp4"], "obra.mp4", { type: "video/mp4" });
  const poster = new File(["jpg"], "capa.jpg", { type: "image/jpeg" });

  it("reports a send that failed for good, and fails with the support code", async () => {
    const sent = fakeApi({
      "POST /api/portfolio/entries/e-1/videos/uploads": () => ({ body: { upload_url: "/up/1", name: "video-1.mp4" } }),
      "POST /api/portfolio/entries/e-1/videos/uploads/failed": () => ({
        status: 502,
        body: { error: "upload_failed" },
        headers: { "X-Request-ID": "ref-9" },
      }),
    });
    vi.mocked(sendFile).mockRejectedValue(new UploadBroke(403, "storageQuotaExceeded")); // e.g. Drive full
    const failure = await sendVideo("e-1", video, poster, () => {}).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).code).toBe("upload_failed");
    expect((failure as ApiError).requestId).toBe("ref-9");
    expect(sent.find((call) => call.path.endsWith("/uploads/failed"))?.body).toEqual({
      name: "obra.mp4",
      size: 3,
      status: 403,
      detail: "storageQuotaExceeded",
    });
    expect(sent.some((call) => call.path === "/api/portfolio/entries/e-1/videos")).toBe(false); // never registered
  });
});
