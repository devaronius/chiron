#!/usr/bin/env python3
"""
chiron-install — install, adopt, upgrade or verify a chiron ideaVerse in a target repo.

This is chiron's own machinery, not payload: it lives in `tools/` and is never copied into
a consumer vault. The `bootstrap-ideaverse` skill runs it from a chiron checkout.

Four modes, detected from the target rather than passed in:

  install   no vault           → write everything, record a manifest
  adopt     vault, no manifest → classify each file against the shipped-hash history,
                                 add what's missing, upgrade what is provably pristine,
                                 report what the user changed, then record a manifest
  upgrade   manifest older     → apply migrations, then the same three-way diff
  verify    manifest current   → report drift only; never write

The three-way decision is the whole point. For each file we know: what is on disk, what
chiron ships now, and what chiron shipped when this vault was installed. Without that
third fact, "the user customised it" and "upstream moved on" look identical, and an
upgrade either destroys local work or can never update anything. `.chiron-hashes.json`
supplies the third fact even with no manifest, by recording every hash chiron has ever
shipped for a path.

Two file classes, distinguished structurally by which payload directory they come from:

  managed   aiOS/** and skills/**  — no install tokens, hashes compare directly upstream
                                     to disk, upgraded automatically while untouched
  seeded    seeds/**               — rendered once from project facts, then yours; never
                                     overwritten again, only reported when upstream moves

Usage:
  chiron-install.py --target DIR --plan
  chiron-install.py --target DIR --apply
  chiron-install.py --target DIR --plan --json
  chiron-install.py --target DIR --apply --vault-root docs \
      --project-name "Acme Checkout" --project-domain "..." --roles "Dev,QA"
  chiron-install.py --target DIR --apply --at-repo-root
  chiron-install.py --target DIR --plan --map skills/wiki-sync=.claude/skills/cca-wiki-sync

Exit codes:
  0 — plan/apply completed with nothing needing a human
  1 — completed, but conflicts or reviews need attention
  2 — refused (bad arguments, or a target that cannot be resolved)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

CHIRON_ROOT = Path(__file__).resolve().parents[1]
HASHES_PATH = CHIRON_ROOT / ".chiron-hashes.json"
MIGRATIONS_PATH = CHIRON_ROOT / "migrations.json"
VERSION_PATH = CHIRON_ROOT / "VERSION"

MANIFEST_REL = "aiOS/.chiron-install.json"      # relative to the vault
SKILLS_DEST = ".claude/skills"
AGENTS_DEST = ".claude/agents"

# The installer itself is user-level (`~/.claude/skills/`), one copy for every repo — a
# per-repo copy is what let the old skill drift from its own payload.
SKILLS_NOT_INSTALLED = {"bootstrap-ideaverse"}

# Never treated as payload, even though they sit in aiOS/.
PAYLOAD_EXCLUDE = {".chiron-install.json", ".DS_Store"}
PAYLOAD_EXCLUDE_DIRS = {"__pycache__", "local"}

# The ACE skeleton. Created empty so a new note has an obvious home rather than requiring
# the author to guess and invent a folder. Git will not track an empty directory, which is
# fine — the first note in one recreates it.
SCAFFOLD_DIRS = [
    "aiOS/schedules", "aiOS/scripts/local",
    "ideaVerse/atlas/apis", "ideaVerse/atlas/concepts", "ideaVerse/atlas/documents",
    "ideaVerse/atlas/personas",
    "ideaVerse/calendar/days", "ideaVerse/calendar/briefings", "ideaVerse/calendar/meetings",
    "ideaVerse/calendar/research", "ideaVerse/calendar/releases", "ideaVerse/calendar/sprints",
    "ideaVerse/efforts/projects", "ideaVerse/efforts/works",
    "ideaVerse/+",
    "wiki/topics", "wiki/concepts", "wiki/entities", "wiki/projects",
]


# ── helpers ────────────────────────────────────────────────────

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def version() -> str:
    try:
        return VERSION_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


def semver(v: str) -> tuple:
    parts = re.findall(r"\d+", v or "0")
    return tuple(int(x) for x in (parts + ["0", "0", "0"])[:3])


def render(text: str, tokens: dict) -> str:
    for k, v in tokens.items():
        text = text.replace("{{%s}}" % k, str(v))
    return text


def walk(root: Path) -> list[Path]:
    """Every file under root, skipping caches and the unmanaged escape hatch."""
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        parts = set(p.relative_to(root).parts)
        if parts & PAYLOAD_EXCLUDE_DIRS or p.name in PAYLOAD_EXCLUDE:
            continue
        out.append(p)
    return out


# ── payload mapping ────────────────────────────────────────────

class Item:
    """One payload file and where it lands in the target."""

    def __init__(self, src: str, dest: str, cls: str):
        self.src = src        # path relative to the chiron root
        self.dest = dest      # path relative to the target repo root
        self.cls = cls        # "managed" | "seeded"

    @property
    def abs_src(self) -> Path:
        return CHIRON_ROOT / self.src


def payload(vault_prefix: str, seed_dests: dict) -> list[Item]:
    items: list[Item] = []

    for p in walk(CHIRON_ROOT / "aiOS"):
        rel = p.relative_to(CHIRON_ROOT).as_posix()
        items.append(Item(rel, f"{vault_prefix}{rel}", "managed"))

    skills_root = CHIRON_ROOT / "skills"
    if skills_root.is_dir():
        for d in sorted(x for x in skills_root.iterdir() if x.is_dir()):
            if d.name in SKILLS_NOT_INSTALLED:
                continue
            for p in walk(d):
                rel = p.relative_to(CHIRON_ROOT).as_posix()
                inner = p.relative_to(d).as_posix()
                items.append(Item(rel, f"{SKILLS_DEST}/{d.name}/{inner}", "managed"))

    for p in walk(CHIRON_ROOT / "seeds"):
        rel = p.relative_to(CHIRON_ROOT).as_posix()
        inner = p.relative_to(CHIRON_ROOT / "seeds").as_posix()
        dest = seed_dests.get(inner)
        if dest is None:                                    # seeds/ideaVerse/**, seeds/wiki/**
            dest = f"{vault_prefix}{inner}"
        items.append(Item(rel, dest, "seeded"))

    return items


def seed_destinations(vault_prefix: str, briefing: str) -> dict:
    """Seeds whose destination is not a straight mirror of their payload path."""
    return {
        "project-brief.md": f"{vault_prefix}{briefing}.md",
        "vault-root.CLAUDE.md": f"{vault_prefix}CLAUDE.md",
        "aios.config.json": f"{vault_prefix}aiOS/aios.config.json",
        "claude-agent-librarian.md": f"{AGENTS_DEST}/librarian.md",
        # The maps land in aiOS/ but are seeded, not managed: they carry the project's name
        # and, once installed, the consumer's own routing rules and precedence notes. An
        # upgrade reports that upstream moved and leaves the merge to a human or an agent.
        "maps/vault-map.md": f"{vault_prefix}aiOS/maps/vault-map.md",
        "maps/skill-map.md": f"{vault_prefix}aiOS/maps/skill-map.md",
    }


# ── planning ───────────────────────────────────────────────────

def remap(item: Item, mapping: dict) -> str:
    """Apply a --map override to one payload file.

    Matches a whole directory as well as a single file, because the renames that actually
    happen are directory-level: a consumer renames the skill `wiki-sync` to
    `cca-wiki-sync`, not each file inside it.
    """
    if item.src in mapping:
        return mapping[item.src]
    for k, v in mapping.items():
        prefix = k.rstrip("/")
        if item.src.startswith(prefix + "/"):
            return v.rstrip("/") + item.src[len(prefix):]
    return item.dest


def content_for(item: Item, tokens: dict) -> bytes:
    raw = item.abs_src.read_bytes()
    if item.cls == "seeded":
        return render(raw.decode("utf-8"), tokens).encode("utf-8")
    return raw


def build_plan(target: Path, vault_prefix: str, tokens: dict, briefing: str,
               manifest: dict, hashes: dict, mapping: dict) -> tuple[list[dict], list[dict]]:
    """Returns (actions, migrations_to_apply)."""
    installed_version = manifest.get("chironVersion")
    files = manifest.get("files", {})

    migrations = []
    if installed_version:
        for m in read_json(MIGRATIONS_PATH, []):
            if semver(m.get("version", "0")) > semver(installed_version):
                migrations.append(m)
        migrations.sort(key=lambda m: semver(m["version"]))

    actions: list[dict] = []
    seed_dests = seed_destinations(vault_prefix, briefing)
    for item in payload(vault_prefix, seed_dests):
        dest_rel = remap(item, mapping)
        # A consumer rename recorded at install time follows the file forever.
        recorded = files.get(dest_rel) or files.get(item.dest) or {}
        if recorded.get("installedAs"):
            dest_rel = recorded["installedAs"]

        dest = target / dest_rel
        want = content_for(item, tokens)
        want_sha = sha(want)
        upstream_sha = sha(item.abs_src.read_bytes())

        if not dest.exists():
            actions.append(dict(action="add", dest=dest_rel, src=item.src, cls=item.cls,
                                sha=want_sha, note=""))
            continue

        have_sha = sha(dest.read_bytes())
        if have_sha == want_sha:
            continue                                        # already exactly what we ship

        if item.cls == "seeded":
            actions.append(dict(action="review", dest=dest_rel, src=item.src, cls=item.cls,
                                sha=have_sha,
                                note="seeded file — yours to own; upstream version differs"))
            continue

        if recorded.get("sha256"):
            pristine = have_sha == recorded["sha256"]
            why = "unchanged since install" if pristine else "edited since install"
        else:
            shipped = set(hashes.get(item.src, {}).values())
            pristine = have_sha in shipped
            why = ("matches a previously shipped version"
                   if pristine else "matches no version chiron ever shipped")

        actions.append(dict(
            action="update" if pristine else "conflict",
            dest=dest_rel, src=item.src, cls=item.cls,
            sha=upstream_sha if pristine else have_sha, note=why))

    actions += plan_retires(target, vault_prefix, migrations, files, hashes)
    return actions, migrations


def plan_retires(target: Path, vault_prefix: str, migrations: list[dict],
                 files: dict, hashes: dict) -> list[dict]:
    """Retirement deletes only a file chiron itself shipped and the user never touched.

    Deleting someone's work because upstream lost interest in a path is not acceptable, so
    a modified file survives its own retirement and says why.
    """
    out = []
    for m in migrations:
        for rel in m.get("retires", []):
            dest_rel = rel.replace("{vault}/", vault_prefix)
            dest = target / dest_rel
            if not dest.exists():
                continue
            have = sha(dest.read_bytes())
            recorded = files.get(dest_rel, {})
            # History is keyed by payload path, so strip the destination's vault prefix.
            shipped = set(hashes.get(rel.replace("{vault}/", ""), {}).values())
            pristine = have == recorded.get("sha256") or have in shipped
            out.append(dict(
                action="retire" if pristine else "keep",
                dest=dest_rel, src="", cls="managed", sha=have,
                note=(f"retired in {m['version']}" if pristine else
                      f"retired in {m['version']} upstream, but you modified it — kept")))
    return out


def plan_renames(vault_prefix: str, migrations: list[dict]) -> list[tuple[str, str]]:
    out = []
    for m in migrations:
        for old, new in m.get("renames", []):
            out.append((old.replace("{vault}/", vault_prefix),
                        new.replace("{vault}/", vault_prefix)))
    return out


# ── applying ───────────────────────────────────────────────────

def apply_plan(target: Path, vault_prefix: str, tokens: dict, briefing: str,
               actions: list[dict], migrations: list[dict], manifest: dict) -> dict:
    # Renames first: without them a moved file looks like "missing at the old path, new at
    # the new one" and the diff would helpfully restore the file you just renamed.
    for old, new in plan_renames(vault_prefix, migrations):
        src, dst = target / old, target / new
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

    for d in SCAFFOLD_DIRS:
        (target / vault_prefix / d).mkdir(parents=True, exist_ok=True)

    seed_dests = seed_destinations(vault_prefix, briefing)
    by_src = {i.src: i for i in payload(vault_prefix, seed_dests)}

    files = dict(manifest.get("files", {}))
    for a in actions:
        dest = target / a["dest"]
        if a["action"] in ("add", "update"):
            item = by_src[a["src"]]
            data = content_for(item, tokens)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            entry = dict(sha256=sha(data), shipped=version(), cls=item.cls, src=item.src)
            if a["dest"] != item.dest:
                # Record the local name so every later upgrade follows it rather than
                # re-adding the file under the name chiron ships.
                entry["installedAs"] = a["dest"]
            files[item.dest] = entry
        elif a["action"] == "retire":
            dest.unlink(missing_ok=True)
            files.pop(a["dest"], None)
        elif a["action"] in ("conflict", "review") and a["src"] in by_src:
            # We are not writing this file, but the local NAME still has to be remembered:
            # without it the next run looks for the upstream name, finds nothing, and adds a
            # second copy alongside the one the consumer renamed.
            #
            # Deliberately no sha256. Recording the current (edited) hash would make the
            # file read as "unchanged since install" next time, and the upgrade after that
            # would overwrite the very edit this action exists to protect.
            item = by_src[a["src"]]
            if a["dest"] != item.dest:
                entry = files.setdefault(item.dest, {})
                entry.update(cls=item.cls, src=item.src, installedAs=a["dest"])

    # Record every in-sync file too, so the next run has the third fact for all of them.
    for item in payload(vault_prefix, seed_dests):
        rec = files.get(item.dest)
        d = target / (rec.get("installedAs") if rec and rec.get("installedAs") else item.dest)
        if d.exists() and item.dest not in files:
            files[item.dest] = dict(sha256=sha(d.read_bytes()), shipped=version(),
                                    cls=item.cls, src=item.src)

    return {
        "chironVersion": version(),
        "installedAt": manifest.get("installedAt") or str(date.today()),
        "upgradedAt": str(date.today()),
        "vaultRoot": vault_prefix.rstrip("/") or ".",
        "vaultAtRepoRoot": vault_prefix == "",
        "tokens": tokens,
        "files": files,
    }


# ── modes & reporting ──────────────────────────────────────────

def detect_mode(target: Path, vault_prefix: str, manifest: dict) -> str:
    vault = target / vault_prefix if vault_prefix else target
    if not manifest:
        has_vault = (vault / "aiOS").is_dir() or (vault / "ideaVerse").is_dir()
        return "adopt" if has_vault else "install"
    if semver(manifest.get("chironVersion", "0")) < semver(version()):
        return "upgrade"
    return "verify"


def report(mode: str, actions: list[dict], migrations: list[dict], applied: bool) -> int:
    order = ["add", "update", "conflict", "review", "retire", "keep"]
    groups = {k: [a for a in actions if a["action"] == k] for k in order}

    verb = "Applied" if applied else "Plan"
    print(f"chiron {version()} — mode: {mode} — {verb.lower()}\n")

    if migrations:
        print("Migrations to apply:")
        for m in migrations:
            bits = []
            if m.get("renames"):
                bits.append(f"{len(m['renames'])} rename(s)")
            if m.get("retires"):
                bits.append(f"{len(m['retires'])} retire(s)")
            print(f"  {m['version']}: {', '.join(bits) or 'notes only'}")
            if m.get("note"):
                print(f"      note: {m['note']}")
        print()

    labels = {
        "add": "ADD       (missing here)",
        "update": "UPDATE    (pristine — safe to overwrite)",
        "conflict": "CONFLICT  (you edited it — left alone)",
        "review": "REVIEW    (seeded — yours; upstream differs)",
        "retire": "RETIRE    (deleted upstream, pristine here)",
        "keep": "KEEP      (retired upstream, modified here)",
    }
    for k in order:
        if not groups[k]:
            continue
        print(f"{labels[k]} — {len(groups[k])}")
        for a in groups[k]:
            note = f"  — {a['note']}" if a["note"] else ""
            print(f"  {a['dest']}{note}")
        print()

    if not actions and not migrations:
        print("Nothing to do — this vault matches chiron " + version() + ".")

    needs_human = groups["conflict"] or groups["review"] or groups["keep"]
    if needs_human and not applied:
        print("Conflicts and reviews are NOT written by --apply. Merge them yourself, or")
        print("let the agent merge the seeded ones semantically.")
    return 1 if needs_human else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Install, adopt, upgrade or verify a chiron ideaVerse.")
    ap.add_argument("--target", required=True, help="repo to install into")
    ap.add_argument("--vault-root", default=None, help="vault directory name (default: docs)")
    ap.add_argument("--at-repo-root", action="store_true", help="vault IS the repo root")
    ap.add_argument("--project-name", default=None)
    ap.add_argument("--project-domain", default="")
    ap.add_argument("--roles", default="", help="comma-separated; empty means solo")
    ap.add_argument("--briefing-note", default=None, help="basename of the briefing note")
    ap.add_argument("--wiki-skill", default="wiki-sync")
    ap.add_argument("--map", action="append", default=[], metavar="SRC=DEST",
                    help="install a payload path to a non-default destination")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true", help="machine-readable plan")
    args = ap.parse_args()

    target = Path(args.target).expanduser().resolve()
    if not target.is_dir():
        print(f"✗ target is not a directory: {target}", file=sys.stderr)
        return 2
    if args.at_repo_root and args.vault_root:
        print("✗ --at-repo-root and --vault-root are mutually exclusive", file=sys.stderr)
        return 2

    # An existing install decides its own layout; only a fresh one takes it from flags.
    vault_prefix = None
    for cand in ("", "docs/"):
        m = read_json(target / cand / MANIFEST_REL, None)
        if m:
            vault_prefix, manifest = cand, m
            break
    else:
        manifest = {}
        for cand in ("docs/", ""):
            probe = target / cand
            if (probe / "aiOS").is_dir() or (probe / "ideaVerse").is_dir():
                vault_prefix = cand
                break
    if vault_prefix is None:
        vault_prefix = "" if args.at_repo_root else f"{args.vault_root or 'docs'}/"
    if manifest:
        vault_prefix = "" if manifest.get("vaultAtRepoRoot") else f"{manifest['vaultRoot']}/"

    stored = manifest.get("tokens", {})
    project = args.project_name or stored.get("PROJECT_NAME") or target.name
    briefing = (args.briefing_note or stored.get("BRIEFING_NOTE") or "project-brief")
    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    roles_section = ""
    if roles:
        roles_section = "## Roles — who you work with\n\n" + "\n".join(f"- **{r}**" for r in roles) + "\n"

    tokens = {
        "PROJECT_NAME": project,
        "PROJECT_DOMAIN": args.project_domain or stored.get("PROJECT_DOMAIN", ""),
        "ROLES_SECTION": roles_section or stored.get("ROLES_SECTION", ""),
        "VAULT_ROOT": vault_prefix.rstrip("/") or ".",
        "VAULT_PREFIX": vault_prefix,
        "BRIEFING_NOTE": briefing,
        "WIKI_SKILL": args.wiki_skill or stored.get("WIKI_SKILL", "wiki-sync"),
        "VAULT_AT_REPO_ROOT": "true" if vault_prefix == "" else "false",
        "date": str(date.today()),
    }

    mapping = {}
    for spec in args.map:
        if "=" not in spec:
            print(f"✗ --map needs SRC=DEST, got: {spec}", file=sys.stderr)
            return 2
        k, v = spec.split("=", 1)
        mapping[k.strip()] = v.strip()

    hashes = read_json(HASHES_PATH, {})
    mode = detect_mode(target, vault_prefix, manifest)
    actions, migrations = build_plan(target, vault_prefix, tokens, briefing,
                                     manifest, hashes, mapping)

    if mode == "verify":
        actions = [a for a in actions if a["action"] != "add"] + \
                  [dict(a, action="conflict", note="present upstream, missing here")
                   for a in actions if a["action"] == "add"]

    if args.json:
        print(json.dumps({"chironVersion": version(), "mode": mode,
                          "vaultRoot": vault_prefix.rstrip("/") or ".",
                          "tokens": tokens, "migrations": migrations,
                          "actions": actions}, indent=2))
        return 1 if any(a["action"] in ("conflict", "review", "keep") for a in actions) else 0

    # No verify-mode short-circuit: with nothing writable, apply_plan only recomputes the
    # manifest, and that is sometimes exactly the repair needed — a --map given on a run
    # whose file came out CONFLICT has no other way to be recorded.
    if args.apply:
        new_manifest = apply_plan(target, vault_prefix, tokens, briefing,
                                  actions, migrations, manifest)
        mpath = target / vault_prefix / MANIFEST_REL
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(new_manifest, indent=2) + "\n", encoding="utf-8")
        rc = report(mode, actions, migrations, applied=True)
        print(f"✓ manifest written: {mpath.relative_to(target)}")
        return rc

    return report(mode, actions, migrations, applied=False)


if __name__ == "__main__":
    sys.exit(main())
