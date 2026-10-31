// The office's portfolio (Portfólio tab): what its address shows at `/` once
// published. Every change answers with the whole portfolio, which replaces ours.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call, type Schemas } from "../api/client";
import { COVER_OUTPUT, cropToFile, loadImage } from "../ui/imageCrop";

export type Portfolio = Schemas["PortfolioOut"];
export type Entry = Schemas["EntryOut"];

export const PORTFOLIO = ["portfolio"] as const;

// As the server allows (backend/portfolio/models.py).
export const LIMITS = { intro: 600, title: 80, place: 80, description: 2000, entries: 60, photos: 30 };

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

/** Moves `items[index]` by `step` (−1 up, +1 down); the ids in their new order. */
export function moved<T extends { id: string }>(items: T[], index: number, step: number): string[] {
  const ids = items.map((item) => item.id);
  const target = index + step;
  if (target < 0 || target >= ids.length) return ids;
  [ids[index], ids[target]] = [ids[target]!, ids[index]!];
  return ids;
}
