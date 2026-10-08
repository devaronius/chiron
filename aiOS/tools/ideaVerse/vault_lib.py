#!/usr/bin/env python3
"""
vault_lib — shared loading/resolution helpers for the aiOS vault scripts.

Extracted because vault-lint, coverage-gap, contradiction-check, note-review and
research-capture each carried their own copy of the same frontmatter parser — and
three of those copies did not parse YAML lists, so `related:`/`tags:` arrived as
raw strings and every list-aware check silently saw nothing.

Key facts this module encodes about the vault:

  * A wikilink may resolve OUTSIDE ideaVerse/ — the briefing note sits at the vault
    root, compiled notes live in wiki/, and the maps live in aiOS/maps/. Resolving
    against ideaVerse alone reports ~69% false "broken link" positives, so resolution
    scans every markdown root in the vault.
  * Notes come in two frontmatter flavours: standard vault notes (up/related/created)
    and raw API clippings under atlas/apis/ (title/source/created, tagged `clippings`).
    A single REQUIRED_FIELDS set wrongly fails every clipping.

Project-specific values are never hardcoded here — they come from
`aiOS/aios.config.json`, so this file stays identical across every vault and can be
upgraded in place. An unconfigured vault runs on the defaults below.

Not a CLI — import it.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from pathlib import Path

# ── Layout ─────────────────────────────────────────────────────

# aiOS is project-owned and lives at the repo root, beside the vault rather than inside
# it. It is the one fixed point: this file is aiOS/tools/<group>/vault_lib.py, so the
# operating layer and the repo are both derived from __file__. The vault is derived from
# config below, because it cannot be known before the config is read.
AIOS_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = AIOS_DIR.parent
CONFIG_PATH = AIOS_DIR / "aios.config.json"

DEFAULT_CONFIG = {
    "briefingNote": "project-brief",
    "rootNotes": [],
    "wikiSkillName": "ideaverse-wiki-sync",
    "vaultAtRepoRoot": False,
    # Directory holding the notes when the vault is not the repo root itself. `docs/` by
    # convention; a repo that already means something else by that name says so here
    # rather than forking the scripts to find its own vault.
    "vaultDir": "docs",
    "codeVocabulary": [],
    "captureKeywords": {},
    "code": {},
    # Declared absences. Each entry is {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD",
    # "why": "..."} with both ends inclusive. The calendar-cadence checks skip these
    # days: a day with nobody working it is not a hole in the record. `why` is
    # required by convention, not by the parser — a future reader seeing weeks of
    # skipped days needs to know it was declared, not a checker quietly weakened.
    "calendar": {"absences": []},
    # A shipped effort note stays whole this many workdays (Mon–Fri) after its
    # `shipped:` date; after that vault-lint reports it as due to be distilled into
    # atlas and replaced by a stub (vault-map → "Retiring a shipped effort").
    "efforts": {"stubAfterWorkdays": 14},
    # Who an open item's [assignee::] routes to. `self` is the human this vault belongs
    # to; `agent` is a reserved literal, not configurable. Anything else is someone else
    # and is never surfaced unless asked for. Empty `self` means nothing routes to the
    # human lane, so an unconfigured vault shows every item as unrouted rather than
    # silently claiming them.
    "assignees": {"self": ""},
}


def _load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass
    return cfg


CONFIG = _load_config()

# Where the notes live. The mode is explicit config, not detection: `.git` is a file,
# not a directory, in worktrees and submodules, so sniffing for it misreports both.
VAULT_DIR = REPO_ROOT if CONFIG["vaultAtRepoRoot"] else REPO_ROOT / CONFIG["vaultDir"]
IDEAVERSE_DIR = VAULT_DIR / "ideaVerse"
WIKI_DIR = VAULT_DIR / "wiki"

# Markdown roots a wikilink may resolve into. Deliberately explicit rather than walking
# the whole vault: with the vault at the repo root a full walk pulls in every README,
# CHANGELOG and vendored dependency, so broken links silently "resolve" against
# unrelated files and duplicate-basename detection drowns in noise.
# Absolute, not vault-relative names: aiOS sits outside the vault at the repo root,
# so these cannot all be resolved against a single parent.
SCAN_ROOTS = (IDEAVERSE_DIR, WIKI_DIR, AIOS_DIR)

# Top-level notes that are vault content. In a `docs/`-style vault the whole directory is
# the vault, so every top-level note counts. At the repo root it does not: README,
# CONTRIBUTING and CHANGELOG sit there too, and letting them into the resolvable set means
# a broken `[[README]]` link quietly passes.
FRAMEWORK_TOP_LEVEL = {"open-items.md", "vault-report.md"}

# ── Vocabulary ─────────────────────────────────────────────────

# Matches [[target]] and [[target|alias]]. Inside a markdown table Obsidian requires the
# alias pipe to be escaped as `\|`, so a trailing backslash on the target is stripped —
# otherwise [[skill-map\|vault-health]] resolves against the literal target "skill-map\".
WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)\\?(?:\|[^\]]+)?\]\]")

# Entry-point notes that are legitimately unreferenced by any other note.
FRAMEWORK_ROOT_NOTES = {
    "vault-map",        # navigation map
    "skill-map",        # intent -> skill lookup
    "open_item",        # framework concept
    "index",            # wiki index
}
ROOT_NOTES = (
    FRAMEWORK_ROOT_NOTES
    | {CONFIG["briefingNote"]}      # the briefing — vault root, points inward
    | set(CONFIG["rootNotes"])
)

# Frontmatter contracts per note flavour.
REQUIRED_FIELDS_STANDARD = {"up", "related", "created"}
REQUIRED_FIELDS_CLIPPING = {"title", "source", "created"}

# Wikilink targets that are template placeholders, never real notes.
PLACEHOLDER_TARGETS = {"linkable", "project", "effort", "note", "wikilinks", "base"}

# Date-shaped placeholders: YYYY-Www, 2026-Www, YYYY-MM-DD, 2026-W31. Matched by shape
# so the set never needs a year added to it.
PLACEHOLDER_DATE_RE = re.compile(r"^(?:YYYY|\d{4})-(?:Www|MM-DD|W\d{2})$")

MIN_BODY_CHARS = 50


# ── Frontmatter ────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from body.

    Handles the three shapes this vault actually uses: inline lists
    (`related: ["[[a]]", "[[b]]"]`), block lists (`sources:` then `  - "..."`),
    and plain scalars. Returns ({fm}, body).
    """
    text = text.lstrip("\n")
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    yaml_block = text[3:end].strip("\n")
    body = text[end + 4:].lstrip("\n")

    fm: dict = {}
    pending_key: str | None = None
    for raw in yaml_block.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        # Continuation of a block list: "  - item"
        if raw.startswith((" ", "\t")) and raw.strip().startswith("- "):
            if pending_key:
                fm.setdefault(pending_key, []).append(_scalar(raw.strip()[2:]))
            continue
        if ":" not in raw:
            continue
        key, _, val = raw.partition(":")
        key, val = key.strip(), val.strip()
        if not val:
            # Block list header — collect the following "- " lines.
            fm[key] = []
            pending_key = key
            continue
        pending_key = None
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [_scalar(i) for i in _split_inline(inner)] if inner else []
        else:
            fm[key] = _scalar(val)
    return fm, body


