#!/usr/bin/env python3
"""Archive-module checks (vault-map: collections/ and people/).

    python3 aiOS/tools/vault/archive-lint.py [--quiet]

[COLL-KIND]   a collection note (atlas/collections/*.md, not the hub) lacks kind: objects | photos | documents
[COLL-UP]     a transcription note in a collection subfolder does not point up to a collection note
[PERSON-NAME] a person note's basename is not lastname_firstname style (lowercase a-z, 0-9, _)
[PERSON-UP]   a person note does not point up to [[people]]
[PERSON-DATA] a person note contains a forbidden kind of personal data (birth date, address, health, contact)
[MASTER]      a person note's rows sourced to a master list disagree with that list

Master lists are optional, in aiOS/aios.config.json:

    "archive": {"masterLists": [{"note": "atlas/concepts/kings.md", "link": "[[kings]]",
                                 "rowLabels": ["King", "Emperor"]}]}

A master list note holds table rows `| <year> | <name> (<variant>) | ...`; a person note's history
rows `| <year> | <label> ... | <link> |` must give the same years for the names in its aliases.
Exit 1 when anything is reported.
"""
import os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault_lib as V  # noqa: E402

COLL, PEOPLE = V.SOURCE_DIR / "atlas/collections", V.SOURCE_DIR / "atlas/people"
KINDS = {"objects", "photos", "documents"}
FORBIDDEN = [
    (r"\bgeboren\b|\bgeboorte\w*|\bgeb\.\s*\d|\bborn\b|\bbirth(day|date)?\b|\bdate of birth\b", "birth date", re.I),
    (r"\b(woont|woonachtig|woonadres|adres|address|lives at)\b", "address", re.I),
    (r"\b(ziek|ziekte|ziekten|ziekbed|kanker|cancer|illness|disease|diagnos\w*|surgery|operatie|gezondheid|health)\b", "health", re.I),
    (r"\b(telefoon\w*|tel\.|phone|e-?mail)\b|[\w.+-]+@[\w-]+\.[\w.]+|(?<![\d-])(?:\+31|0031|06)[\s-]?\d{8}(?![\d-])|(?<![\d-])0\d{2,3}[\s-]\d{6,7}(?![\d-])", "contact", re.I),
]
COMMENT = re.compile(r"<!--.*?-->", re.S)


def split(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return (m.group(1), text[m.end():]) if m else ("", text)


def master_years(cfg):
    path = V.SOURCE_DIR / cfg["note"]
    out = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\| (\d{4}(?:[–-]\d{2,4})?) \| ([^|]+?) \|", line)
        if not m:
            continue
        y, cell = m.group(1).replace("–", "-"), re.sub(r"\s*·.*$", "", m.group(2))
        for nm in [re.sub(r"\s*\(.*\)", "", cell)] + re.findall(r"\(([^)]+)\)", cell):
            out.setdefault(nm.strip().strip("*").strip(), set()).add(y)
    return out


def main():
    quiet = "--quiet" in sys.argv
    out = []
    if COLL.is_dir():
        for p in sorted(COLL.rglob("*.md")):
            fm, _ = split(p.read_text(encoding="utf-8"))
            rel = p.relative_to(V.SOURCE_DIR).as_posix()
            if p.parent == COLL:
                if p.name == "collections.md":
                    continue
                m = re.search(r"^kind:\s*[\"']?([\w-]+)", fm, re.M)
                if not m or m.group(1) not in KINDS:
                    out.append(f"[COLL-KIND] {rel}: kind must be one of {sorted(KINDS)}")
            elif not re.search(r'up:\s*\[\s*"\[\[', fm):
                out.append(f"[COLL-UP] {rel}: up: must point to its collection note")
    masters = [(c, master_years(c)) for c in V.CONFIG.get("archive", {}).get("masterLists", [])]
    if PEOPLE.is_dir():
        for p in sorted(PEOPLE.rglob("*.md")):
            if p.name == "people.md":
                continue
            fm, body = split(p.read_text(encoding="utf-8"))
            rel = p.relative_to(V.SOURCE_DIR).as_posix()
            if not re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*\.md", p.name):
                out.append(f"[PERSON-NAME] {rel}")
            if '"[[people]]"' not in fm:
                out.append(f"[PERSON-UP] {rel}")
            text = COMMENT.sub("", fm + "\n" + body)
            for rx, what, fl in FORBIDDEN:
                m = re.search(rx, text, fl)
                if m:
                    out.append(f"[PERSON-DATA] {rel}: possible {what} ({m.group(0)!r})")
            am = re.search(r"^aliases:\s*\[(.*)\]", fm, re.M)
            aliases = re.findall(r'"([^"]+)"', am.group(1)) if am else []
            for cfg, years in masters:
                labels = "|".join(map(re.escape, cfg.get("rowLabels", [""])))
                mine = {m.group(1) for m in re.finditer(
                    r"^\| ([\d-]+) \| (?:%s)\b[^|]*\| %s \|" % (labels, re.escape(cfg["link"])), body, re.M)}
                expected = set().union(*[years.get(a, set()) for a in aliases]) if aliases else set()
                if mine and not expected:
                    out.append(f"[MASTER] {rel}: rows {sorted(mine)} but no matching name in {cfg['note']}")
                elif mine and not mine <= expected:      # a split doubtful identity may hold a subset
                    out.append(f"[MASTER] {rel}: note {sorted(mine)} vs {cfg['note']} {sorted(expected)}")
    for o in out:
        print(o)
    if not quiet or out:
        print(f"archive-lint: {len(out)} issue(s)")
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
