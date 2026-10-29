// Proposals (A42): the generator's data, its saves, and amounts as typed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call, type Schemas } from "../api/client";
import { OFFICE } from "../office/office";
import { PROJECTS } from "../projects/projects";

export type Generator = Schemas["GeneratorOut"];
export type ProposalContent = Schemas["ProposalContent"];
export type ProposalView = Schemas["ProposalOut"];
export type Preset = Schemas["PresetOut"];

export type ProposalRow = Schemas["ProposalRow"];

export const proposalKey = (projectId: string) => ["proposal", projectId] as const;
export const PROPOSALS = ["proposals"] as const;

/** The Propostas tab (A42): open, accepted and declined proposals. */
export function useProposalList() {
  return useQuery({ queryKey: PROPOSALS, queryFn: () => call(api.GET("/api/proposals")) });
}

/** "Recusada" (archived while a proposal), or undone back to a proposal. */
export function useDeclineProposal() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ row, declined }: { row: ProposalRow; declined: boolean }) =>
      call(
        api.PATCH("/api/projects/{project_id}", {
          params: { path: { project_id: row.project_id } },
          body: { status: declined ? "archived" : "proposal", row_version: row.row_version },
        }),
      ),
    onSuccess: () => void client.invalidateQueries({ queryKey: PROPOSALS }),
  });
}

export function useGenerator(projectId: string) {
  return useQuery({
    queryKey: proposalKey(projectId),
    queryFn: () => call(api.GET("/api/projects/{project_id}/proposal", { params: { path: { project_id: projectId } } })),
  });
}

export function useSaveProposal(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    // An owner may also replace the office's details with the proposal's.
    mutationFn: ({ content, updateOffice }: { content: ProposalContent; updateOffice: boolean }) =>
      call(
        api.POST("/api/projects/{project_id}/proposals", {
          params: { path: { project_id: projectId }, query: { update_office: updateOffice } },
          body: content,
        }),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: proposalKey(projectId) });
      void client.invalidateQueries({ queryKey: OFFICE });
      void client.invalidateQueries({ queryKey: PROPOSALS });
    },
  });
}

export function useAcceptProposal(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (row_version: number) =>
      call(
        api.POST("/api/projects/{project_id}/accept-proposal", {
          params: { path: { project_id: projectId } },
          body: { row_version },
        }),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: proposalKey(projectId) });
      void client.invalidateQueries({ queryKey: PROJECTS });
      void client.invalidateQueries({ queryKey: PROPOSALS });
    },
  });
}

export function useSavePresets(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (services: Preset[]) => call(api.PUT("/api/proposal-presets", { body: { services } })),
    onSuccess: () => void client.invalidateQueries({ queryKey: proposalKey(projectId) }),
  });
}

export function useSaveDefaults(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { intro?: string; notes?: string }) => call(api.PATCH("/api/proposal-defaults", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: proposalKey(projectId) }),
  });
}

/** The live preview: the client page's view of what is on screen. */
export function previewPage(projectId: string, body: Schemas["ProposalStart"]) {
  return call(
    api.POST("/api/projects/{project_id}/proposal/preview-page", { params: { path: { project_id: projectId } }, body }),
  );
}

/** The PDF of what is on screen, unsaved, as a file the browser can open. */
export async function previewPdf(projectId: string, body: ProposalContent): Promise<Blob> {
  return call(
    api.POST("/api/projects/{project_id}/proposal/preview", {
      params: { path: { project_id: projectId } },
      body,
      parseAs: "blob",
    }),
  ) as unknown as Promise<Blob>;
}

// -- amounts, typed as people write them ------------------------------------------

/** An amount field as it is typed: its digits are centavos, shown as currency
 *  ("2" → "0,02", "2900000" → "29.000,00"), so the commas and points come by
 *  themselves. Nothing typed, nothing shown. */
export function typedAmount(typed: string, locale: string): string {
  const digits = typed.replace(/\D/g, "").replace(/^0+/, "").slice(0, 11); // up to 999.999.999,99
  return digits ? formatAmount(Number(digits), locale) : "";
}

/** Centavos as the field shows them: 2900000 → "29.000,00" (pt-BR). */
export function formatAmount(centavos: number, locale: string): string {
  return new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(centavos / 100);
}

/** What was typed, in centavos; null if it isn't an amount. Takes "29.000",
 *  "29000,50", "R$ 29.000,00" (pt-BR) and "29,000.50" (en). */
export function parseAmount(text: string, locale: string): number | null {
  const decimal = locale.startsWith("pt") ? "," : ".";
  const cleaned = text.replace(/[^\d,.]/g, "");
  if (!/\d/.test(cleaned)) return null;
  const at = cleaned.lastIndexOf(decimal);
  // After the decimal mark come the centavos, two digits at most: "1.000,000" is
  // refused rather than read as a million. The other mark groups thousands.
  if (at >= 0 && cleaned.length - at - 1 > 2) return null;
  const [whole, cents] = at >= 0 ? [cleaned.slice(0, at), cleaned.slice(at + 1)] : [cleaned, ""];
  const reais = whole.replace(/[,.]/g, "");
  if (!/^\d*$/.test(reais) || !/^\d*$/.test(cents) || reais.length > 9) return null;
  return Number(reais || "0") * 100 + Number(cents.padEnd(2, "0") || "0");
}

/** The fee in equal instalments, the first taking what doesn't divide evenly. */
export function instalments(fee: number, count: number): number[] {
  const each = Math.floor(fee / count);
  return Array.from({ length: count }, (_, i) => (i === 0 ? fee - each * (count - 1) : each));
}
