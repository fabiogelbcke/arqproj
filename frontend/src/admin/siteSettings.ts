// The site's types and stages as "Configurações" edits them (A44): every change
// answers with both lists as they now are, which replace the cached ones.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call, type Schemas } from "../api/client";

export type Catalog = Schemas["SiteCatalogOut"];
export type SiteType = Schemas["SiteTypeOut"];
export type SiteStage = Schemas["SiteStageOut"];
export type Texts = Schemas["SiteTexts"];

const CATALOG = ["admin", "settings", "types-and-stages"] as const;

export function useCatalog() {
  return useQuery({ queryKey: CATALOG, queryFn: () => call(api.GET("/api/admin/settings/types-and-stages")) });
}

function useChange<T>(send: (body: T) => Promise<Catalog>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: send,
    onSuccess: (catalog) => client.setQueryData(CATALOG, catalog),
  });
}

export const useAddType = () =>
  useChange((body: Schemas["NewSiteTypeIn"]) => call(api.POST("/api/admin/settings/types", { body })));

export const useChangeType = (key: string) =>
  useChange((body: Schemas["SiteTypeIn"]) =>
    call(api.PUT("/api/admin/settings/types/{key}", { params: { path: { key } }, body })),
  );

export const useAddStage = () =>
  useChange((body: Schemas["NewSiteStageIn"]) => call(api.POST("/api/admin/settings/stages", { body })));

export const useChangeStage = (key: string) =>
  useChange((body: Schemas["SiteStageIn"]) =>
    call(api.PUT("/api/admin/settings/stages/{key}", { params: { path: { key } }, body })),
  );

export const useReorder = () =>
  useChange((body: Schemas["SiteOrderIn"]) => call(api.PUT("/api/admin/settings/order", { body })));

// "Avisos" (A48): batching, reminders and what goes by WhatsApp, for every office.
export type Notices = Schemas["NoticeSettingsOut"];
const NOTICES = ["admin", "settings", "notices"] as const;
/** What may go by WhatsApp, in the order the screen lists it (as the server's). */
export const NEWS = ["files", "stages", "project", "meetings", "reminders"] as const satisfies readonly Notices["whatsapp_news"][number][];

export function useNotices() {
  return useQuery({ queryKey: NOTICES, queryFn: () => call(api.GET("/api/admin/settings/notices")) });
}

export function useChangeNotices() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Schemas["NoticeSettingsIn"]) => call(api.PUT("/api/admin/settings/notices", { body })),
    onSuccess: (notices) => client.setQueryData(NOTICES, notices),
  });
}

/** The list with one item moved a place up (-1) or down (1). */
export function moved(keys: string[], key: string, by: -1 | 1): string[] {
  const list = [...keys];
  const at = list.indexOf(key);
  const to = at + by;
  if (at < 0 || to < 0 || to >= list.length) return list;
  [list[at], list[to]] = [list[to]!, list[at]!];
  return list;
}

/** As the server keeps it: English left blank is the Portuguese. */
export const sameTexts = (a: Texts | null | undefined, b: Texts | null | undefined) =>
  (a?.pt.trim() ?? "") === (b?.pt.trim() ?? "") &&
  ((a?.en.trim() || a?.pt.trim()) ?? "") === ((b?.en.trim() || b?.pt.trim()) ?? "");
