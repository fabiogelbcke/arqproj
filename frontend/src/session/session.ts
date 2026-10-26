// Who is signed in. The app asks /api/me on start; 401 means "show sign-in".
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, call, setCsrfToken, type Me, type Schemas } from "../api/client";
import posthog from "../posthog";

export const ME = ["me"] as const;
export const TENANT = ["tenant"] as const;

/** Identifies a signed-in staff member from the existing team response's stable UUID. */
export function identifySignedInMember(me: Me): void {
  void call(api.GET("/api/team")).then(
    (team) => {
      const member = team.members.find((candidate) => candidate.me);
      if (!member) return;
      posthog.identify(member.id, {
        email: me.email,
        name: me.name,
        role: me.role,
        tenant_slug: me.tenant_slug,
      });
    },
    () => undefined,
  );
}

export function useMe() {
  return useQuery({
    queryKey: ME,
    queryFn: async () => {
      try {
        const me = await call(api.GET("/api/me"));
        setCsrfToken(me.csrf_token);
        identifySignedInMember(me);
        return me;
      } catch (error) {
        if (error instanceof ApiError && error.code === "not_signed_in") return null;
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
    identifySignedInMember(me);
    client.setQueryData(ME, me);
  };
}

export function useSignedOut() {
  const client = useQueryClient();
  return () => {
    posthog.reset();
    setCsrfToken(null);
    client.setQueryData(ME, null);
  };
}
