#!/usr/bin/env python3
"""Bring a delivered register (xlsx) into an archive collection note.

The collection note is the master (vault map: archive rule). A register is an input:

    register-import.py init  <register.xlsx> <collection-note.md> [--key COL,COL]  # first fill of the transcription
    register-import.py diff  <register.xlsx> <collection-note.md>                  # list new / changed / note-only rows
    register-import.py apply <register.xlsx> <collection-note.md> --rows 12,40     # take these register rows over

The transcription lives between `<!-- register:begin key=COL,COL -->` and `<!-- register:end -->` in the
note. Rows are matched on the key columns, by header NAME (default: the register's first two columns);
`init` records the key in the begin marker so every later run uses the same one. Rows with the same key
are paired in order, and `apply` updates exactly the note row that `diff` paired.

`apply` never drops anything from the note: columns the note has and the register lacks are kept, columns
new in the register are appended, and only the requested rows change. Newlines in cells are written as
" / ". No third-party packages: the xlsx is read as zipped XML (first sheet in workbook order).
"""
import re, sys, zipfile, xml.etree.ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
BEGIN_RE = re.compile(r"<!-- register:begin(?: key=([^>]*?))? -->")
END = "<!-- register:end -->"


def first_sheet(z):
    """Path of the first worksheet in workbook order (not necessarily sheet1.xml)."""
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        sheet = wb.find("m:sheets/m:sheet", NS)
        rid = sheet.get("{%s}id" % NS["r"])
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        for rel in rels.findall("rel:Relationship", NS):
            if rel.get("Id") == rid:
                t = rel.get("Target").lstrip("/")
                return t if t.startswith("xl/") else "xl/" + t
    except (KeyError, AttributeError, ET.ParseError):
        pass
    return "xl/worksheets/sheet1.xml"


def clean(s):
    return re.sub(r"\s*\n\s*", " / ", s).replace("|", "\\|").strip()


def read_xlsx(path):
    z = zipfile.ZipFile(path)
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            ss.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    rows = []
    for r in ET.fromstring(z.read(first_sheet(z))).iter("{%s}row" % NS["m"]):
        row = {}
        for c in r.findall("m:c", NS):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            v, t = c.find("m:v", NS), c.get("t")
            if t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
            elif v is None:
                continue
            elif t == "s":
                val = ss[int(v.text)]
            else:
                val = v.text
            if val.strip():
                row[col] = val.strip()
        if row:
            rows.append(row)
    if not rows:
        sys.exit(f"{path}: the first sheet is empty")
    head, body = rows[0], rows[1:]
    letters = sorted(head, key=lambda x: (len(x), x))
    cols, seen = [], {}
    for L in letters:                                   # duplicate header names get a _2, _3 suffix
        name = clean(head[L]) or L
        seen[name] = seen.get(name, 0) + 1
        cols.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return cols, [{c: clean(r.get(L, "")) for c, L in zip(cols, letters)} for r in body]


def split_cells(line):
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]


def read_note(path):
    s = open(path, encoding="utf-8").read()
    m = BEGIN_RE.search(s)
    if not m or END not in s[m.end():]:
        return s, None, [], []
    key = [k.strip() for k in m.group(1).split(",")] if m.group(1) else []
    block = s[m.end():s.index(END, m.end())]
    lines = [l for l in block.strip().splitlines() if l.startswith("|")]
    if len(lines) < 2:
        return s, key, [], []
    cols = split_cells(lines[0])[1:]                    # drop the "#" column
    rows = [dict(zip(cols, split_cells(l)[1:])) for l in lines[2:]]
    return s, key, cols, rows


