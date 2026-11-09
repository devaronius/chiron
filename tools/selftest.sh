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

# The upgrade fixtures must sit ABOVE whatever this checkout ships, or "upgrade" is
# indistinguishable from "verify" and scenario 4 tests nothing. Derived, never hardcoded:
# chiron's own version keeps moving, and a fixture pinned to a number it has since reached
# fails as a passing test that stopped exercising its own path.
NEXT=$(python3 -c "import re,sys;a,b,_=(list(map(int,re.findall(r'\d+',sys.argv[1])))+[0,0,0])[:3];print(f'{a}.{b+1}.0')" "$(cat "$CHIRON/VERSION")")
NEXT2=$(python3 -c "import re,sys;a,b,_=(list(map(int,re.findall(r'\d+',sys.argv[1])))+[0,0,0])[:3];print(f'{a}.{b+2}.0')" "$(cat "$CHIRON/VERSION")")

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
[ -f "$T/aiOS/tools/vault/vault_lib.py" ]  && ok "tools installed at repo root" || bad "tools installed at repo root"
[ -f "$T/aiOS/.chiron-install.json" ]          && ok "manifest written"          || bad "manifest written"
[ -f "$T/docs/project-brief.md" ]              && ok "briefing seeded"           || bad "briefing seeded"
[ -f "$T/.claude/skills/vault-wiki-sync/SKILL.md" ] && ok "skills installed" || bad "skills installed"
[ -f "$T/.claude/agents/librarian.md" ]        && ok "agent adapter installed"   || bad "agent adapter installed"
[ -f "$T/.claude/hooks/open-items-lane.py" ]   && ok "session hook installed"    || bad "session hook installed"
[ -d "$T/docs/vault/efforts/works" ]       && ok "ACE skeleton scaffolded"   || bad "ACE skeleton scaffolded"
if [ -e "$T/docs/aiOS" ]
  then bad "aiOS is not installed inside the vault"
  else ok "aiOS is not installed inside the vault"; fi
if [ -e "$T/.claude/skills/bootstrap-vault" ]
  then bad "installer must not be copied into the target"
  else ok "installer not copied into target"; fi
if grep -q '{{' "$T/docs/project-brief.md"
  then bad "seed tokens substituted"
  else ok "seed tokens substituted"; fi
if grep -rq '{{PROJECT_NAME}}\|{{VAULT_PREFIX}}' "$T/aiOS/runbooks/" "$T/aiOS/tools/" "$T/aiOS/templates/" "$T/.claude/skills/" "$T/.claude/hooks/"
  then bad "managed payload carries no install tokens"
  else ok "managed payload carries no install tokens"; fi
if python3 -c "import json;json.load(open('$T/aiOS/aios.config.json'))" 2>/dev/null
  then ok "aios.config.json is valid JSON"; else bad "aios.config.json is valid JSON"; fi
( cd "$T" && python3 aiOS/tools/wiki/wiki-sync.py --update >/dev/null 2>&1 )
out=$( cd "$T" && python3 aiOS/tools/wiki/wiki-sync.py 2>&1 )
grep -q "Wiki is in sync" <<<"$out" && ok "wiki baseline in sync" || bad "wiki baseline in sync"
out=$( cd "$T" && python3 aiOS/tools/vault/vault-lint.py 2>&1 )
if grep -q "FATAL" <<<"$out"; then bad "fresh install lints without FATAL"
  else ok "fresh install lints without FATAL"; fi
if ( cd "$T" && python3 aiOS/tools/vault/vault-report.py >/dev/null 2>&1 )
  then ok "vault-report runs" ; else bad "vault-report runs"; fi
out=$( cd "$T" && python3 aiOS/tools/vault/coverage-gap.py 2>&1 )
if grep -q "Coverage Analysis" <<<"$out"
  then ok "coverage-gap runs with no code config"
  else bad "coverage-gap runs with no code config"; fi
out=$( cd "$T" && python3 aiOS/tools/vault/open-items.py --lane 2>&1 ); rc=$?
check "open-items --lane exits 0 on an empty vault" "$rc" "0"
out=$( cd "$T" && python3 .claude/hooks/open-items-lane.py 2>&1 ); rc=$?
check "session hook exits 0 with nothing ripe" "$rc" "0"
[ -f "$T/.claude/skills/pdf-builder/md2pdf.py" ] && ok "pdf-builder installed with its script" \
                                                 || bad "pdf-builder installed with its script"
