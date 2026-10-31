// The example project shows what a real project page can show (plan section 16):
// when the page gains something (a field in the API's answer), this fails until
// the example fills it in (fixture.ts, exampleApi.ts) or it is listed below with
// the reason the example leaves it out.
import { describe, expect, it } from "vitest";

import openapi from "../../api/openapi.json";
import { EXAMPLE_SLUG } from "./address";
import { installExampleApi } from "./exampleApi";

type Fields = Record<string, unknown>;

const schemas = openapi.components.schemas as unknown as Record<string, { properties: Fields }>;
const fieldsOf = (schema: string) => Object.keys(schemas[schema]!.properties);

/** A value the page would show nothing for. */
const empty = (value: unknown) =>
  value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);

/** The fields of `schema` empty in every one of `shown`, minus those left out on purpose. */
export function unfilled(schema: string, shown: Fields[], leftOut: Record<string, string>): string[] {
  return fieldsOf(schema).filter((field) => !(field in leftOut) && shown.every((item) => empty(item[field])));
}

// What the example leaves out, and why.
const PAGE_LEFT_OUT = {
  in_proposal: "a proposal not yet accepted shows only the proposal; the example is past it",
  proposal: "only while in proposal; once accepted, `proposal_url` (shown)",
  current_position: "the previous release's, unread by this page",
  staff: "the staff view: shown to signed-in staff, tested in example.test.tsx",
};
const FILE_LEFT_OUT = {
  clash: "a naming problem for staff to fix, not something to show off",
};
const FILES_LEFT_OUT = {
  reference: "a support code shown when Drive can't be read",
};

async function exampleAnswers() {
  installExampleApi();
  const read = async (path: string) => (await (await fetch(path)).json()) as Fields;
  const page = await read(`/api/pages/${EXAMPLE_SLUG}`);
  const files = await read(`/api/pages/${EXAMPLE_SLUG}/files`);
  return { page, files };
}

describe("the example project keeps up with the project page", () => {
  it("fills in everything a page shows", async () => {
    const { page, files } = await exampleAnswers();
    expect(unfilled("PageOut", [page], PAGE_LEFT_OUT)).toEqual([]);
    expect(unfilled("PageFilesOut", [files], FILES_LEFT_OUT)).toEqual([]);
    const stages = page.stages as Fields[];
    expect(unfilled("StageOut", stages, {})).toEqual([]);
    expect(unfilled("MeetingOut", [page.next_meeting as Fields], { link: "the meeting is in person" })).toEqual([]);
    // Every kind of file state somewhere: a version, "Atualizado", older versions.
    const shown = (files.stages as { groups: { files: Fields[] }[] }[]).flatMap((stage) =>
      stage.groups.flatMap((group) => group.files),
    );
    expect(unfilled("FileOut", shown, FILE_LEFT_OUT)).toEqual([]);
    expect(shown.some((file) => file.updated === true)).toBe(true);
  });

  it("notices a field the example leaves empty", () => {
    // The check itself: a page without "Responsável" is caught.
    const page = Object.fromEntries(fieldsOf("PageOut").map((field) => [field, "x"]));
    expect(unfilled("PageOut", [{ ...page, team: [] }], PAGE_LEFT_OUT)).toEqual(["team"]);
    expect(unfilled("PageOut", [{ ...page, team: ["Ana"] }], PAGE_LEFT_OUT)).toEqual([]);
  });
});