def _scalar(v: str):
    v = v.strip()
    for q in ('"', "'"):
        if len(v) >= 2 and v.startswith(q) and v.endswith(q):
            return v[1:-1]
    return v


def _split_inline(inner: str) -> list[str]:
    """Split an inline YAML list on commas that are not inside quotes."""
    out, buf, quote = [], "", None
    for ch in inner:
        if quote:
            if ch == quote:
                quote = None
            buf += ch
        elif ch in "\"'":
            quote = ch
            buf += ch
        elif ch == ",":
            out.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf)
    return out


# Folders with a closed list of note kinds (vault-map → "Folder structure"). A required
# `kind:` makes the filer answer "which of these is it?" at filing time — without it
# atlas/documents/ became a dumping ground, and atlas/concepts/ was collecting dated
# upgrade checks and team processes alongside the domain vocabulary.
DOCUMENTS_DIR = "atlas/documents/"
DOCUMENT_KINDS = ("external", "process", "stakeholder-reference", "backend-request")
CONCEPTS_DIR = "atlas/concepts/"
CONCEPT_KINDS = ("domain", "behaviour")

# folder prefix → (lint tag, allowed kinds)
FOLDER_KINDS = {
    DOCUMENTS_DIR: ("DOC-KIND", DOCUMENT_KINDS),
    CONCEPTS_DIR: ("CONCEPT-KIND", CONCEPT_KINDS),
}