for agent in librarian researcher inspector; do
  [ -f "$T/.claude/agents/$agent.md" ] && ok "$agent adapter installed" \
                                       || bad "$agent adapter installed"
  [ -f "$T/aiOS/runbooks/$agent.runbook.md" ] && ok "$agent runbook installed" \
                                              || bad "$agent runbook installed"
done
[ -f "$T/.claude/hooks/researcher-scope.py" ] && ok "researcher scope hook installed" \
                                              || bad "researcher scope hook installed"
[ -f "$T/.claude/hooks/inspector-scope.py" ]  && ok "inspector scope hook installed" \
                                              || bad "inspector scope hook installed"
[ -f "$T/aiOS/runbooks/inspector/severity-rules.toml" ] && ok "severity rules seeded" \
                                                        || bad "severity rules seeded"
# The payload ships its own suites so a consumer can verify their copy after an upgrade.
# Run them in the INSTALLED tree, not chiron's — that is the copy that has to work, and a
# suite that only passes upstream is the failure this assertion exists to catch.
out=$( cd "$T" && bash aiOS/tools/run-tests.sh 2>&1 )
grep -q "all 4 suites pass" <<<"$out" && ok "every shipped suite passes where installed" \
                                      || { bad "every shipped suite passes where installed"; printf '%s\n' "$out" | tail -12; }

# ── 2. idempotence ────────────────────────────────────────────
head1 "2. idempotence — apply twice writes nothing"
snap () { ( cd "$1" && find aiOS docs .claude -type f -exec shasum {} \; | sort | shasum ); }
before=$(snap "$T")
out=$(inst --target "$T" --apply 2>&1); rc=$?
check "second apply changes no file" "$(snap "$T")" "$before"
check "second apply exits 0"         "$rc" "0"
grep -q "Nothing to do" <<<"$out" && ok "second apply reports nothing to do" \
                                  || bad "second apply reports nothing to do"

