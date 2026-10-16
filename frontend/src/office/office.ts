// The office's details (Configurações → Escritório).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call } from "../api/client";
import { ONBOARDING } from "../drive/drive";
import { ME, TENANT } from "../session/session";

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
    mutationFn: (body: { name: string; contact_email: string }) =>
      call(api.PATCH("/api/office", { body })),
    onSuccess: refresh,
  });
}

export function useUploadLogo() {
  const refresh = useRefreshAfterChange();
  return useMutation({
    mutationFn: (file: File) =>
      call(
        api.PUT("/api/office/logo", {
          // OpenAPI describes an uploaded file as a binary string; it is the File.
          body: { file: file as unknown as string },
          bodySerializer: (body) => {
            const form = new FormData();
            form.append("file", body.file as unknown as Blob);
            return form;
          },
        }),
      ),
    onSuccess: refresh,
  });
}
