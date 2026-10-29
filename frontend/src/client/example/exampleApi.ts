// The example project's stand-in for the API (plan section 16): the page's calls
// are answered here, in memory, like the tests' fakeApi. Nothing reaches the
// office's Drive or database, and a reload starts over. Only reads go to the
// server: who is signed in, the office's name and logo, and the lists of project
// types and details the editors offer. Every other /api request stays here.
import type { Schemas } from "../../api/client";
import { fileSource, type Page } from "../format";
import { EXAMPLE_SHARE, EXAMPLE_SHARE_KEY, EXAMPLE_SLUG } from "./address";
import { atOfficeTime, EXAMPLE_TIMEZONE, exampleProject, type ExampleFile, type ExampleProject } from "./fixture";

const READS = ["/api/me", "/api/tenant", "/api/project-types", "/api/detail-types"];
const PROJECT = `/api/projects/${EXAMPLE_SLUG}`; // the example's project id is its address
const PAGE = `/api/pages/${EXAMPLE_SLUG}`;
const UPLOADS = "/exemplo-upload/"; // where the page "sends" a file: ExampleUpload below

type Reply = { status?: number; body?: unknown };
type Body = Record<string, unknown>;
/** The preview page's data (plan section 18, "Visual variants"): the project, the
 *  office and the view are given, and even the reads stay in the browser. */
export type ExamplePreview = {
  project: ExampleProject;
  office: Page["office"];
  staff: boolean; // the staff view (staff bar, edit mode) or the client's
  recipients: string[];
};
type Route = [method: string, path: RegExp, answer: (match: string[], body: Body, request: Request) => Reply | Promise<Reply>];

const done: Reply = { status: 204 };
const refused = (error: Schemas["ErrorCode"], status = 422): Reply => ({ status, body: { error } });

/** Answers the example page's API calls from now on, starting from the fixture
 *  (or from the preview page's data, with no request reaching the server). */
