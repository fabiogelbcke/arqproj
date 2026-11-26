import { describe, expect, it, vi } from "vitest";

import { loadImage } from "../ui/imageCrop";
import { resized, UnreadableImage } from "./portfolio";

// The browser's image decoding isn't in the test DOM: it fails as it does for a HEIC photo.
vi.mock("../ui/imageCrop", async (original) => ({
  ...(await original<typeof import("../ui/imageCrop")>()),
  loadImage: vi.fn(),
}));
URL.createObjectURL ??= () => "blob:photo";
URL.revokeObjectURL ??= () => undefined;

describe("resized", () => {
  it("names a photo the browser can't open, so an upload can skip it and go on", async () => {
    vi.mocked(loadImage).mockRejectedValue(new DOMException("The source image cannot be decoded.", "EncodingError"));
    const failure = await resized(new Blob(["heic"]), "obra.heic").catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(UnreadableImage);
    expect((failure as UnreadableImage).file).toBe("obra.heic");
  });
});
