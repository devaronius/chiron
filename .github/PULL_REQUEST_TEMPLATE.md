<!--
Delete any section that genuinely does not apply. An empty heading is worse
than no heading. "Departures" and "Known, not addressed" are the two that
carry the most weight — they are cheaper stated than discovered in review.
-->

## Type

<!-- Check one. Matches the commit prefix, so the PR title can be reused verbatim.

     Title this PR `type(ticket): summary` — the issue number with NO `#`:
       fix(14): stop the exists lookup missing snake_case basenames
     not `fix(#14):`. GitHub appends the PR number itself on squash merge.
     No issue? Use an area scope (`docs(readme):`, `chore(deps):`) or drop the
     scope entirely. Do not invent a number to satisfy the pattern. -->

- [ ] `feat` — a new capability
- [ ] `fix` — a bug in existing behaviour
- [ ] `refactor` — behaviour unchanged by design
- [ ] `docs` — documentation only
- [ ] `build` — toolchain or packaging
- [ ] `chore` — repo tooling, no payload change
- [ ] `test` — selftest only

## What and why

<!-- Link the issue if there is one. One paragraph on the problem, not the
     solution. Chiron is installed into other people's repos, so say which
     consumer behaviour changes — or that none does. -->

## What changed

<!-- Bullets, one per decision a reviewer would otherwise have to reconstruct.
     Say why, not just what. -->

-

## Departures from the ticket

<!-- Anywhere the implementation does NOT match what was asked, and why. Scope
     you added or left out, a decision the issue left unspecified. Name the one
     a reviewer should push back on.

     If there were none, write "None." — do not delete this section. -->

## Verification

<!-- What you actually ran, and what it reported. Numbers beat adjectives.
     If something is unverified, say so plainly here. -->

- [ ] `bash tools/selftest.sh` — passed N, failed 0
- [ ] `claude plugin validate .` — if `.claude-plugin/` changed
- [ ] Ran against a real vault, if the change touches `aiOS/scripts/`

## Payload and versioning

<!-- VERSION covers aiOS/, seeds/ and skills/ as one unit. Repo meta — README,
     .github/, tools/ — is not payload and needs no CHANGELOG entry. -->

- [ ] CHANGELOG entry added, or **N/A** (no payload change)
- [ ] `migrations.json` entry for any rename or retirement, or **N/A**
- [ ] `VERSION` left alone — bumping and tagging is the release step, not this PR

## Known, not addressed

<!-- Pre-existing breakage you touched near but deliberately left alone, scope
     you cut, anything you could not verify. An installed consumer carrying a
     local edit of a file you changed belongs here too. -->

## Ready for review

<!-- Tick honestly. An unticked box with a sentence explaining why is a useful
     PR; a fully ticked box that isn't true is not. -->

- [ ] Branch is **rebased** onto current `main`, not merged — the diff shows only my work
- [ ] Every changed line traces to the request — no drive-by "improvements" to adjacent code
- [ ] Nothing speculative: no abstraction for single-use code, no unrequested flexibility
- [ ] Orphans my change created are gone; pre-existing dead code left alone (mentioned above)
- [ ] **Departures** is filled in, or says `None.`
- [ ] Verification above was actually run, and its output is what I reported
- [ ] I have read my own diff end to end
