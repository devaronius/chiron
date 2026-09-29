# chiron

The aiOS framework that `bootstrap-ideaverse` installs into other repos. Read `README.md`
first — it covers the payload layout, the install/upgrade model and the release procedure.

## Git

- **Rebase onto `main`, never merge it in.** A branch contains only its own work; a merge
  commit drags another branch's history in and the PR stops showing only your change.
- **Title commits and PRs `type(ticket): summary`** — the issue number **without** a `#`:
  `fix(14): …`, not `fix(#14): …`. GitHub appends the PR number itself on squash merge, so
  `#` is reserved for the one it adds.
- Types: `feat` · `fix` · `refactor` · `docs` · `build` · `chore` · `test`.
- **No issue?** Use a short scope naming the area — `docs(readme):`, `chore(deps):` — or omit
  the scope: `build: pin json_serializable`. **Don't invent a number** to satisfy the pattern.
- **The body carries the why.** The subject says what changed; the body says what the code was
  wrong about before, what you decided against, and anything a reviewer would otherwise have
  to reconstruct. A commit reversing an earlier decision says so, and why.
- Force-push with **`--force-with-lease`**, never plain `--force`. Take a backup ref first on
  anything non-trivial, and re-run `tools/selftest.sh` after a rebase — a conflict-free rebase
  can still produce a broken tree.

`.github/PULL_REQUEST_TEMPLATE.md` is applied automatically. **Departures from the ticket** and
**Known, not addressed** are the two sections that earn their keep; write `None.` rather than
deleting them.

## What this repo is careful about

- **`VERSION` covers `aiOS/`, `seeds/` and `skills/` as one unit.** Repo meta — `README.md`,
  `.github/`, `tools/` — is not payload and needs no CHANGELOG entry.
- **Bumping `VERSION` and tagging is the release step, not a PR step.** See README
  § *Contributing / releasing*; `chiron-release.py` also re-pins the marketplace plugin
  entries, and a stale one strands installed users on whatever version they first got.
- **The installer overwrites files in a vault holding months of someone's notes.**
  `tools/selftest.sh` must be green before anything else — especially its CONFLICT and
  IDEMPOTENCE scenarios, which are the two whose failure destroys work silently.
- **A consumer may carry a local edit of a file you change.** If so, say so under *Known, not
  addressed* so the upgrade path is a reconciliation rather than a surprise.
