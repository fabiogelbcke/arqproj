// Who is signed in. The app asks /api/me on start; 401 means "show sign-in".
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, call, setCsrfToken, type Me, type Schemas } from "../api/client";
import { resetAnalytics, startAnalytics } from "../posthog";

export const ME = ["me"] as const;
export const TENANT = ["tenant"] as const;

export function useMe() {
  return useQuery({
    queryKey: ME,
    queryFn: async () => {
      try {
        const me = await call(api.GET("/api/me"));
        setCsrfToken(me.csrf_token);
        void startAnalytics(me);
        return me;
      } catch (error) {
        if (error instanceof ApiError && error.code === "not_signed_in") {
          resetAnalytics(); // the session ended elsewhere (another tab): stop collecting
          return null;
        }
        throw error;
      }
    },
    staleTime: 60_000,
  });
}

export function useTenant() {
  return useQuery<Schemas["TenantOut"]>({
    queryKey: TENANT,
    queryFn: () => call(api.GET("/api/tenant")),
    staleTime: Infinity,
  });
}

/** After signing in or choosing a password: the response is the new /api/me. */
export function useSignedIn() {
  const client = useQueryClient();
  return (me: Me) => {
    setCsrfToken(me.csrf_token);
    void startAnalytics(me);
    client.setQueryData(ME, me);
  };
}

export function useSignedOut() {
  const client = useQueryClient();
  return () => {
    resetAnalytics();
    setCsrfToken(null);
    client.setQueryData(ME, null);
  };
}
