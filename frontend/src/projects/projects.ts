// The office's projects: the list, and creating one (step P2).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call, type Schemas } from "../api/client";
import { LIMITS } from "../api/limits";
import { ONBOARDING } from "../drive/drive";
import { sortOptions, type Sort as AnySort } from "../ui/sort";

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
    .slice(0, LIMITS.slug)
    .replace(/-+$/, "");
}

// Words before a name that don't make it another person: "Arq. Marina" is Marina.
const TITLES = new Set(["arq", "arqa", "arquiteta", "arquiteto", "eng", "enga", "engenheira", "engenheiro", "dr", "dra", "sr", "sra"]);

/** A person's name as the painel matches it: no accents, case, titles or extra
 *  spaces. "Arq. Marina  Carvalho" → "marina carvalho". */
export function personKey(name: string): string {
  return plain(name)
    .replace(/[^a-z0-9]+/g, " ")
    .split(" ")
    .filter((word) => word && !TITLES.has(word))
    .join(" ");
}

/** The people named as responsible across the projects, once each (by
 *  personKey), as first written, in alphabetical order: the painel's chips. */
export function responsibles(projects: ProjectSummary[], locale: string): { id: string; label: string }[] {
  const seen = new Map<string, string>();
  for (const project of projects) {
    const key = project.responsible ? personKey(project.responsible) : "";
    if (key && !seen.has(key)) seen.set(key, project.responsible!.trim());
  }
  return [...seen].map(([id, label]) => ({ id, label })).sort((a, b) => a.label.localeCompare(b.label, locale));
}

/** Whether a project's responsible is the signed-in person: every word of their
 *  name is in it ("Marina Carvalho" is "Arq. Marina S. Carvalho"). */
export function isMine(responsible: string | null | undefined, myName: string): boolean {
  const mine = personKey(myName).split(" ").filter(Boolean);
  if (!mine.length || !responsible) return false;
  const words = new Set(personKey(responsible).split(" "));
  return mine.every((word) => words.has(word));
}

export function matches(project: ProjectSummary, query: string): boolean {
  const words = plain(query).trim().split(/\s+/).filter(Boolean);
  const haystack = plain(`${project.name} ${project.client_name}`);
  return words.every((word) => haystack.includes(word));
}

/** The types the office has projects of, once each, in alphabetical order: the
 *  painel's filter chips (only types in use, so no chip ever shows nothing).
 *  `name` gives a type's chip its name ("Interiores"; the full one by default). */
export function projectTypes(
  projects: ProjectSummary[],
  locale: string,
  name: (key: string, label: string) => string = (_key, label) => label,
): { id: string; label: string }[] {
  const labels = new Map(projects.map((p) => [p.project_type, p.project_type_label]));
  const text = new Intl.Collator(locale, { sensitivity: "base" });
  return [...labels]
    .map(([id, label]) => ({ id, label: name(id, label) }))
    .sort((a, b) => text.compare(a.label, b.label));
}

export const SORT_KEYS = ["updated", "created", "name", "client", "type"] as const;
export type SortKey = (typeof SORT_KEYS)[number];
export type Sort = AnySort<SortKey>;
export const DEFAULT_SORT: Sort = { key: "updated", direction: "desc" };

/** Every order the list offers, each in both directions (ui/sort). */
export const SORTS = sortOptions(SORT_KEYS, ["updated", "created"]);

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