# ── fake next-minor (add / change / rename / retire) ──────────
FAKE="$WORK/chiron-$NEXT"
mkdir -p "$FAKE"
( cd "$CHIRON" && tar cf - --exclude=./.git --exclude=./.git/* . ) | ( cd "$FAKE" && tar xf - )
printf '# added in %s\n' "$NEXT" > "$FAKE/aiOS/templates/new-thing.template.md"
printf '\n# changed in %s\n' "$NEXT" >> "$FAKE/aiOS/tools/vault/note-review.py"
mv "$FAKE/aiOS/templates/schedule.template.md" "$FAKE/aiOS/templates/routine.template.md"
rm -f "$FAKE/aiOS/templates/api-note.template.md"
cat > "$FAKE/migrations.json" <<JSON
[{"version": "$NEXT",
  "renames": [["aiOS/templates/schedule.template.md",
               "aiOS/templates/routine.template.md"]],
  "retires": ["aiOS/templates/api-note.template.md"],
  "note": "selftest fixture"}]
JSON
printf '# Changelog\n\n## [%s] — selftest fixture\n' "$NEXT" > "$FAKE/CHANGELOG.md"
python3 "$FAKE/tools/chiron-release.py" --set "$NEXT" >/dev/null || bad "fixture release failed"
UP () { python3 "$FAKE/tools/chiron-install.py" "$@"; }

# ── 3. adopt ──────────────────────────────────────────────────
head1 "3. adopt — vault with no manifest, classified by hash history"
T2=$(new_repo adopt)
inst --target "$T2" --apply --project-name "Legacy" >/dev/null
printf '\n# MY OWN TWEAK\n' >> "$T2/aiOS/tools/vault/research-capture.py"
printf '\nMy own paragraph.\n' >> "$T2/docs/project-brief.md"
mine_rc=$(shasum < "$T2/aiOS/tools/vault/research-capture.py")
rm -f "$T2/aiOS/.chiron-install.json"        # now indistinguishable from a pre-chiron vault

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
check "conflicted file untouched by apply" "$(shasum < "$T2/aiOS/tools/vault/research-capture.py")" "$mine_rc"
grep -q "My own paragraph" "$T2/docs/project-brief.md" && ok "seeded edit preserved" \
                                                       || bad "seeded edit preserved"
[ -f "$T2/aiOS/.chiron-install.json" ] && ok "adopt records a manifest" || bad "adopt records a manifest"

# ── 4. upgrade ────────────────────────────────────────────────
head1 "4. upgrade — migrations then three-way diff"
T3=$(new_repo upgrade)
inst --target "$T3" --apply --project-name "Up" >/dev/null
printf '\n# MY LOCAL EDIT\n' >> "$T3/aiOS/tools/vault/vault-lint.py"
mine=$(shasum < "$T3/aiOS/tools/vault/vault-lint.py")

out=$(UP --target "$T3" --plan 2>&1)
grep -q "mode: upgrade" <<<"$out" && ok "detected upgrade mode" || bad "detected upgrade mode"
check "new file → ADD"         "$(sect "$out" ADD      'new-thing.template.md')" "1"
check "changed file → UPDATE"  "$(sect "$out" UPDATE   'note-review.py')"        "1"
check "edited file → CONFLICT" "$(sect "$out" CONFLICT 'vault-lint.py')"         "1"
grep -q "$NEXT: 1 rename(s), 1 retire(s)" <<<"$out" && ok "migrations listed in plan" \
                                                   || bad "migrations listed in plan"

UP --target "$T3" --apply >/dev/null 2>&1
[ -f "$T3/aiOS/templates/new-thing.template.md" ] && ok "added file written" || bad "added file written"
grep -q "changed in $NEXT" "$T3/aiOS/tools/vault/note-review.py" \
  && ok "changed file updated" || bad "changed file updated"
[ -f "$T3/aiOS/templates/routine.template.md" ] && ok "rename landed at new path" \
                                                      || bad "rename landed at new path"
if [ -e "$T3/aiOS/templates/schedule.template.md" ]
  then bad "rename left nothing at the old path"; else ok "rename left nothing at the old path"; fi
if [ -e "$T3/aiOS/templates/api-note.template.md" ]
  then bad "pristine file retired"; else ok "pristine file retired"; fi
check "manifest now at $NEXT" \
  "$(python3 -c "import json;print(json.load(open('$T3/aiOS/.chiron-install.json'))['chironVersion'])")" \
  "$NEXT"

# ── 5. conflict ───────────────────────────────────────────────
head1 "5. conflict — a locally edited managed file is sacred"
check "edited file byte-identical after apply" "$(shasum < "$T3/aiOS/tools/vault/vault-lint.py")" "$mine"
grep -q "MY LOCAL EDIT" "$T3/aiOS/tools/vault/vault-lint.py" && ok "local edit survived the upgrade" \
                                                              || bad "local edit survived the upgrade"
out=$(UP --target "$T3" --plan 2>&1); rc=$?
check "conflict keeps exit code non-zero" "$rc" "1"
grep -q "CONFLICT" <<<"$out" && ok "conflict still reported after apply" \
                             || bad "conflict still reported after apply"

# a file the user edited must survive its own retirement
printf '\n# mine too\n' >> "$T3/aiOS/runbooks/day-note.runbook.md"
rm -f "$FAKE/aiOS/runbooks/day-note.runbook.md"
cat > "$FAKE/migrations.json" <<JSON
[{"version": "$NEXT2", "retires": ["aiOS/runbooks/day-note.runbook.md"],
  "note": "retire a file the user edited"}]
JSON
printf '# Changelog\n\n## [%s] — selftest fixture\n' "$NEXT2" > "$FAKE/CHANGELOG.md"
python3 "$FAKE/tools/chiron-release.py" --set "$NEXT2" >/dev/null
out=$(UP --target "$T3" --plan 2>&1)
check "modified retire → KEEP" "$(sect "$out" KEEP 'day-note.runbook.md')" "1"
UP --target "$T3" --apply >/dev/null 2>&1
[ -f "$T3/aiOS/runbooks/day-note.runbook.md" ] && ok "edited file survived retirement" \
                                                      || bad "edited file survived retirement"

# ── 6. local renames ─────────────────────────────────────────
head1 "6. --map — a consumer's own name is followed, not overwritten"
T4=$(new_repo remap)
inst --target "$T4" --apply --project-name "Renamed" \
     --map skills/knowledge/vault-wiki-sync=.claude/skills/cca-wiki-sync >/dev/null
[ -f "$T4/.claude/skills/cca-wiki-sync/SKILL.md" ] && ok "skill installed under the local name" \
                                                    || bad "skill installed under the local name"
if [ -e "$T4/.claude/skills/vault-wiki-sync" ]
  then bad "upstream name not also created"; else ok "upstream name not also created"; fi
out=$(inst --target "$T4" --plan 2>&1)
grep -q "Nothing to do" <<<"$out" && ok "rename followed without repeating --map" \
                                  || bad "rename followed without repeating --map"

# A conflicted renamed file must keep its mapping, or the next run adds a second copy
# under the upstream name beside the one the consumer renamed.
printf '\n<!-- local tweak -->\n' >> "$T4/.claude/skills/cca-wiki-sync/SKILL.md"
inst --target "$T4" --apply >/dev/null 2>&1
out=$(inst --target "$T4" --plan 2>&1)
check "conflicted rename → CONFLICT, not ADD" "$(sect "$out" CONFLICT 'cca-wiki-sync')" "1"
check "no duplicate under the upstream name"  "$(sect "$out" ADD '.claude/skills/vault-wiki-sync')" "0"
if [ -e "$T4/.claude/skills/vault-wiki-sync" ]
  then bad "upstream name still not created"; else ok "upstream name still not created"; fi

# ── 7. the 2.0.0 move ────────────────────────────────────────
head1 "7. 2.0.0 — a 1.x tree is moved, not re-added"
# A 1.x vault kept aiOS INSIDE the vault, scripts in scripts/, the runbook in agents/, and
# the skills unprefixed. Built by hand from today's payload: what is under test is the
# rename machinery, so the file contents are deliberately current — a file that moved and a
# file that was re-added look identical unless the old path is checked too.
T5=$(new_repo migrate)
mkdir -p "$T5/docs/aiOS/scripts" "$T5/docs/aiOS/agents" "$T5/docs/aiOS/maps" \
         "$T5/docs/aiOS/templates" "$T5/.claude/skills/wiki-sync" "$T5/docs/ideaVerse" \
         "$T5/docs/wiki"
cp "$CHIRON/aiOS/tools/vault/vault_lib.py"       "$T5/docs/aiOS/scripts/vault_lib.py"
cp "$CHIRON/aiOS/tools/vault/note-review.py"     "$T5/docs/aiOS/scripts/note-review.py"
cp "$CHIRON/aiOS/tools/wiki/wiki-sync.py"            "$T5/docs/aiOS/scripts/wiki-sync.py"
cp "$CHIRON/aiOS/runbooks/librarian.runbook.md"      "$T5/docs/aiOS/agents/librarian.md"
cp "$CHIRON/aiOS/runbooks/day-note.runbook.md"       "$T5/docs/aiOS/templates/day-note.runbook.md"
cp "$CHIRON/skills/knowledge/vault-wiki-sync/SKILL.md" "$T5/.claude/skills/wiki-sync/SKILL.md"
printf '\n# MY 1.x EDIT\n' >> "$T5/docs/aiOS/scripts/note-review.py"
mine_1x=$(shasum < "$T5/docs/aiOS/scripts/note-review.py")
cat > "$T5/docs/aiOS/.chiron-install.json" <<JSON
{"chironVersion": "1.1.1", "installedAt": "2026-09-16", "upgradedAt": "2026-09-16",
 "vaultRoot": "docs", "vaultAtRepoRoot": false,
 "tokens": {"PROJECT_NAME": "Legacy", "BRIEFING_NOTE": "project-brief"}, "files": {}}
JSON

out=$(inst --target "$T5" --plan 2>&1)
grep -q "mode: upgrade" <<<"$out" && ok "pre-2.0.0 manifest found under the vault" \
                                  || bad "pre-2.0.0 manifest found under the vault"
grep -q "2.0.0: 25 rename(s)" <<<"$out" && ok "the move is listed as migrations" \
                                        || bad "the move is listed as migrations"

inst --target "$T5" --apply >/dev/null 2>&1
[ -f "$T5/aiOS/tools/vault/vault_lib.py" ] && ok "script moved to the repo root" \
                                               || bad "script moved to the repo root"
[ -f "$T5/aiOS/tools/wiki/wiki-sync.py" ]      && ok "wiki-sync moved to its own group" \
                                               || bad "wiki-sync moved to its own group"
[ -f "$T5/aiOS/runbooks/librarian.runbook.md" ] && ok "agent runbook moved and renamed" \
                                                || bad "agent runbook moved and renamed"
[ -f "$T5/aiOS/runbooks/day-note.runbook.md" ] && ok "day-note runbook left templates/" \
                                               || bad "day-note runbook left templates/"
if [ -e "$T5/docs/aiOS/scripts" ] || [ -e "$T5/docs/aiOS/agents" ]
  then bad "nothing left behind at the 1.x paths"
  else ok "nothing left behind at the 1.x paths"; fi
[ -f "$T5/.claude/skills/vault-wiki-sync/SKILL.md" ] && ok "skill renamed, not re-added" \
                                                         || bad "skill renamed, not re-added"
if [ -e "$T5/.claude/skills/wiki-sync/SKILL.md" ]
  then bad "old skill name removed"; else ok "old skill name removed"; fi
[ -f "$T5/aiOS/.chiron-install.json" ] && ok "manifest now at the repo root" \
                                       || bad "manifest now at the repo root"
if [ -e "$T5/docs/aiOS/.chiron-install.json" ]
  then bad "legacy manifest deleted"; else ok "legacy manifest deleted"; fi
check "a file edited before the move survives it" \
  "$(shasum < "$T5/aiOS/tools/vault/note-review.py")" "$mine_1x"
out=$(inst --target "$T5" --plan 2>&1)
check "no re-add of a moved file"  "$(sect "$out" ADD 'scripts/')" "0"

# ── 8. the 3.0.0 move ───────────────────────────────────────
head1 "8. 3.0.0 — a 2.0.0 tree's directories move, own files and all"
# Built from today's install, then put back into the 2.0.0 shape by hand: what is under
# test is the move machinery, so contents stay current and the old paths are what differ.
T6=$(new_repo rename)
inst --target "$T6" --apply --project-name "Renamed" \
     --map skills/knowledge/vault-wiki-sync=.claude/skills/cca-wiki-sync >/dev/null
mv "$T6/docs/vault" "$T6/docs/ideaVerse"
mv "$T6/aiOS/tools/vault" "$T6/aiOS/tools/ideaVerse"
for d in "$T6"/.claude/skills/vault-*; do
  n=$(basename "$d"); [ "$n" = vault-health ] && old=ideaverse-vault-health || old=ideaverse-${n#vault-}
  mv "$d" "$T6/.claude/skills/$old"
done
printf -- '---\nup: []\n---\n\nMy own note.\n' > "$T6/docs/ideaVerse/atlas/concepts/mine.md"
printf 'print("mine")\n' > "$T6/aiOS/tools/ideaVerse/local/mine.py"
printf '\n# MY 2.0.0 EDIT\n' >> "$T6/aiOS/tools/ideaVerse/vault-lint.py"
mine_lint=$(shasum < "$T6/aiOS/tools/ideaVerse/vault-lint.py")
# A 2.0.0 adapter predates the non-negotiable markers; it is seeded, so the upgrade leaves
# it for the user to merge, and the shipped parity suite has to say so until they do.
cp "$T6/.claude/agents/inspector.md" "$WORK/inspector-adapter.md"
perl -pi -e 's/<!-- nn:[a-z0-9-]+ --> //g' "$T6/.claude/agents/inspector.md"
python3 - "$T6/aiOS/.chiron-install.json" <<'PY'
import json, sys
path = sys.argv[1]
m = json.load(open(path))
def old(k):
    for new, was in (("aiOS/tools/vault/", "aiOS/tools/ideaVerse/"),
                     (".claude/skills/vault-health/", ".claude/skills/ideaverse-vault-health/"),
                     (".claude/skills/vault-", ".claude/skills/ideaverse-"),
                     ("docs/vault/", "docs/ideaVerse/")):
        if k.startswith(new):
            return was + k[len(new):]
    return k
m["chironVersion"] = "2.0.0"
m["files"] = {old(k): v for k, v in m["files"].items()}
json.dump(m, open(path, "w"), indent=2)
PY

out=$(inst --target "$T6" --plan 2>&1)
grep -q "mode: upgrade" <<<"$out" && ok "2.0.0 manifest read as an upgrade" \
                                  || bad "2.0.0 manifest read as an upgrade"
grep -q "3.0.0: 9 directory move(s)" <<<"$out" && ok "the moves are listed as migrations" \
                                               || bad "the moves are listed as migrations"
check "notes folder → MOVE"            "$(sect "$out" MOVE 'docs/vault')"              "1"
check "edited tool → CONFLICT"         "$(sect "$out" CONFLICT 'aiOS/tools/vault/vault-lint.py')" "1"
check "no ADD under a moved directory" "$(sect "$out" ADD '/vault/')"                  "0"
check "mapped skill not re-added"      "$(sect "$out" ADD 'vault-wiki-sync')"          "0"

inst --target "$T6" --apply >/dev/null 2>&1
[ -f "$T6/docs/vault/atlas/concepts/mine.md" ] && ok "own note moved with its folder" \
                                              || bad "own note moved with its folder"
[ -f "$T6/aiOS/tools/vault/local/mine.py" ]    && ok "local/ script moved with it" \
                                              || bad "local/ script moved with it"
if [ -e "$T6/docs/ideaVerse" ] || [ -e "$T6/aiOS/tools/ideaVerse" ]
  then bad "nothing left at the old directories"; else ok "nothing left at the old directories"; fi
check "an edited tool survives the move byte for byte" \
  "$(shasum < "$T6/aiOS/tools/vault/vault-lint.py")" "$mine_lint"
[ -f "$T6/.claude/skills/vault-health/SKILL.md" ] && ok "ideaverse-vault-health → vault-health" \
                                                  || bad "ideaverse-vault-health → vault-health"
if ls -d "$T6"/.claude/skills/ideaverse-* >/dev/null 2>&1
  then bad "no ideaverse-* skill left"; else ok "no ideaverse-* skill left"; fi
[ -f "$T6/.claude/skills/cca-wiki-sync/SKILL.md" ] && ok "--map name kept across the move" \
                                                   || bad "--map name kept across the move"
if [ -e "$T6/.claude/skills/vault-wiki-sync" ]
  then bad "mapped skill not duplicated"; else ok "mapped skill not duplicated"; fi
out=$(inst --target "$T6" --plan 2>&1)
check "second plan moves nothing"   "$(sect "$out" MOVE '/')" "0"
check "second plan adds nothing"    "$(sect "$out" ADD '/')"  "0"
check "old adapter → REVIEW"        "$(sect "$out" REVIEW '.claude/agents/inspector.md')" "1"
out=$( cd "$T6" && bash aiOS/tools/run-tests.sh 2>&1 )
grep -q "test_every_runbook_rule_reaches_the_adapter" <<<"$out" \
  && ok "unmerged adapter fails the parity suite after upgrade" \
  || bad "unmerged adapter fails the parity suite after upgrade"
cp "$WORK/inspector-adapter.md" "$T6/.claude/agents/inspector.md"     # the merge
# Only the inspector suite: this tree renamed a skill with --map, and the vault suite's
# doc-path check then (correctly) finds the librarian adapter naming the upstream path.
out=$( cd "$T6" && python3 -m unittest discover -s aiOS/tools/inspector/tests 2>&1 ); rc=$?
check "the merged adapter passes the inspector suite" "$rc" "0"

# ── 9. a blocked move ────────────────────────────────────────
head1 "9. blocked — both folders hold notes, so neither is touched"
T7=$(new_repo blocked)
inst --target "$T7" --apply --project-name "Both" >/dev/null
python3 -c "import json,sys;p=sys.argv[1];m=json.load(open(p));m['chironVersion']='2.0.0';json.dump(m,open(p,'w'))" \
  "$T7/aiOS/.chiron-install.json"
mkdir -p "$T7/docs/ideaVerse/atlas"
printf 'old\n' > "$T7/docs/ideaVerse/atlas/old.md"
before=$( cd "$T7" && find docs -type f -exec shasum {} \; | sort | shasum )
out=$(inst --target "$T7" --plan 2>&1); rc=$?
check "both folders → BLOCKED"      "$(sect "$out" BLOCKED 'docs/vault')" "1"
check "a blocked move exits 1"      "$rc" "1"
inst --target "$T7" --apply >/dev/null 2>&1
out=$(inst --target "$T7" --apply 2>&1); rc=$?
check "a blocked apply exits 1"     "$rc" "1"
grep -q "nothing written" <<<"$out" && ok "a blocked apply says it wrote nothing" \
                                    || bad "a blocked apply says it wrote nothing"
check "apply leaves both folders as they were" \
  "$( cd "$T7" && find docs -type f -exec shasum {} \; | sort | shasum )" "$before"
check "a blocked apply does not stamp the new version" \
  "$(python3 -c "import json;print(json.load(open('$T7/aiOS/.chiron-install.json'))['chironVersion'])")" \
  "2.0.0"

# ── 10. someone else's vault/ ────────────────────────────────
head1 "10. an unrelated vault/ is not a chiron vault"
T8=$(new_repo hashicorp)
mkdir -p "$T8/vault" && printf 'storage "file" {}\n' > "$T8/vault/config.hcl"
out=$(inst --target "$T8" --plan 2>&1)
grep -q "mode: install" <<<"$out" && ok "read as a fresh install, not an adopt" \
                                  || bad "read as a fresh install, not an adopt"
inst --target "$T8" --apply --project-name "Infra" >/dev/null 2>&1
[ -d "$T8/docs/vault/atlas" ] && ok "notes land in docs/vault" || bad "notes land in docs/vault"
if [ -e "$T8/vault/atlas" ] || [ -e "$T8/vault/vault" ]
  then bad "nothing written into their vault/"; else ok "nothing written into their vault/"; fi
T9=$(new_repo explicit)
mkdir -p "$T9/vault/atlas" "$T9/vault/efforts"
inst --target "$T9" --apply --vault-root docs --project-name "Explicit" >/dev/null 2>&1
[ -f "$T9/docs/project-brief.md" ] && ok "--vault-root wins over detection" \
                                   || bad "--vault-root wins over detection"

# ── 11. optional modules ─────────────────────────────────────
head1 "11. --module archive — opt-in folders, kept on upgrade"
T10=$(new_repo modules)
inst --target "$T10" --apply --project-name "Plain" >/dev/null
[ -d "$T10/docs/vault/atlas/collections" ] && bad "no module folders without --module" || ok "no module folders without --module"
grep -q "module:archive" "$T10/aiOS/maps/vault-map.md" && bad "module section stripped from the map" || ok "module section stripped from the map"
inst --target "$T10" --apply --module archive >/dev/null
[ -d "$T10/docs/vault/atlas/people" ] && ok "module folders scaffolded on opt-in" || bad "module folders scaffolded on opt-in"
[ -f "$T10/aiOS/tools/vault/archive-lint.py" ] && ok "module tools installed" || bad "module tools installed"
[ -f "$T10/docs/vault/atlas/collections/collections.md" ] && ok "module hub seeded" || bad "module hub seeded"
check "module recorded in the manifest" \
  "$(python3 -c "import json;print(json.load(open('$T10/aiOS/.chiron-install.json'))['modules'])")" "['archive']"
grep -q "module:archive" "$T10/aiOS/maps/vault-map.md" && bad "no module markers left in a chosen module's map" || ok "no module markers left in a chosen module's map"
grep -q '"modules"' "$T10/aiOS/aios.config.json" && bad "config carries no modules key" || ok "config carries no modules key"
T11=$(new_repo modules-fresh)
inst --target "$T11" --apply --project-name "Archive" --module archive >/dev/null
grep -q "atlas/collections/" "$T11/aiOS/maps/vault-map.md" && ok "fresh install: map has the archive section" || bad "fresh install: map has the archive section"
( cd "$T11" && python3 -m unittest discover -s aiOS/tools/vault/tests -p 'test_archive*' >/dev/null 2>&1 ) && ok "module tests pass in the installed repo" || bad "module tests pass in the installed repo"
T12=$(new_repo modules-map)
inst --target "$T12" --apply --project-name "Mapped" --module archive --map aiOS/tools/vault=aiOS/tools/notes >/dev/null
[ -f "$T12/aiOS/tools/notes/archive-lint.py" ] && ok "--map moves module files too" || bad "--map moves module files too"
out=$(inst --target "$T10" --plan)
sect "$out" ADD "" | grep -q . && bad "a later run without --module keeps the module" || ok "a later run without --module keeps the module"
grep -q "archive-lint.py" <<<"$(sect "$out" RETIRE "")" && bad "module files are not retired" || ok "module files are not retired"
( cd "$T10" && python3 aiOS/tools/vault/archive-lint.py --quiet ) && ok "archive-lint runs clean on the seeds" || bad "archive-lint runs clean on the seeds"
inst --target "$T10" --plan --module nope >/dev/null 2>&1
check "an unknown module is refused" "$?" "2"

printf '\n\033[1mResult:\033[0m %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
