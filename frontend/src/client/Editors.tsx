// Edit mode on the client's page (part 1): the prototype's inline editors for
// the description, the details, the next meeting and a stage's note. Each saves
// with the page's row version; the page reloads after (A24, plan section 7).
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api, call, type Schemas } from "../api/client";
import { toast } from "../ui/Toast";
import type { Page } from "./format";

type Staff = NonNullable<Page["staff"]>;

function useSave(onSaved: () => void) {
  const { t, i18n } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setProblem(null);
    try {
      await work();
      toast(t("projectSettings.saved"));
      onSaved();
    } catch (failure) {
      const error =
        failure instanceof ApiError ? failure : new ApiError("unexpected");
      const message = i18n.exists(`errors.${error.code}`)
        ? t(`errors.${error.code}`)
        : t("errors.unexpected");
      setProblem(
        error.requestId
          ? `${message} ${t("errors.reference", { id: error.requestId })}`
          : message,
      );
    } finally {
      setBusy(false);
    }
  };
  return { busy, problem, run };
}

function Editor({
  title,
  busy,
  problem,
  onCancel,
  onSubmit,
  extraAction,
  children,
}: {
  title: string;
  busy: boolean;
  problem: string | null;
  onCancel: () => void;
  onSubmit: () => void;
  extraAction?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <form
      className="editor"
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <h3>{title}</h3>
      {children}
      {problem && (
        <p role="alert" className="editor__problem">
          {problem}
        </p>
      )}
      <div className="editor__actions">
        {extraAction}
        <button className="b" type="button" onClick={onCancel}>
          {t("projectSettings.cancel")}
        </button>
        <button className="b b--primary" type="submit" disabled={busy}>
          {busy ? t("projectSettings.saving") : t("projectSettings.save")}
        </button>
      </div>
    </form>
  );
}

