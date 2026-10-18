// The office's file storage (Google Drive): status, connect, disconnect.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call } from "../api/client";

export const DRIVE = ["drive"] as const;
export const ONBOARDING = ["onboarding"] as const;

export function useDrive() {
  return useQuery({ queryKey: DRIVE, queryFn: () => call(api.GET("/api/drive")) });
}

export function useOnboarding() {
  return useQuery({ queryKey: ONBOARDING, queryFn: () => call(api.GET("/api/onboarding")) });
}

/** Off to Google's sign-in; Google brings the person back to the settings page. */
export function useConnectDrive() {
  return useMutation({
    mutationFn: () => call(api.POST("/api/drive/connect")),
    onSuccess: ({ url }) => window.location.assign(url),
  });
}

export function useDisconnectDrive() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => call(api.DELETE("/api/drive")),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: DRIVE });
      void client.invalidateQueries({ queryKey: ONBOARDING });
    },
  });
}