export function installExampleApi(now = new Date(), preview?: ExamplePreview) {
  const real: typeof fetch = (globalThis.fetch as { real?: typeof fetch }).real ?? globalThis.fetch;
  let timeZone = EXAMPLE_TIMEZONE;
  let project: ExampleProject = preview?.project ?? exampleProject(now, timeZone);
  let office: Page["office"] = preview?.office ?? { name: "", logo_url: null, logo_dark_url: null };
  let locale: Page["locale"] = "pt-BR"; // the office's: the page around the (Portuguese) project
  let signedIn = preview?.staff ?? false;
  let version = 1; // the page's row version: each change makes a new one
  // The fictional client's address for updates (A32), in the browser like the rest.
  let recipients = preview?.recipients ?? ["marina.andrade@exemplo.com.br"];
  let options: Schemas["CreationOptions"] | null = null;
  let detailTypes: Schemas["DetailTypeOut"][] | null = null;
  const pending = new Map<string, { position: number; name: string; versionOf?: string }>();
  let counter = 0;
  const id = () => `exemplo-n${(counter += 1)}`;

  const page = (): Page => ({
    id: "00000000-0000-4000-8000-00000000e0e0", // the example project is in no database
    office,
    locale,
    timezone: timeZone,
    name: project.name,
    client_name: project.client_name,
    project_type: project.project_type,
    project_type_key: project.project_type_key,
    description: project.description,
    cover_url: project.cover_url,
    completed: project.status === "completed",
    current_position: null, // the previous release's (A30); this page doesn't read it
    last_update: project.last_update,
    details: project.details,
    stages: project.stages.map(({ title, about, notes, completed }, i) => ({
      position: i + 1,
      title,
      about,
      notes,
      completed,
    })),
    next_meeting: project.next_meeting,
    // Staff see the staff bar and can try edit mode.
    staff: signedIn
      ? {
          project_id: EXAMPLE_SLUG,
          status: project.status,
          row_version: version,
          recipients: recipients.map((email) => ({ email, subscribed: true })),
        }
      : null,
  });

  const files = (): Schemas["PageFilesOut"] => ({
    stages: project.stages.map((stage, i) => ({
      position: i + 1,
      unavailable: false,
      groups: stage.groups
        .filter((group) => group.files.length)
        .map((group) => ({ folder: group.folder, files: group.files.map(({ url: _url, ...shown }) => shown) })),
    })),
    updates: project.updates,
  });

  const find = (key: string) => {
    for (const stage of project.stages)
      for (const group of stage.groups) {
        const index = group.files.findIndex((file) => file.key === key);
        if (index >= 0) return { group, index, file: group.files[index]! };
      }
    return null;
  };
  const addFile = (position: number, file: ExampleFile) => {
    const stage = project.stages[position - 1]!;
    const top = stage.groups.find((group) => group.folder === null);
    if (top) top.files.push(file);
    else stage.groups.unshift({ folder: null, files: [file] });
  };
  // Versions (A25), simply: a document is a file of the same name in the stage's
  // top folder; its next version is "Planta v3.pdf".
  const sameName = (position: number, name: string) =>
    project.stages[position - 1]?.groups
      .find((group) => group.folder === null)
      ?.files.find((file) => file.name.toLowerCase() === name.toLowerCase());
  const nextName = (file: ExampleFile) => {
    const dot = file.name.lastIndexOf(".");
    const [stem, extension] = dot > 0 ? [file.name.slice(0, dot), file.name.slice(dot)] : [file.name, ""];
    return `${stem} v${(file.version ?? 1) + 1}${extension}`;
  };

  /** One more change: a new row version, the page's date, and what the client
   *  sees in "Atualizações". */
  const changed = (update?: Omit<Schemas["UpdateOut"], "id" | "occurred_at">) => {
    version += 1;
    const at = new Date().toISOString();
    project.last_update = at;
    if (update) project.updates.unshift({ id: id(), occurred_at: at, ...update });
    return done;
  };
  const stage = (match: string[]) => project.stages[Number(match[1]) - 1];
  // "Compartilhar arquivos" (A37), in this browser: the links made, and the page
  // the example's link opens (SharePage at /share/exemplo reads it).
  let links: { link: Schemas["ShareOut"]; keys: string[] }[] = [];
  const shareLink = (body: Body): Schemas["ShareMadeOut"] => {
    const keys = body.files as string[];
    const days = body.expiry === "7d" ? 7 : body.expiry === "30d" ? 30 : null;
    const expires = days ? new Date(Date.now() + days * 86400000).toISOString() : null;
    const link: Schemas["ShareOut"] = {
      id: id(),
      label: (body.label as string | null) || null,
      made_by: signedIn ? "Você" : null,
      created_at: new Date().toISOString(),
      expires_at: expires,
      disabled: false,
      expired: false,
      files: keys.length,
      available: keys.length,
      newer: 0,
      downloads: 0,
      last_download_at: null,
      protected: false, // the example's page opens without one
    };
    links = [{ link, keys }, ...links];
    const picked = keys.flatMap((key) =>
      project.stages.flatMap((s, i) =>
        s.groups.flatMap((g) => g.files.filter((f) => f.key === key).map((f) => ({ ...f, position: i + 1, stage: s.title }))),
      ),
    );
    try {
      localStorage.setItem(
        EXAMPLE_SHARE_KEY,
        JSON.stringify({
          project: project.name,
          label: link.label,
          expires_at: expires,
          files: picked.map((f) => ({
            name: f.name,
            kind: f.kind,
            size: f.size,
            modified_at: f.modified_at,
            stage: `${String(f.position).padStart(2, "0")} ${f.stage}`,
            url: f.url,
          })),
        }),
      );
    } catch {
      // Storage off: the example's link opens on an empty page.
    }
    return { link, url: `${window.location.origin}/share/${EXAMPLE_SHARE}`, owner: link.id };
  };

  const routes: Route[] = [
    ["GET", new RegExp(`^${PAGE}$`), () => ({ body: page() })],
    ["GET", new RegExp(`^${PAGE}/files$`), () => ({ body: files() })],
    ["POST", /^\/api\/me\/tour-seen$/, () => done], // the example's tour stores nothing
    // "Novidades por e-mail": as if signed up; nothing leaves the browser.
    ["POST", new RegExp(`^${PAGE}/subscribe$`), () => done],
    ["POST", new RegExp(`^${PAGE}/shares$`), (_, body) => ({ status: 201, body: shareLink(body) })],
    ["GET", new RegExp(`^${PAGE}/shares$`), () => ({ body: links.map((l) => l.link) })],
    [
      "POST",
      new RegExp(`^${PAGE}/shares/mine$`),
      (_, body) => ({ body: links.filter((l) => (body.owners as string[]).includes(l.link.id)).map((l) => l.link) }),
    ],
    [
      "POST",
      new RegExp(`^${PAGE}/shares/([^/]+)/(disable|refresh)$`),
      (match) => {
        const found = links.find((l) => l.link.id === match[1]);
        if (!found) return refused("share_not_found", 404);
        if (match[2] === "disable") found.link = { ...found.link, disabled: true };
        return { body: found.link };
      },
    ],
    [
      "PATCH",
      new RegExp(`^${PROJECT}$`),
      (_, body) => {
        if (typeof body.name === "string" && body.name.trim()) project.name = body.name.trim();
        if (Array.isArray(body.recipients)) recipients = body.recipients as string[];
        return changed();
      },
    ],
    [
      "PATCH",
      new RegExp(`^${PROJECT}/content$`),
      async (_, body) => {
        if (typeof body.description === "string") project.description = body.description;
        if (Array.isArray(body.details)) {
          const types = (detailTypes ??= await list<Schemas["DetailTypeOut"][]>("/api/detail-types")) ?? [];
          project.details = (body.details as Schemas["DetailIn"][]).map(({ key, value }) => {
            const type = types.find((t) => t.key === key) ?? project.details.find((d) => d.key === key);
            const kind = type?.type ?? "text";
            return { key, label: type?.label ?? key, type: kind, value: kind === "area" ? Number(value) : value };
          });
        }
        if (typeof body.project_type === "string") {
          const types = (options ??= await list<Schemas["CreationOptions"]>("/api/project-types"))?.types ?? [];
          const chosen = types.find((type) => type.key === body.project_type);
          if (chosen) [project.project_type_key, project.project_type] = [chosen.key, chosen.label];
        }
        return changed();
      },
    ],
    [
      "PUT",
      new RegExp(`^${PROJECT}/meeting$`),
      (_, body) => {
        const day = String(body.day);
        const starts = atOfficeTime(day, String(body.start), timeZone);
        const ends = body.end
          ? atOfficeTime(day, String(body.end), timeZone)
          : new Date(Date.parse(starts) + 60 * 60 * 1000).toISOString();
        const kind = project.next_meeting ? "meeting_changed" : "meeting_scheduled";
        project.next_meeting = {
          title: String(body.title),
          starts_at: starts,
          ends_at: ends,
          location: (body.location as string | null) || null,
          link: (body.link as string | null) || null,
        };
        return changed({ kind, stage_position: null });
      },
    ],
    [
      "DELETE",
      new RegExp(`^${PROJECT}/meeting$`),
      () => {
        const name = project.next_meeting?.title ?? null;
        project.next_meeting = null;
        return changed({ kind: "meeting_cleared", stage_position: null, name });
      },
    ],
    [
      "PUT",
      new RegExp(`^${PROJECT}/stages/(\\d+)/notes$`),
      (match, body) => {
        const found = stage(match);
        if (!found) return refused("project_not_found", 404);
        found.notes = String(body.notes ?? "");
        return changed(found.notes ? { kind: "note_changed", stage_position: Number(match[1]) } : undefined);
      },
    ],
    [
      "PATCH",
      new RegExp(`^${PROJECT}/stages/(\\d+)$`),
      (match, body) => {
        const found = stage(match);
        if (!found) return refused("project_not_found", 404);
        if (typeof body.title === "string" && body.title.trim()) found.title = body.title.trim();
        return changed();
      },
    ],
    [
      "POST",
      new RegExp(`^${PROJECT}/stages/(\\d+)/move$`),
      (match, body) => {
        const from = Number(match[1]) - 1;
        const to = from + Number(body.direction);
        const stages = project.stages;
        if (!stages[from] || !stages[to]) return refused("invalid_status_change");
        [stages[from], stages[to]] = [stages[to]!, stages[from]!]; // each keeps its completion
        return changed();
      },
    ],
    [
      "DELETE",
      new RegExp(`^${PROJECT}/stages/(\\d+)$`),
      (match) => {
        const position = Number(match[1]);
        if (!stage(match)) return refused("project_not_found", 404);
        project.stages.splice(position - 1, 1);
        return changed();
      },
    ],
    [
      "POST",
      new RegExp(`^${PROJECT}/stages$`),
      async (_, body) => {
        let title = typeof body.title === "string" ? body.title.trim() : "";
        if (body.builtin_key) {
          options ??= await list<Schemas["CreationOptions"]>("/api/project-types");
          title = options?.stages.find((option) => option.key === body.builtin_key)?.title ?? title;
        }
        if (!title) return refused("invalid_status_change");
        project.stages.push({ title, about: null, notes: "", completed: false, groups: [] });
        project.status = "active"; // a new stage is open
        return changed();
      },
    ],
    [
      "PUT",
      new RegExp(`^${PROJECT}/stages/(\\d+)/completion$`),
      (match, body) => {
        // As the server: any stage, any order; the project is staff's to complete.
        const position = Number(match[1]);
        const target = stage(match);
        if (!target) return refused("project_not_found", 404);
        const completed = Boolean(body.completed);
        if (target.completed === completed) return refused("invalid_status_change");
        target.completed = completed;
        if (!completed) {
          project.status = "active";
          return changed();
        }
        return changed({ kind: "stage_completed", stage_position: position });
      },
    ],
    [
      "PUT",
      new RegExp(`^${PROJECT}/completion$`),
      () => {
        if (project.status !== "active" || project.stages.some((s) => !s.completed)) return refused("invalid_status_change");
        project.status = "completed";
        return changed({ kind: "project_completed", stage_position: null });
      },
    ],
    [
      "POST",
      new RegExp(`^${PROJECT}/stages/(\\d+)/uploads/check$`),
      (match, body) => {
        if (!stage(match)) return refused("project_not_found", 404);
        const matches = (body.names as string[]).flatMap((name) => {
          const file = sameName(Number(match[1]), name);
          if (!file) return [];
          const version = file.version ?? 1;
          return [
            {
              name,
              document: file.name,
              current: file.name,
              current_version: version,
              saved_as: nextName(file),
              next_version: version + 1,
              key: file.key,
            },
          ];
        });
        return { body: { matches } };
      },
    ],
    [
      "POST",
      new RegExp(`^${PROJECT}/stages/(\\d+)/uploads$`),
      (match, body) => {
        if (!stage(match)) return refused("project_not_found", 404);
        const upload = id();
        const position = Number(match[1]);
        const versionOf = body.version_of ? String(body.version_of) : undefined;
        // Kept apart, as the app saves it: "Planta (2).pdf".
        let name = String(body.name);
        if (!versionOf && sameName(position, name)) {
          const dot = name.lastIndexOf(".");
          name = dot > 0 ? `${name.slice(0, dot)} (2)${name.slice(dot)}` : `${name} (2)`;
        }
        pending.set(upload, { position, name, versionOf });
        return { body: { upload_url: `${UPLOADS}${upload}` } };
      },
    ],
    [
      "POST",
      new RegExp(`^${PAGE}/files/([^/]+)/hide$`),
      (match) => {
        const found = find(decodeURIComponent(match[1]!));
        if (!found) return refused("file_not_found", 404);
        found.group.files.splice(found.index, 1); // the client no longer sees it
        return changed();
      },
    ],
    [
      "POST",
      new RegExp(`^${PAGE}/files/([^/]+)/move$`),
      (match, body) => {
        const found = find(decodeURIComponent(match[1]!));
        const position = Number(body.position);
        if (!found || !project.stages[position - 1]) return refused("file_not_found", 404);
        found.group.files.splice(found.index, 1);
        addFile(position, found.file);
        return changed();
      },
    ],
    [
      "PUT",
      new RegExp(`^${PROJECT}/cover$`),
      async (_, __, request) => {
        const chosen = (await request.formData()).get("file");
        if (!(chosen instanceof Blob)) return refused("invalid_status_change");
        project.cover_url = URL.createObjectURL(chosen);
        return changed();
      },
    ],
    [
      "DELETE",
      new RegExp(`^${PROJECT}/cover$`),
      () => {
        project.cover_url = null;
        return changed();
      },
    ],
  ];

  /** A list the editors offer, read from the server (null: not signed in). */
  async function list<T>(path: string): Promise<T | null> {
    if (preview) return null; // nothing from the server
    const answer = await real(new URL(path, window.location.origin)).catch(() => null);
    return answer?.ok ? ((await answer.json()) as T) : null;
  }

  /** The server's answer to one of the reads, noting who is signed in and the office. */
  async function read(request: Request, path: string): Promise<Response> {
    const answer = await real(request);
    if (!answer.ok) return answer;
    const body = await answer.clone().json();
    if (path === "/api/tenant") {
      office = { name: body.name, logo_url: body.logo_url, logo_dark_url: body.logo_dark_url };
      locale = body.locale;
    }
    if (path === "/api/project-types") options = body;
    if (path === "/api/detail-types") detailTypes = body;
    if (path === "/api/me") {
      signedIn = true;
      if (body.tenant_timezone !== timeZone && version === 1) {
        // The office's own time zone, before anything has changed.
        timeZone = body.tenant_timezone;
        project = exampleProject(now, timeZone);
      }
      // The example has its own tour; the setup tour stays for the office's projects.
      return Response.json({ ...body, page_tour_seen: true });
    }
    return answer;
  }

  const exampleFetch = async (given: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = new Request(given instanceof Request ? given : new URL(String(given), window.location.origin), init);
    const url = new URL(request.url);
    // The page's own files (images, the bundle) load as usual.
    if (url.origin !== window.location.origin || !url.pathname.startsWith("/api/")) return real(given, init);
    if (request.method === "GET" && READS.includes(url.pathname)) {
      // The preview stays in the browser: no office, no staff, no lists to edit with.
      if (preview) return Response.json({ error: "page_not_found" }, { status: 404 });
      return read(request, url.pathname);
    }
    // "Sair" is real: the session is the person's, not the example's.
    if (request.method === "DELETE" && url.pathname === "/api/session") return real(given, init);
    const route = routes.find(([method, path]) => method === request.method && path.test(url.pathname));
    if (!route) return Response.json({ error: "page_not_found" }, { status: 404 });
    const body = request.method === "GET" || request.method === "DELETE" ? {} : await request.clone().json().catch(() => ({}));
    const reply = await route[2](route[1].exec(url.pathname)!, body, request);
    return reply.status === 204
      ? new Response(null, { status: 204 })
      : Response.json(reply.body ?? {}, { status: reply.status ?? 200 });
  };
  exampleFetch.real = real;
  globalThis.fetch = exampleFetch as typeof fetch;

  /** Stands in for Google's upload session (StageUploads' sendFile): the file stays
   *  in this browser, and shows in its stage. */
  class ExampleUpload {
    status = 0;
    responseText = "";
    upload: { onprogress: ((event: { loaded: number }) => void) | null } = { onprogress: null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    private url = "";
    open(_method: string, url: string) {
      this.url = url;
    }
    setRequestHeader() {}
    getResponseHeader() {
      return null;
    }
    send(body: Blob | null) {
      const target = this.url.startsWith(UPLOADS) ? pending.get(this.url.slice(UPLOADS.length)) : undefined;
      if (!target || !body) {
        setTimeout(() => this.onerror?.()); // nothing leaves the example
        return;
      }
      pending.delete(this.url.slice(UPLOADS.length));
      // A short, visible progress, as a real upload has.
      [0.3, 0.7, 1].forEach((share, i) =>
        setTimeout(() => {
          this.upload.onprogress?.({ loaded: body.size * share });
          if (share < 1) return;
          const kind = /^image\/(jpeg|png|webp|gif)$/.test(body.type)
            ? "image"
            : body.type === "application/pdf"
              ? "pdf"
              : "other";
          const at = new Date().toISOString();
          const current = target.versionOf ? find(target.versionOf)?.file : undefined;
          if (current) {
            // The new version takes the card; the one before goes to "Versões anteriores".
            const version = (current.version ?? 1) + 1;
            const before = { ...current, older: [], version: current.version ?? 1 };
            Object.assign(current, {
              key: id(),
              kind,
              size: body.size,
              modified_at: at,
              url: URL.createObjectURL(body),
              version,
              updated: true,
              older: [before, ...current.older],
            });
            changed({ kind: "file_published", stage_position: target.position, name: current.name, version });
          } else {
            addFile(target.position, {
              key: id(),
              name: target.name,
              kind,
              size: body.size,
              modified_at: at,
              url: URL.createObjectURL(body),
              updated: false,
              clash: false,
              older: [],
            });
            changed({ kind: "file_published", stage_position: target.position, name: target.name });
          }
          this.status = 200;
          this.onload?.();
        }, 150 * (i + 1)),
      );
    }
  }
  globalThis.XMLHttpRequest = ExampleUpload as unknown as typeof XMLHttpRequest;

  // The files are the fixture's (bundled) or uploaded here: their own addresses.
  fileSource.address = (_slug, key, as) => {
    const file =
      find(key)?.file ??
      // An older version keeps its upload's address.
      (project.stages
        .flatMap((stage) => stage.groups.flatMap((group) => group.files.flatMap((shown) => shown.older)))
        .find((old) => old.key === key) as ExampleFile | undefined);
    if (!file) return null;
    return as === "thumb" && file.kind !== "image" ? null : file.url; // a PDF: the sheet icon
  };
  fileSource.calendar = () => null; // the calendar file comes from the server
  fileSource.bundled = true;
}
