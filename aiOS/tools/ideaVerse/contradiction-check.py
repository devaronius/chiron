#!/usr/bin/env python3
"""
contradiction-check — find places where the ideaVerse disagrees with itself or the code.

Four detectors, each aimed at drift this vault has actually suffered:

  1. STATUS   — the same [[open_item]] carrying different [status::] in different notes,
                or a checkbox disagreeing with its own [status::]. This is the drift that
                happened on 2026-07-28: the docking-status-UI item stayed `open` in the
                07-23 day note after the work shipped in a7318e203.
  2. DEADLINE — a note stating a date in prose that disagrees with the [due::] recorded
                for the same commitment. 2026-07-31 is restated as prose in 16 notes, so
                one drifting copy is the realistic failure.
  3. STALE    — frontmatter `updated:` at least STALE_DAYS behind the last commit that
                MODIFIED the file. Gated at 2 days because a 1-day gap is just commit lag.
                Modifications only, because this repo squash-merges: a7318e203 ADDED ~40
                notes at once, which would otherwise read as every note being days stale.
  4. CONTRACT — a field a note attributes to a swagger schema that the schema does not
                declare. Precedent: the 07-28 note records correcting exactly this for
                `dockCodes` and `externalOrderId`. HEURISTIC — the claim side is prose,
                so treat hits as "go look", not as proof.

Deliberately NOT detected: generic "do X vs don't do X" conflicting advice. A regex
cannot judge that, and the skill wrapping this script has an analytical phase that can.

Usage:
  python3 aiOS/tools/ideaVerse/contradiction-check.py
  python3 aiOS/tools/ideaVerse/contradiction-check.py --json
  python3 aiOS/tools/ideaVerse/contradiction-check.py --only status,deadline

Exit codes:
  0 — no contradictions
  1 — contradictions found (need human resolution)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_lib as V  # noqa: E402

STALE_DAYS = 2
ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
FIELD_TOKEN_RE = re.compile(r"^[a-z][A-Za-z0-9]*$")

# Notes that document the item schema itself rather than carrying real items.
SCHEMA_DOC_NOTES = {"open_item", "day-note.template", "daily-briefing.template"}
PLACEHOLDER_ITEM_RE = re.compile(r"^<.*>$|^\s*$")

# Backticked tokens that are language/framework vocabulary, never wire fields. The
# framework set covers what any JSON-over-HTTP project sees; add language-specific
# vocabulary via `codeVocabulary` in aios.config.json rather than editing this file.
NON_FIELD_TOKENS = {
    "json", "int", "string", "bool", "double", "float", "null", "true", "false",
    "get", "post", "put", "patch", "delete", "required", "nullable", "build",
} | {str(t) for t in V.CONFIG["codeVocabulary"]}

# A note may mention a field precisely to record that it does NOT exist — e.g. an API
# note documenting a field that an earlier revision claimed and the spec never had.
# Backticked tokens sitting near any of these are being disclaimed, not claimed.
NEGATION_MARKERS = (
    "no such field", "does not exist", "doesn't exist", "not exist", "never existed",
    "corrected", "absent from", "no longer", "removed", "retired", "does not appear",
    "not in the spec", "neither field exists", "an earlier revision",
)
NEGATION_WINDOW = 200

STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "on", "in", "with", "is", "are",
    "be", "by", "at", "from", "that", "this", "it", "as", "not", "no", "should", "must",
    "still", "now", "was", "were", "has", "have", "had", "into", "via", "per", "than",
}


# ── 1. Open-item status conflicts ──────────────────────────────

def find_status_conflicts(notes: list[dict]) -> list[dict]:
    items = [
        i for i in V.parse_open_items(notes)
        if i["basename"] not in SCHEMA_DOC_NOTES
        and not PLACEHOLDER_ITEM_RE.match(i["text"])
    ]
    by_key: dict[str, list[dict]] = defaultdict(list)
    for i in items:
        key = V.item_key(i["text"])
        if len(key.split()) >= 3:  # very short keys collide by accident
            by_key[key].append(i)

    out = []
    for key, group in sorted(by_key.items()):
        statuses = {i["status"] for i in group if i["status"]}
        if len(statuses) > 1:
            out.append({
                "kind": "status",
                "severity": "critical",
                "item": key,
                "detail": "same open-item carries conflicting status across notes",
                "evidence": [f"{i['note']}: [status:: {i['status']}]" for i in group],
            })
        for i in group:
            if i["checked"] and i["status"] in {"open", "blocked"}:
                out.append({
                    "kind": "status", "severity": "critical", "item": key,
                    "detail": f"checked box but [status:: {i['status']}]",
                    "evidence": [i["note"]],
                })
            elif not i["checked"] and i["status"] == "done":
                out.append({
                    "kind": "status", "severity": "warning", "item": key,
                    "detail": "unchecked box but [status:: done]",
                    "evidence": [i["note"]],
                })
    return out


# ── 2. Deadline / date conflicts ───────────────────────────────

def _keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z]{4,}", V.item_key(text))
    return {w for w in words if w not in STOPWORDS}


def find_deadline_conflicts(notes: list[dict]) -> list[dict]:
    """Prose ISO dates that disagree with the [due::] of the same commitment."""
    # A closed item has no live deadline — whatever date its prose sits near,
    # there is nothing to reconcile. Only open commitments can conflict.
    dated = [i for i in V.parse_open_items(notes)
             if i["due"] and i["status"].lower() != "done"]
    out = []
    seen: set[tuple] = set()

    for item in dated:
        kws = _keywords(item["text"])
        if len(kws) < 3:
            continue
        for n in notes:
            for line in n["body"].splitlines():
                low = line.lower()
                if sum(1 for k in kws if k in low) < 3:
                    continue
                if "raised::" in line or "created" in low:
                    continue
                # If the line states the correct date anywhere, any other date on it
                # belongs to something else (deadline summary lines name several).
                if item["due"] in line:
                    continue
                for found in ISO_DATE_RE.findall(line):
                    # The item itself naming the date means it is recorded as
                    # superseded ("delayed from X to Y"), not contradicted.
                    if found in item["text"]:
                        continue
                    key = (n["path"], item["due"], found)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({
                        "kind": "deadline", "severity": "critical",
                        "item": item["text"][:70],
                        "detail": f"[due:: {item['due']}] but this line says {found}",
                        "evidence": [f"{n['path']}: {line.strip()[:120]}"],
                    })

    # Same commitment, two different due:: values.
    by_key: dict[str, set[str]] = defaultdict(set)
    where: dict[str, list[str]] = defaultdict(list)
    for i in dated:
        k = V.item_key(i["text"])
        by_key[k].add(i["due"])
        where[k].append(f"{i['note']}: [due:: {i['due']}]")
    for k, dues in by_key.items():
        if len(dues) > 1:
            out.append({
                "kind": "deadline", "severity": "critical", "item": k,
                "detail": f"same commitment carries different due dates: {', '.join(sorted(dues))}",
                "evidence": where[k],
            })
    return out


# ── 3. Stale frontmatter ───────────────────────────────────────

def find_stale_updated(notes: list[dict]) -> list[dict]:
    out = []
    for n in notes:
        fm_updated = str(n["frontmatter"].get("updated", "")).strip()
        if not ISO_DATE_RE.fullmatch(fm_updated):
            continue
        git_date = V.git_last_modified(n["abspath"])
        if not git_date or not ISO_DATE_RE.fullmatch(git_date):
            continue
        try:
            gap = (date.fromisoformat(git_date) - date.fromisoformat(fm_updated)).days
        except ValueError:
            continue
        if gap >= STALE_DAYS:
            out.append({
                "kind": "stale", "severity": "warning", "item": n["path"],
                "detail": f"updated: {fm_updated} but last commit {git_date} ({gap}d behind)",
                "evidence": [n["path"]],
            })
    return out


# ── 4. API contract claims ─────────────────────────────────────

def find_contract_conflicts(notes: list[dict]) -> list[dict]:
    """Fields attributed to a swagger schema that the schema does not declare.

    HEURISTIC. Only inspects paragraphs opening with **SchemaName** where SchemaName is
    a real schema in a parseable clipping, and only flags lowerCamelCase backticked
    tokens absent from EVERY schema of that spec (so cross-references don't fire).
    """
    specs: dict[str, dict[str, set[str]]] = {}
    for n in notes:
        if n["path"].startswith("atlas/apis/"):
            s = V.swagger_schemas(n)
            if s:
                specs[n["basename"]] = s
    if not specs:
        return []

    claim_docs: list[tuple[str, str]] = [(n["path"], n["body"]) for n in notes]
    for p in V.WIKI_DIR.rglob("*.md"):
        try:
            claim_docs.append((p.relative_to(V.VAULT_DIR).as_posix(), p.read_text(encoding="utf-8")))
        except OSError:
            continue

    out = []
    for spec_name, schemas in specs.items():
        all_props: set[str] = set().union(*schemas.values()) if schemas else set()
        for path, text in claim_docs:
            for para in re.split(r"\n\s*\n", text):
                m = re.match(r"\s*\*\*`?([A-Za-z0-9]+)`?\*\*", para)
                if not m:
                    continue
                schema = m.group(1)
                if schema not in schemas:
                    continue
                for tm in BACKTICK_RE.finditer(para):
                    tok = tm.group(1).strip()
                    if not FIELD_TOKEN_RE.match(tok) or tok in NON_FIELD_TOKENS:
                        continue
                    if tok in all_props:
                        continue
                    window = para[
                        max(0, tm.start() - NEGATION_WINDOW): tm.end() + NEGATION_WINDOW
                    ].lower()
                    if any(marker in window for marker in NEGATION_MARKERS):
                        continue  # the note is disclaiming this field, not claiming it
                    out.append({
                        "kind": "contract", "severity": "warning",
                        "item": f"{schema}.{tok}",
                        "detail": (
                            f"`{tok}` attributed to {schema} but absent from every schema "
                            f"in {spec_name} (heuristic — verify against the clip)"
                        ),
                        "evidence": [path],
                    })
    return out


# ── Report ─────────────────────────────────────────────────────

DETECTORS = {
    "status": ("Open-item status conflicts", find_status_conflicts),
    "deadline": ("Deadline / date conflicts", find_deadline_conflicts),
    "stale": ("Stale frontmatter `updated:`", find_stale_updated),
    "contract": ("API contract claims (heuristic)", find_contract_conflicts),
}
SEV_ORDER = {"critical": 0, "warning": 1}


def run(only: set[str]) -> dict:
    notes = V.load_notes()
    results: dict[str, list[dict]] = {}
    for key, (_, fn) in DETECTORS.items():
        if key in only:
            results[key] = fn(notes)
    total = sum(len(v) for v in results.values())
    critical = sum(1 for v in results.values() for f in v if f["severity"] == "critical")
    return {
        "notes_scanned": len(notes),
        "detectors": sorted(results),
        "total": total,
        "severity": "CRITICAL" if critical else ("WARNING" if total else "CLEAN"),
        "findings": results,
    }


def format_report(res: dict) -> str:
    lines = [
        f"Contradiction Check — {res['notes_scanned']} notes scanned",
        f"Severity: {res['severity']}",
    ]
    if not res["total"]:
        lines.append(f"\n✓ No contradictions found (detectors run: {', '.join(res['detectors'])}).")
        return "\n".join(lines)
    lines.append(f"Total findings: {res['total']}\n")

    for key, (label, _) in DETECTORS.items():
        items = res["findings"].get(key)
        if not items:
            continue
        lines.append(f"── {label} ({len(items)}) ──")
        for f in sorted(items, key=lambda x: SEV_ORDER.get(x["severity"], 9)):
            mark = "!!" if f["severity"] == "critical" else " !"
            lines.append(f"  {mark} {f['item']}")
            lines.append(f"       {f['detail']}")
            for e in f["evidence"][:4]:
                lines.append(f"       - {e}")
        lines.append("")

    lines.append("Resolve in the OWNING note (flip [status::], correct the date), then re-run")
    lines.append("open-items.py so the ledger clears. Never hand-edit open-items.md.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Find self-contradictions in the ideaVerse.")
    ap.add_argument("--json", action="store_true", help="Machine-readable output.")
    ap.add_argument(
        "--only", default="",
        help=f"Comma-separated subset of detectors: {','.join(DETECTORS)}",
    )
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()} or set(DETECTORS)
    unknown = only - set(DETECTORS)
    if unknown:
        print(f"unknown detector(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 1

    res = run(only)
    print(json.dumps(res, indent=2) if args.json else format_report(res))
    return 1 if res["total"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
