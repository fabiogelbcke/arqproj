# Pull requests

How pull requests for the rewrite are opened and reviewed. `AGENTS.md` keeps the
review guidelines (what any reviewer checks); this file holds the rest.

## Code review (Codex)

Pull requests for the rewrite go into the `staging` branch. Codex reviews them on
GitHub (comment `@codex review`; marking a draft ready does not reliably trigger
it). When the review rounds end, the pull request goes to Fabio, who reviews and
merges.

How many rounds:

- Request another review after fixes while the last round found something that
  was fixed because it was serious or realistic for our setup. Declined or
  marginal findings do not count.
- Stop when a round brings only declined or marginal findings, or comes back
  clean (👍).
- A serious (P1) finding always gets one more round after its fix.
- At most 2 rounds for UI changes and for low-risk backend changes, and at most
  4 for high-risk changes to anything (security, data isolation, migrations,
  deploys, money or email sending) (Fabio, 18 Oct 2026: reviews cost tokens).
  If real issues are still appearing at the limit, the pull request is too big
  or its design is unsettled: pause and discuss it with Fabio.
- Documentation-only or file-move pull requests get one review, and a
  documentation-only change after a clean review needs none.

- Fix serious findings and those realistic for our actual setup.
- Do not implement findings that are nitpicky, guard against configurations we
  never create, or would add code without real benefit. Reply on the comment
  explaining why, and list it in the pull request description.
- Reproduce a finding before fixing it.

## Pull request description

Start every pull request description with a **Context** section linking the
documentation the change is meant to satisfy, so reviewers know what to check it
against. Link the specific section (heading anchor), not just the file: for
example a plan section, a decision in the register, a changelog entry, a step or
milestone, an issue, or a README section the change updates. Then say in one line
each what that documentation calls for, what was built, and what was deliberately
left out or deferred, with the reason. If no documentation covers the change,
say so.

## Screenshots for UI changes

A pull request that changes what the staff app shows includes a **Screenshots**
section: run `make screenshots PR=<number>`, which captures the screens
(desktop and phone; dark where relevant) from the built app on fresh fictional
data, publishes them to the `screenshots` branch (never merged; one folder per
pull request, so images stay out of the code history) and prints the table to
paste. Paste only the rows for screens the change affected or could have
affected (for example every screen that uses a changed component or stylesheet
rule), not every screen the command captured. Add screens to
`frontend/e2e/screenshots.spec.ts` as the app grows. Look at the images yourself
only when checking something visual.
