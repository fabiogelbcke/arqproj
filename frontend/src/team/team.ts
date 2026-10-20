// Configurações → Equipe (A36): the office's staff, invites and the shared link.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call, type Schemas } from "../api/client";

export const TEAM = ["team"] as const;
export type Member = Schemas["MemberOut"];

export function useTeam() {
  return useQuery({ queryKey: TEAM, queryFn: () => call(api.GET("/api/team")) });
}

function useRefresh() {
  const client = useQueryClient();
  return () => void client.invalidateQueries({ queryKey: TEAM });
}

export function useInvite() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: { name: string; email: string; role: "member" | "owner" }) =>
      call(api.POST("/api/team/invites", { body })),
    onSuccess: refresh,
  });
}

/** A new link for a pending invite (emailed again; the old one stops). */
export function useInviteAgain() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (id: string) =>
      call(api.POST("/api/team/invites/{user_id}/link", { params: { path: { user_id: id } } })),
    onSuccess: refresh,
  });
}

export function useCancelInvite() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (id: string) => call(api.DELETE("/api/team/invites/{user_id}", { params: { path: { user_id: id } } })),
    onSuccess: refresh,
  });
}

/** Turns the shared link on with a new link (any old one stops working). */
export function useJoinLinkOn() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: () => call(api.POST("/api/team/join-link")), onSuccess: refresh });
}

export function useJoinLinkOff() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: () => call(api.DELETE("/api/team/join-link")), onSuccess: refresh });
}
