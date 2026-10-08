# hook tests

```bash
aiOS/tools/run-tests.sh                                       # every shipped suite
aiOS/tools/run-tests.sh --coverage                            # the same, with line coverage
python3 -m unittest discover -s .claude/hooks/tests           # this suite only
```

Stdlib `unittest`, no dependencies. Each hook is loaded by path — their filenames are
hyphenated and so not legal module names — and their functions are called directly rather
than launched as subprocesses. **Nothing here shells out to a tracker, the remote or the
real vault**, so the suite passes regardless of what is uncommitted in your working tree.

| Hook | Event | Covered |
|---|---|---|
| `researcher-scope.py` | `PreToolUse` | command splitting, the Bash allowlist, interpreter and curl rules, write scope, exit-code contract |
| `inspector-scope.py` | `PreToolUse` | the Bash allowlist, git subcommands, the configured client and build commands, write scope |
| `open-items-lane.py` | `SessionStart` | the digest, the always-exit-0 contract, the inner timeout |

## What a scope hook is for

A scope hook is the difference between an agent's constitution and its boundary. Both agents
carry rules in prose — one note, no raw git, never vote — and prose is what an unattended run
is free to reinterpret at 2am. The hook refuses the call before it runs.

So the tests here are not about tidy code. Each one pins a route that was open: a command
splitter that treated a quoted `|` as a pipe and refused legitimate work; a heredoc that
smuggled an interpreter past an allowlist; a relative path that meant different things
depending on the caller's working directory; a `scratchpad` matched as a substring, which
silently switched the whole write scope off for a checkout that happened to live under a
directory of that name.

**Flags are allowlisted, never blocklisted.** Blocking `--update` was tried first and is not
a boundary: `argparse` accepts an unambiguous abbreviation, and a shell hands the hook one
spelling while `argparse` receives another. Enumerating what *may* be passed survives both,
because an obfuscated flag is still an unrecognised `-…` word.

**And it is not airtight.** The splitter does not split on `&` or inside `$(…)`, so a command
hiding there is never inspected. The allowlist closes the innocent and the abbreviated cases,
not a determined one — worth knowing before you treat a hook as a sandbox.

## Wiring assertions are conditional

chiron ships the hooks but never writes a consumer's harness settings file — wiring a hook is
a decision a human makes, not one an installer makes for them. So the tests that check an
event registration **skip with a reason** on a repo that has not wired them, and assert
properly on one that has.
