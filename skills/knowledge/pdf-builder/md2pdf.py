#!/usr/bin/env python3
"""
md2pdf.py — render a vault markdown note to PDF.

    python3 .claude/skills/pdf-builder/md2pdf.py <note.md> [-o out.pdf] [--keep-html]

Pipeline: markdown -> HTML (python-markdown) -> headless Chrome --print-to-pdf.
No Obsidian involved. Pagination rules live in pdf.css next to this file.

Handles the Obsidian dialect the vault actually uses: YAML frontmatter,
[[wikilinks]], > [!callouts], ```mermaid fences, and the hard page-break divs.
Adds a contents list and a References appendix built from `sources:`, because a
note handed to someone outside the team has to be checkable.
"""

from __future__ import annotations

import argparse
import html as htmllib
import pathlib
import re
import subprocess
import zlib
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
CSS = HERE / "pdf.css"
MERMAID_CACHE = HERE / ".mermaid.min.js"          # gitignored; fetched on first use
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]

# Tolerant of the forms Obsidian accepts: `>[!note]`, `> [!note]`, and the
# fold markers `> [!note]-` / `> [!note]+`.
CALLOUT_RE = re.compile(
    r'^>[ \t]*\[!(?P<kind>[A-Za-z]+)\][-+]?[ \t]*(?P<title>.*)\n'
    r'(?P<body>(?:>.*\n?)*)', re.M)


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if pathlib.Path(c).exists():
            return c
    sys.exit("error: no Chrome/Chromium/Edge found — install one, or edit CHROME_CANDIDATES.")


def mermaid_js() -> str | None:
    """Return the mermaid bundle, fetching and caching it once. None if unavailable."""
    if MERMAID_CACHE.exists():
        return MERMAID_CACHE.read_text(encoding="utf-8")
    try:
        with urllib.request.urlopen(MERMAID_URL, timeout=30) as r:
            js = r.read().decode("utf-8")
        MERMAID_CACHE.write_text(js, encoding="utf-8")
        return js
    except Exception as e:                                    # offline, proxy, etc.
        print(f"  ! mermaid unavailable ({e.__class__.__name__}) — diagrams will "
              f"render as source blocks", file=sys.stderr)
        return None


def strip_frontmatter(text: str) -> tuple[str, str | None]:
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        return text, None
    title = None
    for line in m.group(1).splitlines():
        if line.startswith("title:"):
            title = line.split(":", 1)[1].strip().strip('"\'')
    return text[m.end():], title



# Below this many top-level sections a contents list is noise, not navigation.
TOC_MIN_HEADINGS = 6


def frontmatter_scalar(text: str, name: str) -> str:
    """A single-line frontmatter value, unquoted. Empty string when absent."""
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        return ''
    found = re.search(rf'^{re.escape(name)}:[ \t]*(.*)$', m.group(1), re.M)
    if not found:
        return ''
    value = found.group(1).strip().strip('"\'')
    return '' if value.startswith('[') and value.endswith(']') and not value[1:-1].strip() else value


def frontmatter_list(text: str, name: str) -> list[str]:
    """An inline `name: ["a", "b"]` list. Block lists are not used for these fields."""
    raw = frontmatter_scalar(text, name)
    if not (raw.startswith('[') and raw.endswith(']')):
        return [raw] if raw else []
    return [a or b for a, b in re.findall(r'"([^"]*)"|\'([^\']*)\'', raw) if (a or b)]


def cover_html(text: str) -> str:
    """The metadata block that turns page one into a title page.

    A cover carrying only an `<h1>` reads as a mistake, and a cover carrying the
    summary is not a cover — the reader meets the conclusion before the contents.
    Frontmatter already holds who wrote it, who it is for and when, so the cover is
    built from that rather than from anything the author has to remember to repeat.
    """
    rows = []
    author = frontmatter_scalar(text, 'author')
    if author:
        rows.append(('Author', author))
    audience = frontmatter_list(text, 'audience')
    if audience:
        rows.append(('Audience', ', '.join(audience)))
    created, updated = (frontmatter_scalar(text, 'created'),
                        frontmatter_scalar(text, 'updated'))
    if created:
        rows.append(('Researched', created))
    if updated and updated != created:
        rows.append(('Revised', updated))
    if not rows:
        return ''
    cells = ''.join(
        f'<div class="cover-key">{htmllib.escape(k)}</div>'
        f'<div class="cover-val">{htmllib.escape(v)}</div>' for k, v in rows)
    return f'<div class="cover-meta">{cells}</div>'


