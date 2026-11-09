#!/usr/bin/env python3
"""Bring a delivered register (xlsx) into an archive collection note.

The collection note is the master (vault-map: archive rule). A register is an input:

    register-import.py diff  <register.xlsx> <collection-note.md>   # list new / changed / missing rows
    register-import.py init  <register.xlsx> <collection-note.md>   # first fill of the transcription block
    register-import.py apply <register.xlsx> <collection-note.md> --rows 12,40   # take these register rows over

Rows are matched on (jaar, first line of naam). The transcription lives between
`<!-- register:begin -->` and `<!-- register:end -->` in the note. Newlines in cells are written as " / ".
Columns are taken from the register's header row, so a renamed or added column shows up in `diff`.
No third-party packages: the xlsx is read as zipped XML.
"""
import re, sys, zipfile, xml.etree.ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
BEGIN, END = "<!-- register:begin -->", "<!-- register:end -->"


def read_xlsx(path):
    z = zipfile.ZipFile(path)
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            ss.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    rows = []
    for r in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter("{%s}row" % NS["m"]):
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
    head, body = rows[0], rows[1:]
    cols = [head[k] for k in sorted(head, key=lambda x: (len(x), x))]
    keyof = {head[k]: k for k in head}
    return cols, [{c: clean(r.get(keyof[c], "")) for c in cols} for r in body]


def clean(s):
    return re.sub(r"\s*\n\s*", " / ", s).replace("|", "\\|").strip()


def rowkey(r, cols):
    return (r.get(cols[0], ""), r.get(cols[2] if len(cols) > 2 and cols[1] == "tot" else cols[1], "").split(" / ")[0].lower())


def table(cols, rows):
    out = ["| # | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for i, r in enumerate(rows, 1):
        out.append(f"| {i} | " + " | ".join(r.get(c, "") for c in cols) + " |")
    return "\n".join(out)


def read_note(path):
    s = open(path, encoding="utf-8").read()
    if BEGIN not in s:
        return s, None, []
    block = s[s.index(BEGIN) + len(BEGIN):s.index(END)]
    lines = [l for l in block.strip().splitlines() if l.startswith("|")]
    if len(lines) < 2:
        return s, None, []
    cols = [c.strip() for c in re.split(r"(?<!\\)\|", lines[0])[2:-1]]
    rows = []
    for l in lines[2:]:
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", l)[2:-1]]
        rows.append(dict(zip(cols, cells)))
    return s, cols, rows


def write_block(path, s, cols, rows):
    blk = f"{BEGIN}\n{table(cols, rows)}\n{END}"
    s = s[:s.index(BEGIN)] + blk + s[s.index(END) + len(END):] if BEGIN in s else s.rstrip() + "\n\n" + blk + "\n"
    open(path, "w", encoding="utf-8").write(s)


def diff(rcols, rrows, ncols, nrows):
    if ncols != rcols:
        print("COLUMNS register:", rcols, "\n        note:    ", ncols)
    nmap = {}
    for r in nrows:
        nmap.setdefault(rowkey(r, ncols), []).append(r)
    seen = set()
    changes = []
    for i, r in enumerate(rrows, 1):
        k = rowkey(r, rcols)
        cand = [x for x in nmap.get(k, []) if id(x) not in seen]
        if not cand:
            changes.append(("NEW", i, r, None)); continue
        n = cand[0]; seen.add(id(n))
        d = {c: (n.get(c, ""), r.get(c, "")) for c in rcols if n.get(c, "") != r.get(c, "")}
        if d:
            changes.append(("CHANGED", i, r, d))
    for r in nrows:
        if id(r) not in seen:
            changes.append(("ONLY IN NOTE", None, r, None))
    return changes


def main():
    if len(sys.argv) < 4 or sys.argv[1] not in ("diff", "init", "apply"):
        print(__doc__); sys.exit(2)
    mode, xlsx, note = sys.argv[1:4]
    rcols, rrows = read_xlsx(xlsx)
    s, ncols, nrows = read_note(note)
    if mode == "init":
        if nrows:
            sys.exit("note already has a transcription; use diff / apply")
        write_block(note, s, rcols, rrows); print(f"wrote {len(rrows)} rows"); return
    changes = diff(rcols, rrows, ncols or [], nrows)
    if mode == "diff":
        for kind, i, r, d in changes:
            label = f"{r.get(rcols[0], '')} {r.get('naam', '')[:40]}"
            print(f"{kind:13} register row {i or '-':>3}  {label}")
            for c, (a, b) in (d or {}).items():
                print(f"      {c}: note={a!r}\n      {' ' * len(c)}  reg ={b!r}")
        print(f"{len(changes)} difference(s)"); return
    want = {int(x) for x in sys.argv[sys.argv.index("--rows") + 1].split(",")} if "--rows" in sys.argv else set()
    if not want:
        sys.exit("apply needs --rows <register row numbers from diff>")
    by_key = {}
    for r in nrows:
        by_key.setdefault(rowkey(r, ncols), []).append(r)
    for kind, i, r, d in changes:
        if i in want:
            if kind == "NEW":
                nrows.append(r)
            elif kind == "CHANGED":
                by_key[rowkey(r, rcols)][0].update(r)
    write_block(note, s, rcols, nrows); print(f"applied {len(want)} row(s)")


if __name__ == "__main__":
    main()