# Framework notes that live in a kinded folder but are not one of its kinds.
KIND_EXEMPT = {"open_item"}


def kind_issue(note: dict, rel_path: str) -> tuple[str, str] | None:
    """(lint tag, reason) when a note in a kinded folder has no allowed `kind:`."""
    if note.get("basename") in KIND_EXEMPT:
        return None
    for prefix, (tag, kinds) in FOLDER_KINDS.items():
        if not rel_path.startswith(prefix):
            continue
        kind = str(note["frontmatter"].get("kind", "")).strip()
        allowed = ", ".join(kinds)
        folder = prefix.rstrip("/")
        if not kind:
            return tag, f"missing `kind:` — {folder}/ notes must declare one of: {allowed}"
        if kind not in kinds:
            return tag, f"`kind: {kind}` is not allowed in {folder}/ — use one of: {allowed}"
        return None
    return None


def is_clipping(note: dict) -> bool:
    """Raw API/source clippings follow a different frontmatter contract."""
    tags = note["frontmatter"].get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    return "clippings" in [str(t).strip() for t in tags] or note["path"].startswith("atlas/apis/")


def required_fields_for(note: dict) -> set[str]:
    return REQUIRED_FIELDS_CLIPPING if is_clipping(note) else REQUIRED_FIELDS_STANDARD


# ── Loading ────────────────────────────────────────────────────

def load_notes(root: Path = IDEAVERSE_DIR) -> list[dict]:
    """Load every markdown note under `root` as {path, basename, frontmatter, body}."""
    notes = []
    if not root.is_dir():
        return notes
    for p in sorted(root.rglob("*.md")):
        text = p.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        notes.append({
            "path": p.relative_to(root).as_posix(),
            "abspath": p,
            "basename": p.stem,
            "frontmatter": fm,
            "body": body.strip(),
        })
    return notes


def markdown_files() -> list[Path]:
    """Every markdown file that counts as vault content.

    The SCAN_ROOTS plus top-level notes (the briefing and the generated ledgers) —
    see SCAN_ROOTS for why this is a fixed list rather than a walk.
    """
    out: list[Path] = []
    for d in SCAN_ROOTS:
        if d.is_dir():
            out += [p for p in sorted(d.rglob("*.md")) if "/.obsidian/" not in p.as_posix()]
    top = sorted(VAULT_DIR.glob("*.md"))
    if CONFIG["vaultAtRepoRoot"]:
        wanted = FRAMEWORK_TOP_LEVEL | {f"{CONFIG['briefingNote']}.md"}
        top = [p for p in top if p.name in wanted]
    out += top
    return out


def resolvable_basenames() -> set[str]:
    """Every basename a [[wikilink]] may legitimately point at.

    Spans the vault — ideaVerse notes, compiled wiki notes, aiOS maps/templates, and
    top-level notes like the briefing.
    """
    return {p.stem for p in markdown_files()}


def link_targets(note: dict) -> set[str]:
    """All wikilink targets in a note's frontmatter (up/related) and body."""
    targets: set[str] = set()
    for field in ("up", "related"):
        val = note["frontmatter"].get(field, [])
        if isinstance(val, str):
            val = [val]
        for item in val:
            m = WIKILINK_RE.search(str(item))
            if m:
                targets.add(m.group(1).strip())
    for m in WIKILINK_RE.finditer(note["body"]):
        targets.add(m.group(1).strip())
    return targets


