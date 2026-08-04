#!/usr/bin/env bash
# selftest — exercise chiron-install.py against throwaway repos.
#
# The installer overwrites and deletes files inside a vault holding months of someone's
# notes, and every interesting path (adopt with no manifest, rename migration,
# pristine-only retirement, conflict detection) is the kind of logic that looks right and
# is not. A dry run only proves what the PLAN says; the bug class to fear is "plan says one
# thing, apply does another", so every assertion here runs against a real applied tree.
#
# The two scenarios that matter most are CONFLICT and IDEMPOTENCE. Everything else being
# wrong wastes time; those two being wrong destroys work silently.
#
# Self-contained: fixtures are built from chiron itself, so this runs on any checkout.
#
# Usage: tools/selftest.sh [--keep]

set -uo pipefail

CHIRON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/chiron-selftest.XXXXXX")"
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

PASS=0; FAIL=0
ok   () { PASS=$((PASS+1)); printf '    \033[32m✓\033[0m %s\n' "$1"; }
bad  () { FAIL=$((FAIL+1)); printf '    \033[31m✗\033[0m %s\n' "$1"; }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (want '$3', got '$2')"; fi; }
head1() { printf '\n\033[1m%s\033[0m\n' "$1"; }
inst () { python3 "$CHIRON/tools/chiron-install.py" "$@"; }

cleanup() { if [ "$KEEP" = 1 ]; then echo "kept: $WORK"; else rm -rf "$WORK"; fi; }
trap cleanup EXIT

# How many lines under plan section $2 mention $3.
sect () { awk -v want="$2" '/^[A-Z]+ /{cur=$1} cur==want && /^  /{print}' <<<"$1" | grep -c -- "$3"; }

new_repo () {
  local d="$WORK/$1"; mkdir -p "$d"
  ( cd "$d" && git init -q && git config user.email t@t && git config user.name t )
  echo "$d"
}

# ── 1. install ────────────────────────────────────────────────
head1 "1. install — empty repo"
T=$(new_repo install)
inst --target "$T" --apply --project-name "Acme" --project-domain "Payments." --roles "Dev,QA" >/dev/null
[ -f "$T/docs/aiOS/scripts/vault_lib.py" ]     && ok "scripts installed"         || bad "scripts installed"
[ -f "$T/docs/aiOS/.chiron-install.json" ]     && ok "manifest written"          || bad "manifest written"
[ -f "$T/docs/project-brief.md" ]              && ok "briefing seeded"           || bad "briefing seeded"
[ -f "$T/.claude/skills/wiki-sync/SKILL.md" ]  && ok "skills installed"          || bad "skills installed"
[ -f "$T/.claude/agents/librarian.md" ]        && ok "agent adapter installed"   || bad "agent adapter installed"
[ -d "$T/docs/ideaVerse/efforts/works" ]       && ok "ACE skeleton scaffolded"   || bad "ACE skeleton scaffolded"
if [ -e "$T/.claude/skills/bootstrap-ideaverse" ]
  then bad "installer must not be copied into the target"
  else ok "installer not copied into target"; fi
if grep -q '{{' "$T/docs/project-brief.md"
  then bad "seed tokens substituted"
  else ok "seed tokens substituted"; fi
if grep -rq '{{PROJECT_NAME}}\|{{VAULT_PREFIX}}' "$T/docs/aiOS/" "$T/.claude/skills/"
  then bad "managed payload carries no install tokens"
  else ok "managed payload carries no install tokens"; fi
if python3 -c "import json;json.load(open('$T/docs/aiOS/aios.config.json'))" 2>/dev/null
  then ok "aios.config.json is valid JSON"; else bad "aios.config.json is valid JSON"; fi
( cd "$T" && python3 docs/aiOS/scripts/wiki-sync.py --update >/dev/null 2>&1 )
out=$( cd "$T" && python3 docs/aiOS/scripts/wiki-sync.py 2>&1 )
grep -q "Wiki is in sync" <<<"$out" && ok "wiki baseline in sync" || bad "wiki baseline in sync"
out=$( cd "$T" && python3 docs/aiOS/scripts/vault-lint.py 2>&1 )
if grep -q "FATAL" <<<"$out"; then bad "fresh install lints without FATAL"
  else ok "fresh install lints without FATAL"; fi