def table(cols, rows):
    out = ["| # | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for i, r in enumerate(rows, 1):
        out.append(f"| {i} | " + " | ".join(r.get(c, "") for c in cols) + " |")
    return "\n".join(out)


def write_block(path, s, key, cols, rows):
    blk = f"<!-- register:begin key={','.join(key)} -->\n{table(cols, rows)}\n{END}"
    m = BEGIN_RE.search(s)
    if m:
        s = s[:m.start()] + blk + s[s.index(END, m.end()) + len(END):]
    else:
        # first fill: under a "## Transcription" heading, replacing a placeholder table there
        h = re.search(r"^## Transcription[^\n]*\n", s, re.M)
        if h:
            rest = s[h.end():]
            t = re.match(r"(?:[^\n|#][^\n]*\n|\n)*?((?:\|[^\n]*\n)+)", rest)
            if t and not rest[:t.start(1)].count("\n## "):
                s = s[:h.end()] + rest[:t.start(1)] + blk + "\n" + rest[t.end(1):]
            else:
                s = s[:h.end()] + "\n" + blk + "\n" + rest
        else:
            s = s.rstrip() + "\n\n" + blk + "\n"
    open(path, "w", encoding="utf-8").write(s)


def rowkey(r, key):
    return tuple(r.get(k, "").split(" / ")[0].strip().lower() for k in key)


def pair(rrows, nrows, key):
    """Pair register rows with note rows by key, in order. Returns (pairs, register-only, note-only)."""
    pool = {}
    for i, r in enumerate(nrows):
        pool.setdefault(rowkey(r, key), []).append(i)
    pairs, new = {}, []
    for i, r in enumerate(rrows, 1):
        cand = pool.get(rowkey(r, key))
        if cand:
            pairs[i] = cand.pop(0)
        else:
            new.append(i)
    used = set(pairs.values())
    return pairs, new, [j for j in range(len(nrows)) if j not in used]


def main():
    args = sys.argv[1:]
    if len(args) < 3 or args[0] not in ("diff", "init", "apply"):
        print(__doc__); sys.exit(2)
    mode, xlsx, note = args[:3]
    rcols, rrows = read_xlsx(xlsx)
    s, key, ncols, nrows = read_note(note)
    if "--key" in args:
        key = [k.strip() for k in args[args.index("--key") + 1].split(",")]
    key = key or rcols[:2]
    if any("," in k for k in key):
        sys.exit("a key column name may not contain a comma (it is stored as key=a,b in the note)")
    missing = [k for k in key if k not in rcols]
    if missing:
        sys.exit(f"key column(s) {missing} not in the register's header {rcols}")
    if mode == "init":
        if nrows:
            sys.exit("the note already has a transcription; use diff / apply")
        write_block(note, s, key, rcols, rrows); print(f"wrote {len(rrows)} rows, key {key}"); return
    pairs, new, note_only = pair(rrows, nrows, key)
    label = lambda r: " ".join(r.get(k, "")[:40] for k in key)
    if mode == "diff":
        if set(rcols) != set(ncols):
            print("COLUMNS only in register:", [c for c in rcols if c not in ncols],
                  "| only in note:", [c for c in ncols if c not in rcols])
        n = 0
        for i, r in enumerate(rrows, 1):
            if i in new:
                print(f"NEW           register row {i:>3}  {label(r)}"); n += 1
            else:
                d = {c: (nrows[pairs[i]].get(c, ""), r[c]) for c in rcols if nrows[pairs[i]].get(c, "") != r[c]}
                if d:
                    n += 1
                    print(f"CHANGED       register row {i:>3}  {label(r)}  (note row {pairs[i] + 1})")
                    for c, (a, b) in d.items():
                        print(f"      {c}: note={a!r}\n      {' ' * len(c)}  reg ={b!r}")
        for j in note_only:
            print(f"ONLY IN NOTE  note row {j + 1:>3}  {label(nrows[j])}"); n += 1
        print(f"{n} difference(s)"); return
    if "--rows" not in args:
        sys.exit("apply needs --rows <register row numbers from diff>")
    want = [int(x) for x in args[args.index("--rows") + 1].split(",")]
    cols = ncols + [c for c in rcols if c not in ncols]  # keep every note column, append new ones
    done = 0
    for i in want:
        if not 1 <= i <= len(rrows):
            print(f"skipped register row {i}: out of range"); continue
        if i in new:
            nrows.append(dict(rrows[i - 1])); done += 1
        else:
            nrows[pairs[i]].update(rrows[i - 1]); done += 1
    write_block(note, s, key, cols, nrows)
    print(f"applied {done} row(s)")


if __name__ == "__main__":
    main()
