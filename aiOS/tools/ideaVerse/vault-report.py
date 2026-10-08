#!/usr/bin/env python3
"""
vault-report — roll the aiOS analysis tools up into vault-report.md.

This is an **aggregator**. Every finding in sections 1-4 comes from vault-lint,
coverage-gap, contradiction-check or wiki-sync, imported and called directly. It
re-implements none of their checks: the division of labour between those four is
deliberate, and overlapping tools disagree (see efforts/works/vault_tooling.md).

The one thing it owns is section 5, the aiOS invariants — facts the maps and
schedules assert about themselves that nothing else verifies:

  * every skill under .claude/skills/ has a row in the skill-map
  * the map's Invoke column matches each skill's `disable-model-invocation`
  * absolute paths written into aiOS/ actually exist

Section 6 is left empty for the librarian agent to fill with judgment the
scripts can't supply. Every run rewrites the whole file.

Usage:
  python3 aiOS/tools/ideaVerse/vault-report.py            # write vault-report.md
  python3 aiOS/tools/ideaVerse/vault-report.py --stdout   # print instead of writing

Exit codes:
  0 — report written (always, regardless of what it found)
  1 — a tool failed to run
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_lib as V  # noqa: E402

SCRIPTS_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SCRIPTS_DIR.parent      # aiOS/tools — the tool groups live beneath it
REPORT = V.VAULT_DIR / "vault-report.md"
SKILLS_DIR = V.REPO_ROOT / ".claude" / "skills"
SKILL_MAP = V.AIOS_DIR / "maps" / "skill-map.md"
SCHEDULES_DIR = V.AIOS_DIR / "schedules"

# Absolute home-dir paths hardcoded into aiOS prose. Globs and placeholders are
# not paths — skip anything containing * or <.
ABS_PATH_RE = re.compile(r"/(?:Users|home)/[A-Za-z0-9._\-/]+")

# Markdown links written vault-root-relative, e.g. [skill-map](/aiOS/maps/skill-map.md).
# These resolve against VAULT_DIR, not the filesystem root — so a link into a
# sibling of the vault (`/.claude/...`) is silently dead, which is how two of them
# survived unnoticed in vault-map.md.
VAULT_LINK_RE = re.compile(r"\]\((/[A-Za-z0-9._\-/]+)\)")


def load_script(stem: str, required: bool = True):
    """Import a sibling script by filename (they use hyphens, so plain import won't do).

    Returns None for an absent optional script. Not every vault installs every tool —
    the code-aware ones only make sense where there is code to scan — and a missing
    optional tool must cost its section, not the whole report.
    """
    path = SCRIPTS_DIR / f"{stem}.py"
    if not path.is_file():
        # Tools are grouped by domain (ideaVerse/, wiki/), so a sibling group may own it.
        path = next(iter(sorted(TOOLS_DIR.glob(f"*/{stem}.py"))), path)
    if not path.is_file():
        if required:
            raise FileNotFoundError(path)
        return None
    spec = importlib.util.spec_from_file_location(stem.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Section 5: aiOS invariants (this script's own checks) ──────

def check_skill_map() -> list[str]:
    """The skill-map's own maintenance contract, which nothing else enforces."""
    if not SKILL_MAP.exists() or not SKILLS_DIR.is_dir():
        return []

    text = SKILL_MAP.read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines() if ln.lstrip().startswith("|")]
    issues: list[str] = []

    for skill_dir in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        name = skill_dir.name
        # A leading underscore marks a shared library imported by sibling skills, not an
        # invocable skill. It has no SKILL.md by design, so a skill-map row would
        # misrepresent it — and then trip the next check.
        if name.startswith("_"):
            continue
        manifest = skill_dir / "SKILL.md"
        pattern = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
        matches = [r for r in rows if pattern.search(r)]

        if not matches:
            issues.append(f"[MAP] skill '{name}' has no row in skill-map.md")
            continue
        if not manifest.exists():
            issues.append(f"[MAP] skill '{name}' has no SKILL.md")
            continue

        fm, _ = V.parse_frontmatter(manifest.read_text(encoding="utf-8"))
        user_only = str(fm.get("disable-model-invocation", "")).lower() == "true"
        marked = any("user only" in r.lower() for r in matches)
        if user_only and not marked:
            issues.append(
                f"[MAP] skill '{name}' sets disable-model-invocation but its row "
                f"does not say 'user only'"
            )
        elif marked and not user_only:
            issues.append(
                f"[MAP] skill '{name}' is marked 'user only' but does not set "
                f"disable-model-invocation"
            )
    return issues


