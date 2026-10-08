#!/usr/bin/env bash
# Every Python test suite the aiOS and its skills ship.
#
#   aiOS/tools/run-tests.sh              all suites
#   aiOS/tools/run-tests.sh -v           unittest's per-test output
#   aiOS/tools/run-tests.sh --coverage   line coverage over aiOS/tools and .claude
#
# No network, no fixtures outside a temp directory, nothing that needs a PAT: the tools
# under test are pure, and the ones that are not are stubbed by their own suites.
#
# It lives in `aiOS/tools/` rather than under `.claude/` because the aiOS is the
# vendor-neutral ring — a repo with no Claude Code in front of it still has to be able to
# verify its own tooling.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"      # repo root
mode="${1:-}"
failed=()
found=0

# Discovered, not listed. A hardcoded roster is how a suite goes unrun for a week: the
# tests exist, the runner does not know about them, and nothing says so. Both rings are
# searched — `aiOS/tools/**/tests` (the framework's own) and `.claude/**/tests` (the
# skills and hooks, which ship their tests beside them).
suites="$(find "$here/aiOS/tools" "$here/.claude" -type d -name tests 2>/dev/null | sort)"

run_suite () {                                   # $1 = suite dir, $2 = label
  if [ "$mode" = "-v" ]; then
    printf '%s\n' "--- $2"
    $PY -m unittest discover -s "$1" -v
  else
    local output status
    output="$($PY -m unittest discover -s "$1" 2>&1)"; status=$?
    printf '%-44s %s\n' "$2" "$(printf '%s' "$output" | grep -E '^(OK|FAILED|Ran)' | tr '\n' ' ')"
    [ $status -eq 0 ] || printf '%s\n' "$output"
    return $status
  fi
}

PY="python3"
if [ "$mode" = "--coverage" ]; then
  if python3 -c 'import coverage' 2>/dev/null; then
    PY="python3 -m coverage run --append --source=$here/aiOS/tools,$here/.claude"
    python3 -m coverage erase
  else
    # Saying so beats reporting "no coverage" as if it were 0%.
    echo "coverage.py is not installed — running the suites without it (pip install coverage)"
    mode=""
  fi
fi

for suite in $suites; do
  found=$((found + 1))
  run_suite "$suite" "${suite#"$here"/}"
  [ $? -eq 0 ] || failed+=("${suite#"$here"/}")
done

echo
# An unmatched glob would otherwise exit 0 having run nothing — a green result that
# tested nothing is worse than a red one.
if [ "$found" -eq 0 ]; then
  echo "No test suites found under aiOS/tools/**/tests or .claude/**/tests." >&2
  exit 1
fi

if [ "$mode" = "--coverage" ]; then
  echo
  python3 -m coverage report --skip-empty
fi

if [ ${#failed[@]} -eq 0 ]; then
  echo "all $found suites pass"
else
  printf 'FAILED: %s\n' "${failed[*]}"
  exit 1
fi
