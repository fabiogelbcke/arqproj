// The longest each field can be today, so the preview's "long" is the longest a
// real page can show. The editors' own maxLength (Editors.tsx, StageEditing.tsx)
// and the server's (backend/web/page_edit.py, page_stages.py) are the source;
// preview.test.tsx opens the editors and fails if these drift from them.
export const LIMITS = {
  description: 5000, // DESCRIPTION_MAX; the editor's text area has no limit of its own
  stageTitle: 80, // STAGE_TITLE_MAX, and the editors' maxLength
  meetingTitle: 40, // the editor's maxLength (the server allows 200)
  meetingLocation: 60, // the editor's maxLength (the server allows 200)
} as const;