def frontmatter_sources(text: str) -> list[str]:
    """The `sources:` entries, in order. Handles the inline and block YAML forms.

    Deliberately a small parser rather than a YAML dependency: this runs on every
    render, and the two shapes the vault actually uses are both trivial.
    """
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        return []
    fm = m.group(1)
    found = re.search(r'^sources:[ \t]*(.*)$', fm, re.M)
    if not found:
        return []
    inline = found.group(1).strip()
    if inline.startswith('['):
        pairs = re.findall(r'"([^"]*)"|\'([^\']*)\'', inline)
        return [a or b for a, b in pairs if (a or b)]
    out: list[str] = []
    for line in fm[found.end():].splitlines():
        if not line.strip():
            continue
        if not line.startswith((' ', '\t')):
            break
        entry = line.strip()
        if not entry.startswith('- '):
            break
        out.append(entry[2:].strip().strip('"\''))
    return out


def split_reference(source: str) -> tuple[str, str, str]:
    """A `sources:` entry as (label, locator, provenance).

    Entries are free-form by convention — `<url> (<label> — <how it was read>, <date>)`
    is the common shape, but a repo path or a vault note is equally valid. Rendering
    them as one long run per line is what made the appendix unreadable: the URL is the
    least interesting part and was taking the most room, while the label and the date
    — the two things a reader actually checks — were buried mid-line.
    """
    locator, rest = '', source.strip()
    found = re.match(r'(https?://[^\s)]+)\s*(.*)$', rest)
    if found:
        locator, rest = found.group(1), found.group(2).strip()
    if rest.startswith('(') and rest.endswith(')'):
        rest = rest[1:-1].strip()

    provenance = ''
    # The clause naming how and when it was read, wherever it sits in the entry, so
    # a description after the date stays in the label instead of being absorbed.
    tail = re.search(r'(?:via search summary|fetched|inspected read-only)'
                     r'[^,;()]*?,?\s*\d{4}-\d{2}-\d{2}', rest, re.IGNORECASE)
    if tail:
        provenance = tail.group(0).strip(' ,;—')
        head, tail_text = (rest[:tail.start()].strip(' ,;—:'),
                           rest[tail.end():].strip(' ,;—:'))
        # Rejoin with a separator, not a bare space: the provenance clause sat
        # *between* two halves of the label, and fusing them produced
        # "MMP pricing pricing decays" in the appendix that was handed over.
        rest = '; '.join(part for part in (head, tail_text) if part)
    return rest, locator, provenance


def references_html(sources: list[str]) -> str:
    """A References appendix, one entry per row: what it is, where, how it was read."""
    if not sources:
        return ''
    items = []
    for source in sources:
        label, locator, provenance = split_reference(source)
        parts = []
        if label:
            parts.append(f'<span class="ref-label">{htmllib.escape(label)}</span>')
        if locator:
            safe = htmllib.escape(locator)
            parts.append(f'<span class="ref-loc"><a href="{safe}">{safe}</a></span>')
        if not label and not locator:
            parts.append(f'<span class="ref-label">{htmllib.escape(source)}</span>')
        if provenance:
            parts.append(f'<span class="ref-prov">{htmllib.escape(provenance)}</span>')
        items.append('<li>' + ''.join(parts) + '</li>')
    return ('<h2 id="references">References</h2>'
            f'<ol class="references">{"".join(items)}</ol>')


def flatten_toc(tokens: list) -> list:
    """Every heading token, depth-first.

    `toc_tokens` is a tree, not a list: with an `# H1` present every `##` arrives as
    its *child*, so a flat scan for level 2 finds nothing and the contents list
    silently never appears.
    """
    out = []
    for token in tokens:
        out.append(token)
        out.extend(flatten_toc(token.get('children') or []))
    return out


def toc_html(tokens: list, with_references: bool = False) -> str:
    """Two levels of contents: `##` sections and the `###` beneath each.

    Unordered on purpose. Section headings in this vault carry their own numbers
    ("0. How to read this"), and an `<ol>` renders its own on top of them — the
    first entry came out as "1. 0. How to read this".

    `with_references` adds the generated appendix, which is appended *after* this
    runs and so is invisible to `toc_tokens` — without it the citations are the one
    section a reader cannot navigate to.
    """
    sections = [t for t in flatten_toc(tokens) if t.get('level') == 2]
    if len(sections) < TOC_MIN_HEADINGS:
        return ''

    def entry(token: dict) -> str:
        return (f'<a href="#{token["id"]}">'
                f'{htmllib.escape(token["name"])}</a>')

    items = []
    for section in sections:
        subs = [c for c in (section.get('children') or []) if c.get('level') == 3]
        nested = ''
        if subs:
            nested = ('<ul class="toc-sub">'
                      + ''.join(f'<li>{entry(c)}</li>' for c in subs)
                      + '</ul>')
        items.append(f'<li>{entry(section)}{nested}</li>')
    if with_references:
        items.append('<li><a href="#references">References</a></li>')
    return f'<nav class="toc"><h2>Contents</h2><ul>{"".join(items)}</ul></nav>'