def unresolved_targets(note: dict, known: set[str]) -> list[str]:
    """Targets in `note` that resolve to nothing. Applies all skip rules."""
    headings = re.findall(r"^#{1,6}\s+(.+)$", note["body"], re.MULTILINE)
    missing = []
    for t in sorted(link_targets(note)):
        if t.startswith("#") or t.startswith(f"{VAULT_DIR.name}/") or t.startswith("."):
            continue
        if t in PLACEHOLDER_TARGETS or PLACEHOLDER_DATE_RE.match(t):
            continue
        # Path-style link: [[briefings/2026-07-23]] -> resolve on last segment.
        tail = t.split("/")[-1]
        if t in known or tail in known:
            continue
        # Intra-file heading reference.
        if any(t == h or h.startswith(t + " ") or h.startswith(t + "-") for h in headings):
            continue
        missing.append(t)
    return missing


# ── Open items ─────────────────────────────────────────────────

OPEN_ITEM_RE = re.compile(
    r"^\s*-\s*\[(?P<box>[ xX])\]\s*(?P<glyph>[^\s\[]*)\s*(?P<text>.*?)"
    r"(?=\[status::|\[due::|\[raised::|$)",
    re.MULTILINE,
)
FIELD_RE = re.compile(r"\[(?P<key>status|due|raised)::\s*(?P<val>[^\]]*)\]")


def parse_open_items(notes: list[dict]) -> list[dict]:
    """Extract every [[open_item]] with its inline Dataview fields."""
    items = []
    for n in notes:
        for line in n["body"].splitlines():
            if "[status::" not in line:
                continue
            fields = {m.group("key"): m.group("val").strip() for m in FIELD_RE.finditer(line)}
            text = FIELD_RE.sub("", line).strip()
            text = re.sub(r"^\s*-\s*\[[ xX]\]\s*", "", text).strip()
            items.append({
                "note": n["path"],
                "basename": n["basename"],
                "text": text,
                "status": fields.get("status", ""),
                "due": fields.get("due", ""),
                "raised": fields.get("raised", ""),
                "checked": bool(re.match(r"^\s*-\s*\[[xX]\]", line)),
            })
    return items


def item_key(text: str) -> str:
    """Normalise an open-item's prose to a comparison key.

    Strips markdown emphasis, code ticks, wikilinks, glyphs, resolution suffixes
    and punctuation so the same item written in two notes collapses to one key.
    """
    t = text.split("→")[0]                       # drop "→ resolved ..." suffixes
    t = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", t)
    t = re.sub(r"[*`_]", "", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return " ".join(t.split()[:10])              # first 10 words identify the item


# ── Git ────────────────────────────────────────────────────────

def git_last_modified(path: Path, modifications_only: bool = True) -> str | None:
    """Last commit date (YYYY-MM-DD) touching `path`, or None.

    `modifications_only` restricts to commits that MODIFIED the file (--diff-filter=M).
    This matters in any squash-merging repo: a single squashed PR can ADD dozens of
    vault notes in one commit, and counting that as "last touched" makes every note look
    days stale when nothing was edited at all. Most notes never get a modify-commit, so
    without this filter the freshness signal is a pure squash artifact.
    """
    cmd = ["git", "log", "-1", "--format=%ad", "--date=short"]
    if modifications_only:
        cmd.append("--diff-filter=M")
    cmd += ["--", str(path)]
    try:
        r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=15)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def today() -> date:
    return date.today()


def vault_rel(*parts: str) -> str:
    """A vault path written as a reader of a generated file needs it: relative to the
    repo root, so it can be pasted straight into a shell. Docstrings may say `<vault>`;
    generated output must not.
    """
    prefix = "" if CONFIG["vaultAtRepoRoot"] else f"{VAULT_DIR.name}/"
    return prefix + "/".join(parts)


# ── Swagger clippings ──────────────────────────────────────────

JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.S)


def swagger_schemas(note: dict) -> dict[str, set[str]]:
    """Parse an atlas/apis clipping's embedded swagger into {SchemaName: {property, ...}}.

    Returns {} when the note carries no parseable JSON fence — a prose clipping rather
    than a raw dump.
    """
    m = JSON_FENCE_RE.search(note["body"])
    if not m:
        return {}
    try:
        spec = json.loads(m.group(1))
    except (json.JSONDecodeError, TypeError):
        return {}
    schemas = spec.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict):
        return {}
    return {
        name: set((body or {}).get("properties", {}).keys())
        for name, body in schemas.items()
        if isinstance(body, dict)
    }