export function DescriptionEditor({
  page,
  staff,
  onDone,
}: {
  page: Page;
  staff: Staff;
  onDone: (saved: boolean) => void;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState(page.description);
  const save = useSave(() => onDone(true));
  return (
    <Editor
      title={t("edit.description")}
      {...save}
      onCancel={() => onDone(false)}
      onSubmit={() =>
        save.run(() =>
          call(
            api.PATCH("/api/projects/{project_id}/content", {
              params: { path: { project_id: staff.project_id } },
              body: { row_version: staff.row_version, description: text },
            }),
          ),
        )
      }
    >
      <div className="field">
        <label className="sr" htmlFor="ed-desc">
          {t("edit.description")}
        </label>
        <textarea
          className="textarea"
          id="ed-desc"
          rows={7}
          value={text}
          onChange={(e) => setText(e.target.value)}
          autoFocus
        />
        <p className="hint">{t("edit.descriptionHint")}</p>
      </div>
    </Editor>
  );
}

type DetailType = Schemas["DetailTypeOut"];

export function DetailsEditor({
  page,
  staff,
  onDone,
}: {
  page: Page;
  staff: Staff;
  onDone: (saved: boolean) => void;
}) {
  const { t } = useTranslation();
  const [types, setTypes] = useState<DetailType[]>([]);
  const [projectTypes, setProjectTypes] = useState<
    Schemas["ProjectTypeOption"][]
  >([]);
  const [projectType, setProjectType] = useState(page.project_type_key);
  const [rows, setRows] = useState(() =>
    page.details.map((d) => ({ key: d.key, value: String(d.value) })),
  );
  const save = useSave(() => onDone(true));
  useEffect(() => {
    call(api.GET("/api/detail-types")).then(setTypes, () => setTypes([]));
    call(api.GET("/api/project-types")).then(
      (found) => setProjectTypes(found.types),
      () => setProjectTypes([]),
    );
  }, []);
  const typeOf = (key: string) => types.find((type) => type.key === key);
  const unused = types.filter(
    (type) => !rows.some((row) => row.key === type.key),
  );
  return (
    <Editor
      title={t("edit.details")}
      {...save}
      onCancel={() => onDone(false)}
      onSubmit={() =>
        save.run(() =>
          call(
            api.PATCH("/api/projects/{project_id}/content", {
              params: { path: { project_id: staff.project_id } },
              body: {
                row_version: staff.row_version,
                details: rows.filter((row) => row.value.trim() !== ""),
                ...(projectType !== page.project_type_key
                  ? { project_type: projectType }
                  : {}),
              },
            }),
          ),
        )
      }
    >
      <ul className="facts-edit">
        <li>
          <label className="lbl" htmlFor="fv-project-type">
            {t("page.projectType")}
          </label>
          <select
            className="select"
            id="fv-project-type"
            value={projectType}
            onChange={(e) => setProjectType(e.target.value)}
          >
            {(projectTypes.length
              ? projectTypes
              : [{ key: page.project_type_key, label: page.project_type }]
            ).map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
          <span />
        </li>
        {rows.map((row, i) => {
          const type =
            typeOf(row.key) ?? page.details.find((d) => d.key === row.key);
          const label = type && "label" in type ? type.label : row.key;
          const kind = type?.type ?? "text";
          const id = `fv-${row.key}`;
          const set = (value: string) =>
            setRows(rows.map((r, j) => (j === i ? { ...r, value } : r)));
          return (
            <li key={row.key}>
              <label className="lbl" htmlFor={id}>
                {label}
              </label>
              {kind === "area" ? (
                <div className="unit">
                  <input
                    className="input"
                    id={id}
                    type="number"
                    min="0"
                    step="0.01"
                    inputMode="decimal"
                    value={row.value}
                    onChange={(e) => set(e.target.value)}
                  />
                  <span>m²</span>
                </div>
              ) : (
                <input
                  className="input"
                  id={id}
                  type={kind === "date" ? "date" : "text"}
                  value={row.value}
                  onChange={(e) => set(e.target.value)}
                />
              )}
              <button
                className="iconbtn"
                type="button"
                aria-label={t("edit.removeDetail", { name: label })}
                onClick={() => setRows(rows.filter((_, j) => j !== i))}
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>
      {unused.length > 0 && (
        <label className="add-detail">
          <span className="sr">{t("edit.addDetail")}</span>
          <select
            className="select"
            value=""
            onChange={(e) =>
              e.target.value &&
              setRows([...rows, { key: e.target.value, value: "" }])
            }
          >
            <option value="">+ {t("edit.addDetail")}</option>
            {unused.map((type) => (
              <option key={type.key} value={type.key}>
                {type.label}
              </option>
            ))}
          </select>
        </label>
      )}
    </Editor>
  );
}

/** The meeting's day and times as the office's clock shows them. */
function officeClock(iso: string, timeZone: string) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(iso))
      .map((part) => [part.type, part.value]),
  );
  return {
    day: `${parts.year}-${parts.month}-${parts.day}`,
    time: `${parts.hour}:${parts.minute}`,
  };
}

export function MeetingEditor({
  page,
  staff,
  onDone,
}: {
  page: Page;
  staff: Staff;
  onDone: (saved: boolean) => void;
}) {
  const { t } = useTranslation();
  const meeting = page.next_meeting;
  const start = meeting
    ? officeClock(meeting.starts_at, page.timezone)
    : { day: "", time: "" };
  const end = meeting
    ? officeClock(meeting.ends_at, page.timezone)
    : { day: "", time: "" };
  const [form, setForm] = useState({
    title: meeting?.title ?? "",
    day: start.day,
    start: start.time,
    end: end.time,
    location: meeting?.location ?? "",
    link: meeting?.link ?? "",
  });
  const set =
    (field: keyof typeof form) => (e: { target: { value: string } }) =>
      setForm({ ...form, [field]: e.target.value });
  const save = useSave(() => onDone(true));
  const path = { params: { path: { project_id: staff.project_id } } };
  return (
    <Editor
      title={meeting ? t("edit.meeting") : t("edit.scheduleMeeting")}
      {...save}
      onCancel={() => onDone(false)}
      onSubmit={() =>
        save.run(() =>
          call(
            api.PUT("/api/projects/{project_id}/meeting", {
              ...path,
              body: {
                row_version: staff.row_version,
                title: form.title,
                day: form.day,
                start: form.start,
                end: form.end || null,
                location: form.location || null,
                link: form.link || null,
              },
            }),
          ),
        )
      }
      extraAction={
        meeting && (
          <button
            className="b b--ghost b--danger"
            type="button"
            style={{ marginRight: "auto" }}
            onClick={() =>
              save.run(() =>
                call(
                  api.DELETE("/api/projects/{project_id}/meeting", {
                    params: {
                      path: { project_id: staff.project_id },
                      query: { row_version: staff.row_version },
                    },
                  }),
                ),
              )
            }
          >
            {t("edit.removeMeeting")}
          </button>
        )
      }
    >
      <div className="field">
        <label htmlFor="m-title">{t("edit.subject")}</label>
        <input
          className="input"
          id="m-title"
          value={form.title}
          onChange={set("title")}
          maxLength={40}
          required
          autoFocus
        />
        <p className="hint">{t("edit.subjectHint")}</p>
      </div>
      <div className="row3">
        <div className="field">
          <label htmlFor="m-date">{t("edit.day")}</label>
          <input
            className="input"
            type="date"
            id="m-date"
            value={form.day}
            onChange={set("day")}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="m-start">{t("edit.start")}</label>
          <input
            className="input"
            type="time"
            id="m-start"
            value={form.start}
            onChange={set("start")}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="m-end">{t("edit.end")}</label>
          <input
            className="input"
            type="time"
            id="m-end"
            value={form.end}
            onChange={set("end")}
          />
        </div>
      </div>
      <div className="row2">
        <div className="field">
          <label htmlFor="m-loc">{t("edit.location")}</label>
          <input
            className="input"
            id="m-loc"
            value={form.location}
            onChange={set("location")}
            maxLength={60}
          />
        </div>
        <div className="field">
          <label htmlFor="m-link">{t("edit.link")}</label>
          <input
            className="input"
            type="url"
            id="m-link"
            value={form.link}
            onChange={set("link")}
            placeholder="https://meet.google.com/…"
          />
        </div>
      </div>
      <p className="hint">{t("edit.timeZoneHint")}</p>
    </Editor>
  );
}

export function NotesEditor({
  page,
  staff,
  index,
  onDone,
}: {
  page: Page;
  staff: Staff;
  index: number;
  onDone: (saved: boolean) => void;
}) {
  const { t } = useTranslation();
  const stage = page.stages[index]!;
  const [notes, setNotes] = useState(stage.notes);
  const save = useSave(() => onDone(true));
  return (
    <Editor
      title={t("edit.notes")}
      {...save}
      onCancel={() => onDone(false)}
      onSubmit={() =>
        save.run(() =>
          call(
            api.PUT("/api/projects/{project_id}/stages/{position}/notes", {
              params: {
                path: {
                  project_id: staff.project_id,
                  position: stage.position,
                },
              },
              body: { row_version: staff.row_version, notes },
            }),
          ),
        )
      }
    >
      <div className="field">
        <label className="sr" htmlFor={`ed-notes-${index}`}>
          {t("edit.notes")}
        </label>
        <textarea
          className="textarea"
          id={`ed-notes-${index}`}
          rows={4}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={t("edit.notesPlaceholder")}
          autoFocus
        />
      </div>
    </Editor>
  );
}
