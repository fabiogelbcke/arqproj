// The office's portfolio (Portfólio tab): what its address shows at `/` once
// published. Every change answers with the whole portfolio, which replaces ours.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call, type Schemas } from "../api/client";
import { sendFile, UploadBroke } from "../client/StageUploads";
import { COVER_OUTPUT, cropToFile, loadImage } from "../ui/imageCrop";

export type Portfolio = Schemas["PortfolioOut"];
export type Entry = Schemas["EntryOut"];
/** A line of a work's sheet: a built-in detail (its `key`) or one with the office's own label. */
export type SheetLine = Schemas["SheetLineOut"];
export type DetailType = Schemas["DetailTypeOut"];

export const PORTFOLIO = ["portfolio"] as const;
// How the public page lays the works out: landscape covers, or every image in
// its own shape, as the networks show them (PortfolioFormat).
export const FORMATS = ["gallery", "mosaic"] as const satisfies readonly Portfolio["format"][];

// As the server allows (backend/portfolio/models.py).
export const LIMITS = {
  intro: 600,
  title: 80,
  place: 80,
  description: 2000,
  entries: 60,
  photos: 30,
  credits: 120,
  label: 40,
  details: 20, // lines of a work's sheet
  detail: 200, // a text value: room for a team's names
  link: 300,
  videos: 6,
  videoMb: 200,
};

/** Lines a portfolio's sheet usually names that a project's page doesn't, offered
 * ready-made as the office's own labels (text): what architecture sites and
 * ArchDaily's project sheets credit (photography, builder, manufacturers...). */
export const SUGGESTED_LINES = [
  "photography",
  "builder",
  "woodwork",
  "landscape",
  "lighting",
  "structure",
  "collaborators",
  "suppliers",
] as const;

/** The built-in details a line of the sheet may be: the project page's, with
 * "Responsável" even where projects name their members instead. */
export function useDetailTypes() {
  return useQuery({
    queryKey: ["portfolio", "detail-types"],
    queryFn: () => call(api.GET("/api/portfolio/detail-types")),
    staleTime: Infinity,
  });
}

/** What every browser plays (the server checks it too). */
export const VIDEO_TYPES = ["video/mp4", "video/webm"];

/** The networks the page links to, in its footer's order. */
export const NETWORKS = [
  "instagram",
  "linkedin",
  "pinterest",
  "youtube",
  "vimeo",
  "behance",
  "facebook",
  "tiktok",
] as const satisfies readonly Schemas["SocialNetwork"][];

/** An area as typed ("1.250,5", "1.250", "180 m²", or "1,250.5" the English
 * way): its number, null when empty, or undefined when it isn't one the server
 * keeps. With both separators, the last one is the decimal one; alone, a
 * separator before exactly three digits groups thousands ("12.000" is twelve
 * thousand, not twelve). */
export function parsedArea(text: string): number | null | undefined {
  let written = text.replace(/\s|m²|m2/gi, "");
  if (!written) return null;
  const comma = written.lastIndexOf(",");
  const dot = written.lastIndexOf(".");
  if (comma >= 0 && dot >= 0) {
    const [group, decimal] = comma > dot ? [".", ","] : [",", "."];
    written = written.split(group).join("").replace(decimal, ".");
  } else if (comma >= 0 || dot >= 0) {
    const separator = comma >= 0 ? "," : ".";
    const parts = written.split(separator);
    const grouping = parts.length > 2 || parts[parts.length - 1]!.length === 3;
    written = grouping ? parts.join("") : parts.join(".");
  }
  const area = Number(written);
  // What the server keeps for a detail: from zero to under ten billion.
  return Number.isFinite(area) && area >= 0 && area < 10_000_000_000 ? Math.round(area * 100) / 100 : undefined;
}

export function usePortfolio() {
  return useQuery({ queryKey: PORTFOLIO, queryFn: () => call(api.GET("/api/portfolio")) });
}

function useChange<T>(send: (value: T) => Promise<Portfolio>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: send,
    onSuccess: (portfolio) => client.setQueryData(PORTFOLIO, portfolio),
  });
}

export const useSavePortfolio = () =>
  useChange((body: Schemas["PortfolioIn"]) => call(api.PATCH("/api/portfolio", { body })));

export const useAddEntry = () =>
  useChange((body: Schemas["EntryIn"]) => call(api.POST("/api/portfolio/entries", { body })));

export const useChangeEntry = () =>
  useChange(({ id, ...body }: Schemas["EntryChange"] & { id: string }) =>
    call(api.PATCH("/api/portfolio/entries/{entry_id}", { params: { path: { entry_id: id } }, body })),
  );

