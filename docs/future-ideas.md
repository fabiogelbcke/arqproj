# Future ideas

A running list of possibilities to explore, started 15 October 2026. Add ideas
here as they come up; they do not need a full specification or a delivery date.
This is not committed scope or a second implementation plan. When an idea is
selected for implementation, record the decision in the
[implementation plan](multi-tenant-implementation-plan.md) and any changed
decision in the [decision changelog](decision-changelog.md).

## Project-page templates and branding

- Let each office choose from different project-page templates and select a
  colour scheme that matches its branding.
- Basic branding is already in the implementation plan; this idea extends it
  with more layouts and customization choices.
- More advanced customization might be a premium feature. Which options belong
  in the base product versus a paid tier remains open.

## Multiple users and more granular permissions

- Support teams working within one office, with different responsibilities and
  access levels. The current plan already includes basic owner/member roles;
  this extends that model rather than postponing basic multi-user support.
- Contractors might only access assigned projects or upload into specific
  stages, without access to all project files.
- Financial documents, such as invoices and monetary proposals, may need
  restricted access even within the same office.
- Explore how restricted content appears: show a locked item or an indication
  that content is unavailable, versus hide it entirely. Decide what information
  can be shown without revealing confidential document names or details.
- Portal restrictions and permissions in the office's own Google Drive need to
  be considered together; hiding something in the portal does not remove direct
  Drive access.

## Organizing projects across a team

- Make it easier to find and organize projects when several architects work in
  the same office.
- Possibilities include tabs per architect, filters by responsible professional,
  and saved searches or default views such as "my projects".
- Keep organization separate from authorization: a default view can help someone
  focus on their work without necessarily restricting access to other projects.

## Searchable project themes and tags

- Let staff add `#tags` or keywords to a project's description so projects
  with related themes can be grouped, searched and filtered across the painel.
- Suggest existing terms while editing to avoid several spellings for the same
  theme (for example, natural materials or integrated spaces).
- Explore inline hashtags versus a separate keyword field. Keep the project
  description readable while making the themes reusable for search and filters.

## WhatsApp updates

- Add project-update notifications through WhatsApp alongside email.
- **Interest: potentially soon**, rather than a distant enhancement; timing is
  still undecided.
- Explore recipient preferences, batching, delivery costs and the provider's
  consent/template requirements before choosing an implementation.
- Decide whether recipients choose one channel or can receive both, and how to
  avoid unwanted duplicate notifications.
