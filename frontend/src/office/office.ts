// The office's details (Configurações → Escritório).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api, call, type Schemas } from "../api/client";
import { ONBOARDING } from "../drive/drive";
import { ME, TENANT } from "../session/session";
import { svgToPng } from "./svgToPng";

export const OFFICE = ["office"] as const;

export function useOffice() {
  return useQuery({ queryKey: OFFICE, queryFn: () => call(api.GET("/api/office")) });
}

function useRefreshAfterChange() {
  const client = useQueryClient();
  return (office: unknown) => {
    client.setQueryData(OFFICE, office);
    // The name shows in the header and on the sign-in page; the checklist follows.
    void client.invalidateQueries({ queryKey: ME });
    void client.invalidateQueries({ queryKey: TENANT });
    void client.invalidateQueries({ queryKey: ONBOARDING });
  };
}

export function useSaveOffice() {
  const refresh = useRefreshAfterChange();
  return useMutation({
    // Any of the office's details; those left out stay as they are.
    mutationFn: (body: Schemas["OfficeIn"]) => call(api.PATCH("/api/office", { body })),
    onSuccess: refresh,
  });
}

/** A logo file as the API takes it. */
const asForm = (file: File) => ({
  // OpenAPI describes an uploaded file as a binary string; it is the File.
  body: { file: file as unknown as string },
  bodySerializer: (body: { file: string }) => {
    const form = new FormData();
    form.append("file", body.file as unknown as Blob, file.name);
    return form;
  },
});

/** The logo, as cropped in the browser (ImageCropDialog): always a PNG, which
 *  email programs show too. */
export function useUploadLogo() {
  const refresh = useRefreshAfterChange();
  return useMutation({
    mutationFn: (file: File) => call(api.PUT("/api/office/logo", asForm(file))),
    onSuccess: refresh,
  });
}

/** The logo for dark mode, or (null) the usual logo there too. */
export function useDarkLogo() {
  const refresh = useRefreshAfterChange();
  return useMutation({
    mutationFn: (file: File | null) =>
      call(file ? api.PUT("/api/office/logo/dark", asForm(file)) : api.DELETE("/api/office/logo/dark")),
    onSuccess: refresh,
  });
}

/** An SVG logo uploaded before PNGs were drawn gets its PNG, quietly, the next
 *  time its owner opens the painel. */
export function LogoPng() {
  const office = useOffice();
  const client = useQueryClient();
  const needed = office.data?.can_manage && office.data.logo_needs_png ? office.data.logo_url : null;
  const tried = useRef<string | null>(null);
  useEffect(() => {
    if (!needed || tried.current === needed) return;
    tried.current = needed; // once per logo, even if it fails
    void (async () => {
      try {
        const svg = await (await fetch(new Request(new URL(needed, window.location.href)))).blob();
        const png = await svgToPng(svg);
        const updated = await call(
          api.PUT("/api/office/logo/png", {
            body: { file: png as unknown as string },
            bodySerializer: (body) => {
              const form = new FormData();
              form.append("file", body.file as unknown as Blob, "logo.png");
              return form;
            },
          }),
        );
        client.setQueryData(OFFICE, updated);
      } catch {
        // Nothing to tell anyone: emails show the name until it works.
      }
    })();
  }, [needed, client]);
  return null;
}