export const useRemoveEntry = () =>
  useChange((id: string) => call(api.DELETE("/api/portfolio/entries/{entry_id}", { params: { path: { entry_id: id } } })));

export const useOrderEntries = () =>
  useChange((entries: string[]) => call(api.PUT("/api/portfolio/order", { body: { entries } })));

export const useRemovePhoto = () =>
  useChange((id: string) => call(api.DELETE("/api/portfolio/photos/{photo_id}", { params: { path: { photo_id: id } } })));

/** A photo as the server keeps it: a JPEG of at most 2400 px, like a cover. */
export async function resized(source: Blob, name: string): Promise<File> {
  const address = URL.createObjectURL(source);
  try {
    const whole = { x: 0, y: 0, width: 100, height: 100 }; // in percent
    return await cropToFile(await loadImage(address), whole, COVER_OUTPUT, name.replace(/\.[^.]*$/, "") + ".jpg");
  } finally {
    URL.revokeObjectURL(address);
  }
}

export const useAddPhoto = () =>
  useChange(({ entry, file }: { entry: string; file: File }) =>
    call(
      api.POST("/api/portfolio/entries/{entry_id}/photos", {
        params: { path: { entry_id: entry } },
        // OpenAPI describes an uploaded file as a binary string; it is the File.
        body: { file: file as unknown as string },
        bodySerializer: (body: { file: string }) => {
          const form = new FormData();
          form.append("file", body.file as unknown as Blob, file.name);
          return form;
        },
      }),
    ),
  );

export const useRemoveVideo = () =>
  useChange((id: string) => call(api.DELETE("/api/portfolio/videos/{video_id}", { params: { path: { video_id: id } } })));

/** A frame of the video, about a second in, as a JPEG: its thumbnail, and the
 *  poster shown until it plays. Rejects when the browser can't play the file,
 *  which visitors' browsers then couldn't either. */
export function videoPoster(file: File, wait = 20000): Promise<File> {
  return new Promise((resolve, reject) => {
    const address = URL.createObjectURL(file);
    const video = document.createElement("video");
    const done = (outcome: () => void) => {
      clearTimeout(timer);
      URL.revokeObjectURL(address);
      outcome();
    };
    const timer = setTimeout(() => done(() => reject(new Error("video"))), wait);
    video.muted = true;
    video.playsInline = true;
    video.preload = "auto";
    video.onerror = () => done(() => reject(new Error("video")));
    video.onloadeddata = () => {
      video.currentTime = Math.min(1, (video.duration || 0) / 10);
    };
    video.onseeked = () => {
      const scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight, 1));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      if (!canvas.width || !canvas.height) return done(() => reject(new Error("video")));
      canvas.getContext("2d")!.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        (blob) =>
          done(() => (blob ? resolve(new File([blob], "capa.jpg", { type: "image/jpeg" })) : reject(new Error("video")))),
        "image/jpeg",
        0.85,
      );
    };
    video.src = address;
  });
}

/** A video: straight to the office's storage (as clients' uploads go), then
 *  registered with its poster. */
export async function sendVideo(
  entry: string,
  file: File,
  poster: File,
  onProgress: (fraction: number) => void,
): Promise<Portfolio> {
  const path = { entry_id: entry };
  const opened = await call(
    api.POST("/api/portfolio/entries/{entry_id}/videos/uploads", {
      params: { path },
      body: { size: file.size, mime_type: file.type },
    }),
  );
  await sendFile(opened.upload_url, file, onProgress).catch((broke) =>
    broke instanceof UploadBroke
      ? call(
          api.POST("/api/portfolio/entries/{entry_id}/videos/uploads/failed", {
            params: { path },
            body: { name: file.name, size: file.size, status: broke.status, detail: broke.detail },
          }),
        ) // always an error: "upload_failed", with the support code
      : Promise.reject(broke),
  );
  return call(
    api.POST("/api/portfolio/entries/{entry_id}/videos", {
      params: { path },
      // OpenAPI describes an uploaded file as a binary string; it is the File.
      body: { name: opened.name, poster: poster as unknown as string },
      bodySerializer: (body: { name: string; poster: string }) => {
        const form = new FormData();
        form.append("name", body.name);
        form.append("poster", body.poster as unknown as Blob, "capa.jpg");
        return form;
      },
    }),
  );
}

/** Moves `items[index]` by `step` (−1 up, +1 down); the ids in their new order. */
export function moved<T extends { id: string }>(items: T[], index: number, step: number): string[] {
  const ids = items.map((item) => item.id);
  const target = index + step;
  if (target < 0 || target >= ids.length) return ids;
  [ids[index], ids[target]] = [ids[target]!, ids[index]!];
  return ids;
}