def check_aios_paths() -> list[str]:
    """Paths written into aiOS prose that don't resolve — two flavours.

    Machine-absolute (`/Users/...`) is a dead repo root. Vault-root-relative
    (`](/aiOS/...)`) is a dead link: it resolves against VAULT_DIR, so a link
    aimed at a sibling of the vault never existed in the first place.
    """
    issues: list[str] = []
    for md in sorted(V.AIOS_DIR.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        # Repo-root relative: aiOS sits beside the vault, not inside it, so VAULT_DIR is
        # no longer an ancestor of these files.
        rel = md.relative_to(V.REPO_ROOT).as_posix()

        for raw in ABS_PATH_RE.findall(text):
            path = raw.rstrip(".,;:)`\"'")
            if "*" in path or "<" in path or Path(path).exists():
                continue
            issues.append(f"[PATH] {rel}: '{path}' does not exist")

        for link in VAULT_LINK_RE.findall(text):
            target = link.split("#", 1)[0]
            if "*" in target or "<" in target or not target.strip("/"):
                continue
            # Obsidian resolves a leading-slash link from the vault root, which here is
            # the repo root (.obsidian sits there) — and aiOS/ is a sibling of the notes
            # rather than inside them, so both roots are legitimate anchors.
            bare = target.lstrip("/")
            if (V.VAULT_DIR / bare).exists() or (V.REPO_ROOT / bare).exists():
                continue
            issues.append(f"[PATH] {rel}: link '{target}' resolves from neither the vault nor the repo root")
    return sorted(set(issues))


# ── Rendering ──────────────────────────────────────────────────

def bullets(items: list[str], empty: str) -> list[str]:
    return [f"- {i}" for i in items] if items else [f"_{empty}_"]


def render_lint(lint, notes) -> tuple[list[str], dict[str, int]]:
    issues = lint.run_checks(notes, with_wiki=False)
    buckets: dict[str, list[str]] = {}
    for i in issues:
        tag = i.split("]")[0].lstrip("[") if i.startswith("[") else "OTHER"
        buckets.setdefault(tag, []).append(i.split("] ", 1)[-1])

    counts = {k: len(v) for k, v in buckets.items()}
    lines = ["## 1. Structure — `vault-lint`", ""]
    lines.append("Tier 1: broken links, missing frontmatter and missing `sources:` are "
                 "mechanically fixable. Orphans and duplicates are **not** — naming is a judgment "
                 "call, and a rename can silently open a coverage gap.")
    lines.append("")
    for tag in ("FATAL", "BROKEN", "DUPE", "ORPHAN", "EMPTY", "INFO"):
        found = buckets.get(tag, [])
        if not found:
            continue
        lines.append(f"### {tag} ({len(found)})")
        lines += [f"- {f}" for f in found]
        lines.append("")
    if not issues:
        lines += ["_Vault structure is clean._", ""]
    return lines, counts


def render_wiki(sync) -> tuple[list[str], dict[str, int]]:
    current = sync.scan_sources()
    manifest = sync.load_manifest()
    cover = sync.load_catalog_coverage()

    cur, man = set(current), set(manifest)
    new = sorted(cur - man)
    deleted = sorted(man - cur)
    changed = sorted(k for k in (cur & man) if current[k]["sha256"] != manifest[k]["sha256"])
    uncovered = sorted(k for k in cur if not sync.notes_for(k, cover))

    counts = {"new": len(new), "changed": len(changed),
              "deleted": len(deleted), "uncovered": len(uncovered)}

    lines = ["## 2. Wiki sync — `wiki-sync`", ""]
    lines.append("Tier 1: compiling these is the sweep's own job. Reconcile per the "
                 f"`{V.CONFIG['wikiSkillName']}` skill, then re-snapshot — but **never** "
                 "`--update` while drift outside the reconciled set remains, or it is "
                 "silently baselined.")
    lines.append("")
    for title, items, show in (
        ("NEW — needs a wiki note", new, False),
        ("CHANGED — affected notes may be stale", changed, True),
        ("DELETED — wiki note orphaned", deleted, True),
        ("UNCOVERED — no wiki note cites this source", uncovered, False),
    ):
        if not items:
            continue
        lines.append(f"### {title} ({len(items)})")
        for k in items:
            affects = sync.notes_for(k, cover) if show else []
            suffix = f" — affects: {', '.join(affects)}" if affects else ""
            lines.append(f"- `{k}`{suffix}")
        lines.append("")
    if not any(counts.values()):
        lines += ["_Wiki is in sync._", ""]
    return lines, counts


def render_coverage(cov) -> tuple[list[str], int]:
    if cov is None:
        return ["## 3. Coverage — `coverage-gap`", "",
                "_`coverage-gap.py` is not installed in this vault — section skipped._", ""], 0
    gaps = cov.collect(want_code=True, want_calendar=True)
    lines = ["## 3. Coverage — `coverage-gap`", ""]
    lines.append("Tier 2 throughout: a gap is a note that does not exist, and the librarian "
                 "does not author notes. Reported for a human to write.")
    lines.append("")
    grouped: dict[str, list[dict]] = {}
    for g in gaps:
        grouped.setdefault(cov.GROUPS.get(g["type"], g["type"]), []).append(g)
    for group in sorted(grouped):
        lines.append(f"### {group} ({len(grouped[group])})")
        for g in grouped[group]:
            lines.append(f"- **{g['item']}** ({g['severity']}) — {g['detail']}")
        lines.append("")
    if not gaps:
        lines += ["_No coverage gaps._", ""]
    return lines, len(gaps)


def render_contradictions(con) -> tuple[list[str], int]:
    res = con.run(set(con.DETECTORS))
    lines = ["## 4. Contradictions — `contradiction-check`", ""]
    lines.append("Tier 2: resolving a contradiction means deciding which side is right. "
                 "The code is the final authority; fix in the owning note, then re-run "
                 "`open-items.py` so the ledger clears.")
    lines.append("")
    for key, (label, _) in con.DETECTORS.items():
        items = res["findings"].get(key) or []
        if not items:
            continue
        lines.append(f"### {label} ({len(items)})")
        for f in sorted(items, key=lambda x: con.SEV_ORDER.get(x["severity"], 9)):
            mark = "**critical**" if f["severity"] == "critical" else "warning"
            lines.append(f"- [{mark}] **{f['item']}** — {f['detail']}")
            for e in f["evidence"][:4]:
                lines.append(f"  - {e}")
        lines.append("")
    if not res["total"]:
        lines += ["_No contradictions found._", ""]
    return lines, res["total"]


SCHEDULE_CAPS = {"browser-control"}  # plus the open "mcp:<server>" family


def check_schedule_capabilities() -> list[str]:
    """Every schedule declares the harness capabilities it needs, and what happens without.

    A schedule is the only file in the vendor-neutral ring allowed to name a concrete
    harness. Undeclared, that dependency is invisible until a run under a harness that
    lacks it silently produces an empty section — which is how a stale Crashlytics table
    comes to read as a fresh one.

    The `## Without` match is anchored to a heading: a step that merely *mentions*
    `## Without browser-control` in backticks must not satisfy the check.
    """
    issues: list[str] = []
    for md in sorted(SCHEDULES_DIR.glob("*.md")):
        rel = md.relative_to(V.REPO_ROOT).as_posix()
        fm, body = V.parse_frontmatter(md.read_text(encoding="utf-8"))
        if "requires" not in fm:
            issues.append(f"[SCHED] {rel}: no `requires:` — declare `[]` if any harness can run it")
            continue
        for cap in fm["requires"]:
            if cap not in SCHEDULE_CAPS and not cap.startswith("mcp:"):
                issues.append(f"[SCHED] {rel}: unknown capability '{cap}'")
            elif not re.search(rf"^## Without {re.escape(cap)}\s*$", body, re.M):
                issues.append(f"[SCHED] {rel}: requires '{cap}' but has no `## Without {cap}` section")
    return issues


def render_invariants() -> tuple[list[str], int]:
    issues = check_skill_map() + check_aios_paths() + check_schedule_capabilities()
    lines = ["## 5. aiOS invariants", ""]
    lines.append("Contracts the maps and schedules assert about themselves. Tier 1 — the "
                 "librarian may write `aiOS/{maps,schedules,templates}/`. It may **not** write "
                 "`aiOS/tools/ideaVerse/` or `aiOS/runbooks/`; findings there are proposals only.")
    lines.append("")
    lines += bullets(issues, "All aiOS invariants hold.")
    lines.append("")
    return lines, len(issues)


def build() -> tuple[str, str]:
    lint = load_script("vault-lint")
    sync = load_script("wiki-sync")
    cov = load_script("coverage-gap", required=False)
    con = load_script("contradiction-check")

    notes = V.load_notes()
    today = datetime.date.today().isoformat()

    lint_lines, lint_counts = render_lint(lint, notes)
    wiki_lines, wiki_counts = render_wiki(sync)
    cov_lines, cov_total = render_coverage(cov)
    con_lines, con_total = render_contradictions(con)
    inv_lines, inv_total = render_invariants()

    drift = wiki_counts["new"] + wiki_counts["changed"] + wiki_counts["deleted"]
    headline = (
        f"_As of **{today}** — {len(notes)} notes · "
        f"{lint_counts.get('FATAL', 0)} fatal · "
        f"{lint_counts.get('BROKEN', 0)} broken · "
        f"{drift} wiki drift · {cov_total} coverage gaps · "
        f"{con_total} contradictions · {inv_total} invariant breaks_"
    )

    head = [
        "---",
        "generated: true",
        f"generated_on: {today}",
        "tags: [vault-report, librarian, generated]",
        "---",
        "",
        "> [!warning] Generated file — do not edit by hand.",
        "> Sections 1-5 are compiled by `aiOS/tools/ideaVerse/vault-report.py`, "
        "which aggregates",
        "> `vault-lint`, `coverage-gap`, `contradiction-check` and `wiki-sync`. Section 6 is",
        "> written by the librarian agent. Every run rewrites the whole file — fix findings in",
        "> their owning note, never here.",
        "",
        "# Vault report",
        "",
        headline,
        "",
    ]
    tail = [
        "## 6. Proposals — librarian judgment",
        "",
        "<!-- LIBRARIAN:PROPOSALS -->",
        "",
        "_No proposals written this run._",
        "",
    ]

    body = "\n".join(head + lint_lines + wiki_lines + cov_lines
                     + con_lines + inv_lines + tail)
    summary = (
        f"{len(notes)} notes · {lint_counts.get('BROKEN', 0)} broken · {drift} wiki drift · "
        f"{cov_total} coverage · {con_total} contradictions · {inv_total} invariants"
    )
    return body, summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Aggregate the aiOS tools into vault-report.md.")
    ap.add_argument("--stdout", action="store_true", help="Print the report instead of writing it.")
    args = ap.parse_args()

    try:
        body, summary = build()
    except Exception as exc:  # a tool failing must not leave a half-written report
        print(f"✗ vault-report failed: {exc}", file=sys.stderr)
        return 1

    if args.stdout:
        print(body)
    else:
        REPORT.write_text(body, encoding="utf-8")
        print(f"✓ {REPORT.relative_to(V.REPO_ROOT)} — {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
