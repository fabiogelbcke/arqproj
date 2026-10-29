# Pull requests

How pull requests for the rewrite are opened and reviewed. `AGENTS.md` keeps the
review guidelines (what any reviewer checks); this file holds the rest.

## Code review

Pull requests for the rewrite go into the `staging` branch. Three reviewers
are available (Fabio, 28 Oct 2026: Codex reviews use up the Codex plan, the
Claude plan has room). None of them has the author's conversation, and the
author's session never reviews its own change in their place.

- **Claude on GitHub** (`.github/workflows/claude-review.yml`): start a comment
  on the pull request with `@claude review` (after the "🤖 Claude:" prefix, from
  an agent), or `@claude review high-risk` for the larger model. It reviews only
  pull requests opened by someone with write access: the repository is public. It reviews with the instructions in the workflow, comments on
  the lines it finds problems in, and posts a summary. Its runs are in the
  repository's Actions tab, so what it was asked and what it did can be
  checked (Fabio, 28 Oct 2026: more auditable than a review started from a
  session). Anyone with write access can ask for it, so pull requests from
  Codex or Cowork get it too.
- **A local fresh reviewer**, for documentation-only pull requests and file
  moves: the author's Claude Code session starts a new agent with the brief
  below, changing only the pull request number.
- **Codex** on GitHub (comment `@codex review`; marking a draft ready does not
  reliably trigger it). A Codex round that hasn't come back in 15 minutes is
  asked for again.

Ask for each round as soon as its commit is pushed, without waiting for CI: the
two run side by side (Fabio, 23 Oct 2026). When the review rounds end and CI has
passed, the pull request goes to Fabio, who reviews and merges.

The local fresh reviewer's brief:

> Review pull request #N in fabiogelbcke/arqproj. You did not write it. Read
> `AGENTS.md` (its "Review guidelines"), `docs/pull-requests.md` and the
> documentation the description's Context section links, then the pull request
> through `gh pr view N` and `gh pr diff N`; read any other file you need on its
> branch. Skip the "Git workflow" steps: you change nothing. Look for bugs and
> for mismatches with the documentation, keeping to real problems. Post exactly
> one comment with `gh pr comment N`, starting "🤖 Claude: fresh-agent review",
> listing findings as P1 (serious), P2 (worth fixing) or P3 (minor), or saying
> it is clean (👍). Do not edit files, push, approve or merge.

Who reviews (when a pull request fits more than one row, the riskiest wins: a
UI change to the sign-in screens is high-risk):

| Pull request | Reviews |
| --- | --- |
| An extremely simple change (a typo, a one-line copy fix, a doc wording tweak) | None. Say so in the description. |
| Documentation only, file moves | One local fresh review. A documentation-only change after a clean review needs no other. |
| UI changes, low-risk and very simple code changes | `@claude review` only, at most 2 rounds (1 for very simple changes). |
| High-risk changes to anything: security, data isolation, migrations, deploys, money, email sending, sign-in, privacy | Before each Codex round, a Claude review (`@claude review high-risk`) of the same changes, and its findings fixed; then Codex, even if Claude came back clean: a second model catches different things. At most 3 Codex rounds; a 4th only if the 3rd found something critical, such as a data leak or a security hole (Fabio, 28 Oct 2026). |

How many rounds:

- Request another review after fixes while the last round found something that
  was fixed because it was serious or realistic for our setup. Declined or
  marginal findings do not count.
- Stop when a round brings only declined or marginal findings, or comes back
  clean (👍).
- A serious (P1) finding always gets one more round after its fix.
- A high-risk pull request stops only after a Codex round.
- The limits above stand (Fabio, 18 Oct 2026: reviews cost tokens). If real
  issues are still appearing at the limit, the pull request is too big or its
  design is unsettled: pause and discuss it with Fabio.
- When Codex is out of quota, a high-risk pull request goes through its rounds
  with Claude reviews, its description says "Codex review pending", and
  Fabio decides whether to merge before it. Codex reviews it once it is back,
  merged or not.

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
