// Who is signed in. The app asks /api/me on start; 401 means "show sign-in".
import { hashKey, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { ApiError, api, call, setCsrfToken, type Me, type Schemas } from "../api/client";
import { resetAnalytics, startAnalytics } from "../posthog";

export const ME = ["me"] as const;
export const TENANT = ["tenant"] as const;

/** Whether the office has a feature switched on from the operator dashboard (A40). */
export function useFeature(feature: Schemas["Feature"]): boolean {
  return useMe().data?.features.includes(feature) ?? false;
}

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

/** Everything the painel loaded for the person who was signed in (the projects,
 *  the team, the proposals…), so that the next one never sees it, even for a
 *  moment. Who is signed in is replaced by the caller; the office's public
 *  details (the sign-in page's) stay. */
function forgetSession(client: QueryClient) {
  const kept = [hashKey(ME), hashKey(TENANT)];
  client.removeQueries({ predicate: (query) => !kept.includes(query.queryHash) });
}

/** After signing in or choosing a password: the response is the new /api/me.
 *  Someone else than before (or no one before): nothing of theirs is kept. */
export function useSignedIn() {
  const client = useQueryClient();
  return (me: Me) => {
    setCsrfToken(me.csrf_token);
    void startAnalytics(me);
    if (client.getQueryData<Me | null>(ME)?.id !== me.id) forgetSession(client);
    client.setQueryData(ME, me);
  };
}

export function useSignedOut() {
  const client = useQueryClient();
  return () => {
    resetAnalytics();
    setCsrfToken(null);
    forgetSession(client);
    client.setQueryData(ME, null);
  };
}
