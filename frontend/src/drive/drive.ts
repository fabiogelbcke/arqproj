// The office's file storage (Google Drive): status, connect, disconnect.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call } from "../api/client";

export const DRIVE = ["drive"] as const;
export const ONBOARDING = ["onboarding"] as const;

export function useDrive() {
  return useQuery({ queryKey: DRIVE, queryFn: () => call(api.GET("/api/drive")) });
}

/** How full the office's Google account is: asked of Google on each visit, only
 *  while connected. */
export function useDriveSpace(connected: boolean) {
  return useQuery({
    queryKey: [...DRIVE, "space"],
    queryFn: () => call(api.GET("/api/drive/space")),
    enabled: connected,
    retry: false,
  });
}

/** "12,3 GB", "850 MB": in the language's own number format. */
export function bytes(count: number, locale: string): string {
  const gb = count / 2 ** 30;
  const [value, unit] = gb >= 1 ? [gb, "GB"] : [count / 2 ** 20, "MB"];
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: value < 10 ? 1 : 0 }).format(value)} ${unit}`;
}

/** At or above this share used, the page says space is running low. */
export const SPACE_LOW = 0.8;

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
