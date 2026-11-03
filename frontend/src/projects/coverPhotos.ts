// The stock cover photos bundled with the app (plan section 10): a new project
// starts with one as its cover, staff can choose another instead of uploading,
// and the painel shows one while a project has none. Loaded once per page; both
// the painel and the project page use it, and only the painel has a query cache.
import { useEffect, useState } from "react";

import { api, call, type Schemas } from "../api/client";

export type CoverPhoto = Schemas["CoverPhoto"];

let loading: Promise<CoverPhoto[]> | null = null;

function load(): Promise<CoverPhoto[]> {
  loading ??= call(api.GET("/api/cover-photos")).catch((failure: unknown) => {
    loading = null; // the next screen asks again
    throw failure;
  });
  return loading;
}

/** The photos, `null` while loading, or `"failed"`. */
export function useCoverPhotos(): CoverPhoto[] | null | "failed" {
  const [photos, setPhotos] = useState<CoverPhoto[] | null | "failed">(null);
  useEffect(() => {
    let live = true;
    load().then(
      (found) => live && setPhotos(found),
      () => live && setPhotos("failed"),
    );
    return () => {
      live = false;
    };
  }, []);
  return photos;
}

/** Forget the loaded list (tests start each case fresh). */
export function resetCoverPhotos(): void {
  loading = null;
}
