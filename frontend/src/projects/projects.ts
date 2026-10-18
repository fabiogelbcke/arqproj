// The office's projects: the list, and creating one (step P2).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call, type Schemas } from "../api/client";
import { ONBOARDING } from "../drive/drive";

export type ProjectSummary = Schemas["ProjectSummary"];
export type CreationOptions = Schemas["CreationOptions"];
export type NewProject = Schemas["ProjectIn"];

export const PROJECTS = ["projects"] as const;
const CREATION_OPTIONS = ["project-types"] as const;

export function useProjects() {
  return useQuery({ queryKey: PROJECTS, queryFn: () => call(api.GET("/api/projects")) });
}

/** The project types, each with its usual stages, and every built-in stage in order. */
export function useCreationOptions() {
  return useQuery({
    queryKey: CREATION_OPTIONS,
    queryFn: () => call(api.GET("/api/project-types")),
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

/** Puts a project returned by a change into the list (or takes it out, archived). */
function useStoreProject() {
  const client = useQueryClient();
  return (project: ProjectSummary) => {
    client.setQueryData<ProjectSummary[]>(PROJECTS, (list) => {
      if (!list) return list;
      const others = list.filter((p) => p.id !== project.id);
      return project.status === "archived" ? others : [...others, project];
    });
    void client.invalidateQueries({ queryKey: PROJECTS });
  };
}

export type ProjectChange = Schemas["ProjectChange"];

export function useChangeProject() {
  const store = useStoreProject();
  return useMutation({
    mutationFn: ({ id, ...body }: ProjectChange & { id: string }) =>
      call(api.PATCH("/api/projects/{project_id}", { params: { path: { project_id: id } }, body })),
    onSuccess: store,
  });
}

export const COVER_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const COVER_MAX_BYTES = 10 * 1024 * 1024;

export function useUploadCover() {
  const store = useStoreProject();
  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) =>
      call(
        api.PUT("/api/projects/{project_id}/cover", {
          params: { path: { project_id: id } },
          // OpenAPI describes an uploaded file as a binary string; it is the File.
          body: { file: file as unknown as string },
          bodySerializer: (body) => {
            const form = new FormData();
            form.append("file", body.file as unknown as Blob);
            return form;
          },
        }),
      ),
    onSuccess: store,
  });
}

export function useRemoveCover() {
  const store = useStoreProject();
  return useMutation({
    mutationFn: (id: string) =>
      call(api.DELETE("/api/projects/{project_id}/cover", { params: { path: { project_id: id } } })),
    onSuccess: store,
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