def insert_toc(body: str, toc: str) -> str:
    """Immediately after the cover, so the contents is page two.

    Falls back to the first `##`, then to the `<h1>`, for a note with no cover block.
    """
    if not toc:
        return body
    cover_end = body.find('</header>')
    if cover_end != -1:
        cover_end += len('</header>')
        return body[:cover_end] + toc + body[cover_end:]
    first_section = re.search(r'<h2[\s>]', body)
    if first_section:
        return body[:first_section.start()] + toc + body[first_section.start():]
    close = body.find('</h1>')
    if close == -1:
        return toc + body
    return body[:close + len('</h1>')] + toc + body[close + len('</h1>'):]


def convert_callouts(text: str) -> str:
    def repl(m):
        kind = m.group("kind").lower()
        title = m.group("title").strip() or kind.capitalize()
        body = re.sub(r'^> ?', '', m.group("body"), flags=re.M).strip()
        import markdown as _md
        inner = _md.markdown(body, extensions=["tables", "sane_lists"]) if body else ""
        return (f'\n<div class="callout callout-{kind}" markdown="0">'
                f'<div class="callout-title">{htmllib.escape(title)}</div>'
                f'<div class="callout-body">{inner}</div></div>\n\n')
    return CALLOUT_RE.sub(repl, text)


def convert_wikilinks(text: str) -> str:
    """[[Target|alias]] -> alias, [[Target]] -> Target. A PDF reader cannot follow them."""
    text = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', text)
    return re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)


def extract_mermaid(text: str) -> tuple[str, list[str]]:
    blocks: list[str] = []

    def repl(m):
        blocks.append(m.group(1))
        return f'\n@@MERMAID{len(blocks) - 1}@@\n'
    text = re.sub(r'```mermaid\n(.*?)```', repl, text, flags=re.S)
    return text, blocks


def build_html(md_path: pathlib.Path, with_mermaid: bool, with_toc: bool = True,
               with_references: bool = True) -> tuple[str, int, list[str]]:
    try:
        import markdown
    except ImportError:
        sys.exit("error: python-markdown missing — pip3 install --user markdown")

    raw = md_path.read_text(encoding="utf-8")
    raw_text = raw
    sources = frontmatter_sources(raw)
    raw, fm_title = strip_frontmatter(raw)
    raw, diagrams = extract_mermaid(raw)
    raw = convert_wikilinks(raw)
    raw = convert_callouts(raw)

    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list", "md_in_html",
                    "toc"])
    body = md.convert(raw)
    # Split the title off, so the cover is a cover: the summary and the constraint
    # that sit between the `# title` and the first `##` move behind the contents.
    h1_end = body.find('</h1>')
    first_section = re.search(r'<h2[\s>]', body)
    if h1_end != -1 and first_section and first_section.start() > h1_end:
        h1_end += len('</h1>')
        title_block = body[:h1_end]
        front_matter = body[h1_end:first_section.start()]
        body = (f'<header class="cover">{title_block}{cover_html(raw_text)}</header>'
                + front_matter + body[first_section.start():])

    refs = references_html(sources) if with_references else ''
    # Belt and braces with the template: a note that writes its own `## References`
    # would otherwise get a second <h2 id="references">, and the contents anchor
    # resolves to whichever came first — the prose, not the citations.
    body_has_references = bool(re.search(r'<h2[^>]*>References</h2>', body))
    if refs and body_has_references:
        refs = refs.replace('<h2 id="references">References</h2>',
                            '<h3 id="references-list">Cited sources</h3>', 1)
    if with_toc:
        # Only add the contents entry when the appendix owns the `#references`
        # anchor. When the body already has that heading, `toc_tokens` carries it
        # and appending a second entry lists References twice, both resolving to
        # the prose — the navigation failure the demotion was meant to end.
        body = insert_toc(body, toc_html(getattr(md, "toc_tokens", []),
                                         bool(refs) and not body_has_references))
    body += refs

    for i, src in enumerate(diagrams):
        if with_mermaid:
            rep = f'<pre class="mermaid">{htmllib.escape(src)}</pre>'
        else:
            rep = (f'<pre class="mermaid-unrendered">[diagram not rendered]\n'
                   f'{htmllib.escape(src)}</pre>')
        body = body.replace(f'<p>@@MERMAID{i}@@</p>', rep).replace(f'@@MERMAID{i}@@', rep)

    js = ""
    if with_mermaid and diagrams:
        bundle = mermaid_js()
        if bundle:
            js = (f'<script>{bundle}</script>'
                  '<script>mermaid.initialize({startOnLoad:true,theme:"neutral",'
                  'flowchart:{useMaxWidth:true},htmlLabels:true});</script>')
        else:
            for i, src in enumerate(diagrams):
                body = body.replace(
                    f'<pre class="mermaid">{htmllib.escape(src)}</pre>',
                    f'<pre class="mermaid-unrendered">[diagram not rendered]\n'
                    f'{htmllib.escape(src)}</pre>')

    structure = audit_structure(body, getattr(md, 'toc_tokens', []))

    title = fm_title or md_path.stem
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<title>{htmllib.escape(title)}</title>'
            f'<style>{CSS.read_text(encoding="utf-8")}</style></head>'
            f'<body>{body}{js}</body></html>'), len(diagrams), structure