if ( cd "$T" && python3 docs/aiOS/scripts/vault-report.py >/dev/null 2>&1 )
  then ok "vault-report runs without coverage-gap installed"
  else bad "vault-report runs without coverage-gap installed"; fi

# ── 2. idempotence ────────────────────────────────────────────
head1 "2. idempotence — apply twice writes nothing"
snap () { ( cd "$1" && find docs .claude -type f -exec shasum {} \; | sort | shasum ); }
before=$(snap "$T")
out=$(inst --target "$T" --apply 2>&1); rc=$?
check "second apply changes no file" "$(snap "$T")" "$before"
check "second apply exits 0"         "$rc" "0"
grep -q "Nothing to do" <<<"$out" && ok "second apply reports nothing to do" \
                                  || bad "second apply reports nothing to do"

# ── fake 1.1.0 (add / change / rename / retire) ───────────────
FAKE="$WORK/chiron-1.1.0"
mkdir -p "$FAKE"
( cd "$CHIRON" && tar cf - --exclude=./.git --exclude=./.git/* . ) | ( cd "$FAKE" && tar xf - )
printf '# added in 1.1.0\n' > "$FAKE/aiOS/templates/new-thing.template.md"
printf '\n# changed in 1.1.0\n' >> "$FAKE/aiOS/scripts/note-review.py"
mv "$FAKE/aiOS/templates/schedule.template.md" "$FAKE/aiOS/templates/routine.template.md"
rm -f "$FAKE/aiOS/templates/api-note.template.md"
cat > "$FAKE/migrations.json" <<'JSON'
[{"version": "1.1.0",
  "renames": [["{vault}/aiOS/templates/schedule.template.md",
               "{vault}/aiOS/templates/routine.template.md"]],
  "retires": ["{vault}/aiOS/templates/api-note.template.md"],
  "note": "selftest fixture"}]
JSON
printf '# Changelog\n\n## [1.1.0] — selftest fixture\n' > "$FAKE/CHANGELOG.md"
python3 "$FAKE/tools/chiron-release.py" --set 1.1.0 >/dev/null || bad "fixture release failed"
UP () { python3 "$FAKE/tools/chiron-install.py" "$@"; }

# ── 3. adopt ──────────────────────────────────────────────────
head1 "3. adopt — vault with no manifest, classified by hash history"
T2=$(new_repo adopt)
inst --target "$T2" --apply --project-name "Legacy" >/dev/null
printf '\n# MY OWN TWEAK\n' >> "$T2/docs/aiOS/scripts/research-capture.py"
printf '\nMy own paragraph.\n' >> "$T2/docs/project-brief.md"
mine_rc=$(shasum < "$T2/docs/aiOS/scripts/research-capture.py")
rm -f "$T2/docs/aiOS/.chiron-install.json"        # now indistinguishable from a pre-chiron vault

out=$(UP --target "$T2" --plan 2>&1)
grep -q "mode: adopt" <<<"$out" && ok "detected adopt mode" || bad "detected adopt mode"
check "pristine changed file → UPDATE"  "$(sect "$out" UPDATE   'note-review.py')"      "1"
check "user-edited file → CONFLICT"     "$(sect "$out" CONFLICT 'research-capture.py')" "1"
check "edited seed → REVIEW"            "$(sect "$out" REVIEW   'project-brief.md')"    "1"
grep -q "matches a previously shipped version" <<<"$out" \
  && ok "pristine verdict cites the hash history" || bad "pristine verdict cites the hash history"
grep -q "matches no version chiron ever shipped" <<<"$out" \
  && ok "conflict verdict says why" || bad "conflict verdict says why"

UP --target "$T2" --apply >/dev/null 2>&1
check "conflicted file untouched by apply" "$(shasum < "$T2/docs/aiOS/scripts/research-capture.py")" "$mine_rc"
grep -q "My own paragraph" "$T2/docs/project-brief.md" && ok "seeded edit preserved" \
                                                       || bad "seeded edit preserved"
[ -f "$T2/docs/aiOS/.chiron-install.json" ] && ok "adopt records a manifest" || bad "adopt records a manifest"

# ── 4. upgrade ────────────────────────────────────────────────
head1 "4. upgrade — migrations then three-way diff"
T3=$(new_repo upgrade)
inst --target "$T3" --apply --project-name "Up" >/dev/null
printf '\n# MY LOCAL EDIT\n' >> "$T3/docs/aiOS/scripts/vault-lint.py"
mine=$(shasum < "$T3/docs/aiOS/scripts/vault-lint.py")

out=$(UP --target "$T3" --plan 2>&1)
grep -q "mode: upgrade" <<<"$out" && ok "detected upgrade mode" || bad "detected upgrade mode"
check "new file → ADD"         "$(sect "$out" ADD      'new-thing.template.md')" "1"
check "changed file → UPDATE"  "$(sect "$out" UPDATE   'note-review.py')"        "1"
check "edited file → CONFLICT" "$(sect "$out" CONFLICT 'vault-lint.py')"         "1"
grep -q "1.1.0: 1 rename(s), 1 retire(s)" <<<"$out" && ok "migrations listed in plan" \
                                                    || bad "migrations listed in plan"

UP --target "$T3" --apply >/dev/null 2>&1
[ -f "$T3/docs/aiOS/templates/new-thing.template.md" ] && ok "added file written" || bad "added file written"
grep -q "changed in 1.1.0" "$T3/docs/aiOS/scripts/note-review.py" \
  && ok "changed file updated" || bad "changed file updated"
[ -f "$T3/docs/aiOS/templates/routine.template.md" ] && ok "rename landed at new path" \
                                                      || bad "rename landed at new path"
if [ -e "$T3/docs/aiOS/templates/schedule.template.md" ]
  then bad "rename left nothing at the old path"; else ok "rename left nothing at the old path"; fi
if [ -e "$T3/docs/aiOS/templates/api-note.template.md" ]
  then bad "pristine file retired"; else ok "pristine file retired"; fi
check "manifest now at 1.1.0" \
  "$(python3 -c "import json;print(json.load(open('$T3/docs/aiOS/.chiron-install.json'))['chironVersion'])")" \
  "1.1.0"

# ── 5. conflict ───────────────────────────────────────────────
head1 "5. conflict — a locally edited managed file is sacred"
check "edited file byte-identical after apply" "$(shasum < "$T3/docs/aiOS/scripts/vault-lint.py")" "$mine"
grep -q "MY LOCAL EDIT" "$T3/docs/aiOS/scripts/vault-lint.py" && ok "local edit survived the upgrade" \
                                                              || bad "local edit survived the upgrade"
out=$(UP --target "$T3" --plan 2>&1); rc=$?
check "conflict keeps exit code non-zero" "$rc" "1"
grep -q "CONFLICT" <<<"$out" && ok "conflict still reported after apply" \
                             || bad "conflict still reported after apply"

# a file the user edited must survive its own retirement
printf '\n# mine too\n' >> "$T3/docs/aiOS/templates/day-note.runbook.md"
rm -f "$FAKE/aiOS/templates/day-note.runbook.md"
cat > "$FAKE/migrations.json" <<'JSON'
[{"version": "1.2.0", "retires": ["{vault}/aiOS/templates/day-note.runbook.md"],
  "note": "retire a file the user edited"}]
JSON
printf '# Changelog\n\n## [1.2.0] — selftest fixture\n' > "$FAKE/CHANGELOG.md"
python3 "$FAKE/tools/chiron-release.py" --set 1.2.0 >/dev/null
out=$(UP --target "$T3" --plan 2>&1)
check "modified retire → KEEP" "$(sect "$out" KEEP 'day-note.runbook.md')" "1"
UP --target "$T3" --apply >/dev/null 2>&1
[ -f "$T3/docs/aiOS/templates/day-note.runbook.md" ] && ok "edited file survived retirement" \
                                                      || bad "edited file survived retirement"

# ── 6. local renames ─────────────────────────────────────────
head1 "6. --map — a consumer's own name is followed, not overwritten"
T4=$(new_repo remap)
inst --target "$T4" --apply --project-name "Renamed" \
     --map skills/wiki-sync=.claude/skills/cca-wiki-sync >/dev/null
[ -f "$T4/.claude/skills/cca-wiki-sync/SKILL.md" ] && ok "skill installed under the local name" \
                                                    || bad "skill installed under the local name"
if [ -e "$T4/.claude/skills/wiki-sync" ]
  then bad "upstream name not also created"; else ok "upstream name not also created"; fi
out=$(inst --target "$T4" --plan 2>&1)
grep -q "Nothing to do" <<<"$out" && ok "rename followed without repeating --map" \
                                  || bad "rename followed without repeating --map"

printf '\n\033[1mResult:\033[0m %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
