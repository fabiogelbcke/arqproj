// The office's projects: the list, and creating one (step P2).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call, type Schemas } from "../api/client";
import { ONBOARDING } from "../drive/drive";

export type ProjectSummary = Schemas["ProjectSummary"];
export type Template = Schemas["TemplateOut"];
export type NewProject = Schemas["ProjectIn"];

export const PROJECTS = ["projects"] as const;
const TEMPLATES = ["templates"] as const;

export function useProjects() {
  return useQuery({ queryKey: PROJECTS, queryFn: () => call(api.GET("/api/projects")) });
}

export function useTemplates() {
  return useQuery({
    queryKey: TEMPLATES,
    queryFn: () => call(api.GET("/api/templates")),
    staleTime: Infinity,
  });
}

export function useCreateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: NewProject) => call(api.POST("/api/projects", { body })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: PROJECTS });
      void client.invalidateQueries({ queryKey: ONBOARDING }); // "create the first project"
    },
  });
}

/** Lowercase, no accents: "Conceição" and "conceicao" match. */
export function plain(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

/** A page address from a name: "Casa Jardim — Lagoa" → "casa-jardim-lagoa". */
export function suggestedSlug(name: string): string {
  return plain(name)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80)
    .replace(/-+$/, "");
}

export function matches(project: ProjectSummary, query: string): boolean {
  const words = plain(query).trim().split(/\s+/).filter(Boolean);
  const haystack = plain(`${project.name} ${project.client_name}`);
  return words.every((word) => haystack.includes(word));
}

export const SORT_KEYS = ["updated", "created", "name", "client", "type"] as const;
export type SortKey = (typeof SORT_KEYS)[number];
export type Sort = { key: SortKey; direction: "asc" | "desc" };
export const DEFAULT_SORT: Sort = { key: "updated", direction: "desc" };

/** Dates newest first by default; names A–Z. */
export function defaultDirection(key: SortKey): Sort["direction"] {
  return key === "updated" || key === "created" ? "desc" : "asc";
}

const lastUpdate = (p: ProjectSummary) => Date.parse(p.last_activity_at ?? p.created_at);

export function compareProjects(sort: Sort, locale: string) {
  const text = new Intl.Collator(locale, { numeric: true, sensitivity: "base" });
  const value = (p: ProjectSummary): string | number => {
    switch (sort.key) {
      case "updated":
        return lastUpdate(p);
      case "created":
        return Date.parse(p.created_at);
      case "name":
        return p.name;
      case "client":
        return p.client_name;
      case "type":
        return p.project_type_label;
    }
  };
  return (a: ProjectSummary, b: ProjectSummary) => {
    const [x, y] = [value(a), value(b)];
    const result = typeof x === "number" ? x - (y as number) : text.compare(x, y as string);
    return (sort.direction === "asc" ? result : -result) || text.compare(a.name, b.name);
  };
}

// The sort is remembered on this device (plan: list decisions for P2).
const SORT_STORAGE = "painel.projectSort";

export function loadSort(): Sort {
  try {
    const saved = JSON.parse(localStorage.getItem(SORT_STORAGE) ?? "null") as Partial<Sort> | null;
    if (
      saved &&
      SORT_KEYS.includes(saved.key as SortKey) &&
      (saved.direction === "asc" || saved.direction === "desc")
    ) {
      return saved as Sort;
    }
  } catch {
    // Unreadable or blocked storage: the default order.
  }
  return DEFAULT_SORT;
}

export function saveSort(sort: Sort): void {
  try {
    localStorage.setItem(SORT_STORAGE, JSON.stringify(sort));
  } catch {
    // Not remembered; the list still sorts.
  }
}

/** The same placeholder photo for a project every time, until it has a cover (P4). */
export function coverIndex(projectId: string, count: number): number {
  let hash = 7;
  for (const char of projectId) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return hash % count;
}