def page_count(pdf: pathlib.Path) -> int:
    b = pdf.read_bytes()
    for a, c in ((b"/Type /Page", b"/Type /Pages"), (b"/Type/Page", b"/Type/Pages")):
        n = b.count(a) - b.count(c)
        if n > 0:
            return n
    return 0


# A page carrying no glyphs is almost always a layout bug, not a choice — an empty
# block with `break-after: page` that landed at the top of a fresh page, or two
# breaks in a row. One reached a document that had already been sent, and nothing
# in the pipeline could have told us: the renderer reports a page *count*, and a
# blank page is indistinguishable from a real one by count alone.
BLANK_GLYPH_OPS = 3
THIN_GLYPH_OPS = 150


def pdf_pages_in_order(pdf: pathlib.Path) -> list[bytes]:
    """Each page's decoded content stream, in reading order.

    Page objects are not stored in page order, so the `/Kids` tree is what gives
    the sequence — numbering the objects instead reports the wrong page.
    """
    raw = pdf.read_bytes()
    objects = {int(m.group(1)): m.group(2)
               for m in re.finditer(rb'(\d+)\s+0\s+obj\b(.*?)\bendobj', raw, re.S)}
    kids: list[int] = []
    for body in objects.values():
        if b'/Type /Pages' in body:
            kids += [int(x) for x in re.findall(rb'(\d+)\s+0\s+R', body)]
    pages = [k for k in kids
             if k in objects and re.search(rb'/Type\s*/Page[^s]', objects[k])]

    def stream(num: int) -> bytes:
        body = objects.get(num, b'')
        start = re.search(rb'stream\r?\n', body)
        if not start:
            return b''
        data = body[start.end():body.rfind(b'endstream')]
        for attempt in (data, data.rstrip(b'\r\n')):
            try:
                return zlib.decompress(attempt)
            except zlib.error:
                pass
        return data

    out = []
    for page in pages:
        ref = re.search(rb'/Contents\s+(\d+)\s+0\s+R', objects[page])
        out.append(stream(int(ref.group(1))) if ref else b'')
    return out


def audit_pages(pdf: pathlib.Path) -> tuple[list[int], list[tuple[int, int]]]:
    """(blank pages, thin pages) as 1-based numbers. Thin pages carry their count."""
    blank, thin = [], []
    for i, content in enumerate(pdf_pages_in_order(pdf), 1):
        glyphs = len(re.findall(rb'\bTj\b|\bTJ\b', content))
        if glyphs < BLANK_GLYPH_OPS:
            blank.append(i)
        elif glyphs < THIN_GLYPH_OPS:
            thin.append((i, glyphs))
    return blank, thin


def audit_structure(body: str, toc_tokens: list) -> list[str]:
    """Structural problems the page audit cannot see, because they render fine.

    Each shipped at least once: a heading level skipped (section 9's parts sat at
    `####` under a `##`, so the contents reduced a nine-part ask to one line), two
    headings reading the same, and **two contents entries pointing at the same
    anchor** — the last being the defect this was written after.
    """
    problems = []

    levels = [(int(m.group(1)), re.sub(r'<[^>]+>', '', m.group(2)).strip())
              for m in re.finditer(r'<h([1-6])[^>]*>(.*?)</h\1>', body, re.S)]
    for (prev_level, _), (level, name) in zip(levels, levels[1:]):
        if level > prev_level + 1:
            problems.append(
                f'heading level skips h{prev_level} → h{level} at "{name[:48]}" — '
                f'the contents lists one level, so anything below it disappears')

    seen: dict[str, int] = {}
    for _, name in levels:
        seen[name.lower()] = seen.get(name.lower(), 0) + 1
    for name, count in seen.items():
        if count > 1:
            # python-markdown de-duplicates ids (`references`, `references_1`), so the
            # anchors differ — the damage is that two contents rows read identically
            # and a hand-written `#references` link silently resolves to the first.
            problems.append(
                f'{count} headings read "{name[:48]}" — the contents cannot '
                f'distinguish them, and a link to the plain anchor reaches the first')

    ids = re.findall(r'<h[1-6][^>]*\bid="([^"]+)"', body)
    for anchor_id in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f'duplicate heading id "{anchor_id}" — '
                        f'every link to it resolves to whichever came first')

    # The contents is generated after the headings, so a wrong entry there is not
    # visible in the heading list at all. Two rows pointing at one anchor is exactly
    # what shipped: References appeared twice and the citations were unreachable.
    nav = re.search(r'<nav class="toc">(.*?)</nav>', body, re.S)
    if nav:
        targets = re.findall(r'<a href="#([^"]+)"', nav.group(1))
        for target in sorted({t for t in targets if targets.count(t) > 1}):
            problems.append(
                f'the contents lists "#{target}" {targets.count(target)} times — '
                f'the rows are not distinguishable and one of them is wrong')
        heading_ids = set(ids)
        for target in sorted(set(targets)):
            if heading_ids and target not in heading_ids:
                problems.append(f'contents entry "#{target}" matches no heading — '
                                f'the link goes nowhere')
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a markdown note to PDF.")
    ap.add_argument("note")
    ap.add_argument("-o", "--out")
    ap.add_argument("--no-mermaid", action="store_true", help="skip diagram rendering")
    ap.add_argument("--no-toc", action="store_true", help="skip the contents list")
    ap.add_argument("--no-references", action="store_true",
                    help="skip the References appendix built from `sources:`")
    ap.add_argument("--keep-html", action="store_true", help="leave the intermediate .html")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if the render has a blank page")
    a = ap.parse_args()

    src = pathlib.Path(a.note).resolve()
    if not src.is_file():
        sys.exit(f"error: no such file: {src}")
    out = pathlib.Path(a.out).resolve() if a.out else src.with_suffix(".pdf")

    html_doc, n_diagrams, structure_problems = build_html(src, with_mermaid=not a.no_mermaid,
                                      with_toc=not a.no_toc,
                                      with_references=not a.no_references)
    tmp = out.with_suffix(".build.html")
    tmp.write_text(html_doc, encoding="utf-8")

    # Chrome needs real time to lay out mermaid before printing.
    budget = 12000 if n_diagrams else 3000
    r = subprocess.run(
        [find_chrome(), "--headless", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer", "--allow-file-access-from-files",
         f"--virtual-time-budget={budget}", f"--print-to-pdf={out}", tmp.as_uri()],
        capture_output=True, timeout=180)

    if not out.exists():
        sys.stderr.write(r.stderr.decode("utf-8", "replace")[-2000:])
        sys.exit("error: Chrome produced no PDF")
    if not a.keep_html:
        tmp.unlink(missing_ok=True)

    for problem in structure_problems:
        print(f"  · {problem}", file=sys.stderr)

    blank, thin = audit_pages(out)
    # The warning goes in the summary line, not only above it. A caller piping through
    # `tail` sees the last line and nothing else — which is how a NOT RECONCILED report
    # from a sibling tool got run straight past the day it was written.
    alarm = f" · ⚠ {len(blank)} BLANK PAGE{'S' if len(blank) > 1 else ''}" if blank else ""

    print(f"  {out}")
    if blank:
        print(f"  ! blank page(s): {', '.join(map(str, blank))} — almost always an "
              f"empty block carrying `break-after: page`", file=sys.stderr)
    if thin:
        print("  · very light page(s): "
              + ", ".join(f"{n} ({g} glyph runs)" for n, g in thin), file=sys.stderr)
    print(f"  {page_count(out)} pages · {out.stat().st_size // 1024} KB · "
          f"{n_diagrams} diagram(s){alarm}")

    if blank and a.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
