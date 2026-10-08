"""What md2pdf.py has to get right before Chrome ever sees the page.

The value of this suite is the Obsidian dialect: frontmatter, wikilinks, callouts and
mermaid fences all render as raw noise in a PDF if their transform is wrong, and that
failure is invisible until someone opens the file. Everything here is pure text in,
text out — no network, no Chrome, no PDF written.
"""
from __future__ import annotations

import contextlib
import io
import pathlib
import tempfile
import unittest
from unittest import mock

from _harness import HAS_MARKDOWN, m, pdf_bytes, vault_dir


class TestStripFrontmatter(unittest.TestCase):
    def test_removes_the_block_and_leaves_the_body(self):
        body, title = m.strip_frontmatter("---\ntags: [a]\n---\n# H\n\ntext\n")
        self.assertEqual(body, "# H\n\ntext\n")
        self.assertIsNone(title)

    def test_reads_a_title_field_and_strips_quotes(self):
        _, title = m.strip_frontmatter('---\ntitle: "My Doc"\n---\nbody\n')
        self.assertEqual(title, "My Doc")

    def test_sources_are_read_from_both_yaml_shapes(self):
        """`sources:` is written inline in wiki notes and as a block list in research ones."""
        self.assertEqual(m.frontmatter_sources('---\nsources: ["a", "b"]\n---\nx\n'),
                         ['a', 'b'])
        self.assertEqual(
            m.frontmatter_sources('---\nsources:\n  - "one"\n  - two\n---\nx\n'),
            ['one', 'two'])

    def test_sources_absent_empty_or_unparseable_yield_no_references(self):
        for text in ('---\nsources: []\n---\nx\n', '---\ntags: [a]\n---\nx\n', '# hi\n'):
            self.assertEqual(m.frontmatter_sources(text), [])
        self.assertEqual(m.references_html([]), '')

    def test_the_block_list_stops_at_the_next_key(self):
        text = '---\nsources:\n  - "one"\naliases: ["x"]\n---\nbody\n'
        self.assertEqual(m.frontmatter_sources(text), ['one'])

    def test_a_reference_links_its_url_and_keeps_the_note_beside_it(self):
        html = m.references_html(['https://example.com/p (fetched 2026-09-30)'])
        self.assertIn('<a href="https://example.com/p">', html)
        self.assertIn('fetched 2026-09-30', html)
        self.assertIn('<h2 id="references">References</h2>', html)

    def test_a_reference_that_is_not_a_url_still_renders(self):
        self.assertIn('<span class="ref-label">analytics</span>',
                      m.references_html(['analytics']))

    def test_an_entry_splits_into_what_where_and_how_it_was_read(self):
        label, loc, prov = m.split_reference(
            'https://example.com/pricing (Pro tier 15/mo — via search summary, 2026-09-30)')
        self.assertEqual(loc, 'https://example.com/pricing')
        self.assertIn('Pro tier', label)
        self.assertEqual(prov, 'via search summary, 2026-09-30')

    def test_text_after_the_date_stays_in_the_label(self):
        """An earlier cut let provenance swallow the rest of the entry."""
        label, _, prov = m.split_reference(
            'https://example.com/x (Spark vs Blaze, fetched 2026-09-30 — the tier table)')
        self.assertEqual(prov, 'fetched 2026-09-30')
        self.assertIn('Spark vs Blaze', label)
        self.assertIn('tier table', label)

    def test_an_entry_with_no_url_keeps_its_text(self):
        label, loc, _ = m.split_reference('Repo 2026-09-30: build.gradle.kts')
        self.assertEqual(loc, '')
        self.assertIn('build.gradle.kts', label)

    def test_the_cover_takes_the_title_and_the_summary_goes_behind_the_contents(self):
        """Page one is a title page. A reader should not meet the conclusion first,
        and a cover holding only an `<h1>` reads as a mistake rather than a cover."""
        import tempfile
        note = ('---\nauthor: "A Person"\naudience: ["mobile", "backend"]\n'
                'created: 2026-09-30\nupdated: 2026-10-01\nsources: []\n---\n'
                '# The Title\n\n> [!tip] The short version\n> The answer.\n\n'
                '## One\n\nText.\n')
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'n.md'
            path.write_text(note, encoding='utf-8')
            html, _, _ = m.build_html(path, with_mermaid=False)
        # the stylesheet is inlined in <head> and mentions `callout`, so scope to the body
        body = html.split('</style></head>', 1)[1]
        cover = body[body.index('<header class="cover">'):body.index('</header>')]
        self.assertIn('<h1', cover)
        self.assertIn('A Person', cover)
        self.assertIn('mobile, backend', cover)
        self.assertNotIn('callout', cover, 'the summary must not sit on the cover')
        self.assertLess(body.index('</header>'), body.index('callout'))
        self.assertLess(body.index('</header>'), body.index('nav class="toc"')
                        if 'nav class="toc"' in body else len(body))

    def test_a_note_without_those_frontmatter_fields_gets_no_meta_block(self):
        self.assertEqual(m.cover_html('---\ntags: [a]\n---\nbody\n'), '')

    def test_revised_is_omitted_when_it_equals_created(self):
        fm = '---\ncreated: 2026-09-30\nupdated: 2026-09-30\n---\nx\n'
        self.assertIn('Researched', m.cover_html(fm))
        self.assertNotIn('Revised', m.cover_html(fm))

    # A hand-built PDF, so the audit is testable without Chrome. Page objects are
    # deliberately numbered against reading order: object 3 is page one.
    MINI_PDF = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type /Pages /Kids [3 0 R 2 0 R] /Count 2>>endobj\n"
        b"2 0 obj<</Type /Page /Contents 5 0 R>>endobj\n"
        b"3 0 obj<</Type /Page /Contents 4 0 R>>endobj\n"
        b"4 0 obj<</Length 40>>stream\n"
        + b"BT (x) Tj ET " * 200 + b"\nendstream endobj\n"
        b"5 0 obj<</Length 0>>stream\n\nendstream endobj\n"
    )

    def _mini(self, body: bytes):
        import tempfile
        d = tempfile.mkdtemp()
        path = pathlib.Path(d) / 'mini.pdf'
        path.write_bytes(body)
        return path

    def test_the_blank_page_alarm_rides_on_the_summary_line(self):
        """A caller piping through `tail -1` sees the summary and nothing else.
        A warning printed only above it is a warning that gets run past."""
        source = (pathlib.Path(m.__file__)).read_text(encoding='utf-8')
        summary = source[source.index('print(f"  {page_count(out)}'):]
        self.assertIn('{alarm}', summary.split('\n')[1] + summary.split('\n')[0])

    def test_build_html_actually_runs_the_structural_audit(self):
        """`audit_structure` could be unwired from `build_html` with every test still
        green, because they all called it directly."""
        import tempfile
        note = '---\nsources: []\n---\n# T\n\n## A\n\nx\n\n#### Buried\n\ny\n'
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'n.md'
            path.write_text(note, encoding='utf-8')
            _, _, problems = m.build_html(path, with_mermaid=False)
        self.assertTrue(any('skips h2' in p for p in problems),
                        'build_html no longer runs audit_structure')

    def test_a_skipped_heading_level_is_reported(self):
        """Section 9's parts sat at `####` under a `##`, so the contents reduced the
        whole backend ask to a single line."""
        body = '<h2 id="a">A</h2><h4 id="b">Buried</h4>'
        self.assertTrue(any('skips h2' in p for p in m.audit_structure(body, [])))

    def test_consecutive_levels_are_fine(self):
        body = '<h2 id="a">A</h2><h3 id="b">B</h3><h2 id="c">C</h2>'
        self.assertEqual(m.audit_structure(body, []), [])

    def test_two_headings_with_the_same_text_are_reported(self):
        """They do NOT share an anchor — python-markdown emits `references` and
        `references_1`. The damage is that the contents rows read identically and a
        hand-written `#references` link silently reaches the first."""
        body = '<h2 id="references">References</h2><h2 id="references_1">References</h2>'
        found = m.audit_structure(body, [])
        self.assertTrue(any('cannot distinguish them' in p for p in found))
        self.assertFalse(any('duplicate heading id' in p for p in found),
                         'distinct ids must not be reported as duplicates')

    def test_the_contents_pointing_twice_at_one_anchor_is_reported(self):
        """The defect this audit was written after: References appeared twice in the
        contents, both resolving to the prose, and the citations were unreachable."""
        body = ('<h2 id="references">References</h2>'
                '<nav class="toc"><a href="#references">References</a>'
                '<a href="#references">References</a></nav>')
        self.assertTrue(any('lists "#references" 2 times' in p
                            for p in m.audit_structure(body, [])))

    def test_a_contents_entry_with_no_heading_is_reported(self):
        body = '<h2 id="a">A</h2><nav class="toc"><a href="#gone">X</a></nav>'
        self.assertTrue(any('matches no heading' in p for p in m.audit_structure(body, [])))

    def test_a_duplicate_id_is_reported(self):
        body = '<h2 id="references">One</h2><h2 id="references">Two</h2>'
        self.assertTrue(any('duplicate heading id' in p for p in m.audit_structure(body, [])))

    def test_the_audit_finds_a_page_with_no_glyphs(self):
        """A blank page is indistinguishable from a real one by page count alone,
        which is how one reached a document that had already been sent."""
        blank, _ = m.audit_pages(self._mini(self.MINI_PDF))
        self.assertEqual(blank, [2])

    def test_the_audit_numbers_pages_in_reading_order(self):
        """The fixture's object numbers run opposite to its `/Kids` order. Walking
        objects instead of the page tree names the wrong page."""
        blank, _ = m.audit_pages(self._mini(self.MINI_PDF))
        self.assertNotEqual(blank, [1], 'reported the content page as blank')

    def test_a_page_with_text_but_very_little_is_reported_separately(self):
        """Not a defect on its own — a cover page is legitimately light — so it is
        reported rather than failed, and `--strict` keys only on blank."""
        body = self.MINI_PDF.replace(
            b"5 0 obj<</Length 0>>stream\n\nendstream endobj",
            b"5 0 obj<</Length 40>>stream\n" + b"BT (y) Tj ET " * 10 + b"\nendstream endobj")
        blank, thin = m.audit_pages(self._mini(body))
        self.assertEqual(blank, [])
        self.assertEqual([n for n, _ in thin], [2])

    def test_a_document_with_text_on_every_page_is_clean(self):
        body = self.MINI_PDF.replace(
            b"5 0 obj<</Length 0>>stream\n\nendstream endobj",
            b"5 0 obj<</Length 40>>stream\n" + b"BT (y) Tj ET " * 200 + b"\nendstream endobj")
        blank, thin = m.audit_pages(self._mini(body))
        self.assertEqual(blank, [])
        self.assertEqual(thin, [])

    def test_the_page_audit_reads_pages_in_tree_order_not_object_order(self):
        """Page objects are not stored in page order. Numbering the objects reports
        the wrong page, which is how the first version of this check named page 24
        when the blank one was elsewhere."""
        self.assertIn('Kids', m.pdf_pages_in_order.__doc__ or '')
        self.assertIn('/Kids', m.pdf_pages_in_order.__doc__ or '')

    def test_the_audit_thresholds_are_named_not_inlined(self):
        self.assertLess(m.BLANK_GLYPH_OPS, m.THIN_GLYPH_OPS)

    def test_the_stylesheet_keeps_the_page_rules_that_cost_a_reprint(self):
        """Both were added after a layout defect reached a sent PDF.

        `.new-page` replaced empty `break-after` divs, one of which became a blank
        page; `h2#references` keeps the citations starting a page of their own.
        Neither is reachable from a unit test, so this guards them from deletion.
        """
        css = (pathlib.Path(m.__file__).parent / 'pdf.css').read_text(encoding='utf-8')
        self.assertRegex(css, r'\.new-page\s*\{[^}]*break-before:\s*page')
        self.assertRegex(css, r'h2#references\s*\{[^}]*break-before:\s*page')

    def test_every_sources_entry_in_the_vault_parses_readably(self):
        """Synthetic shapes passed while three real citations read as duplicated text.

        Four hand-written fixtures cannot cover a convention that 70-odd notes write
        by hand. This walks the whole vault instead, which is the only version of
        this test that would have caught `MMP pricing pricing decays` before it
        shipped in a PDF that was sent.
        """
        vault = vault_dir()
        if vault is None or not vault.exists():
            self.skipTest('no installed vault in this checkout')
        checked = 0
        for note in vault.rglob('*.md'):
            for entry in m.frontmatter_sources(note.read_text(encoding='utf-8')):
                checked += 1
                label, locator, _ = m.split_reference(entry)
                with self.subTest(note=note.name, entry=entry[:50]):
                    self.assertTrue(label or locator, 'renders as an empty citation')
                    self.assertNotIn('  ', label, 'fragments joined with a bare gap')
                    words = label.lower().split()
                    doubled = [a for a, b in zip(words, words[1:])
                               if a == b and len(a) > 3]
                    self.assertEqual(doubled, [], f'duplicated word: {label}')
        # Not a count of this vault's notes — a guard against the walk finding nothing
        # and reporting that as a pass. A vault too young to have cited anything skips.
        if not checked:
            self.skipTest('vault carries no `sources:` entries yet')

    def test_every_entry_renders_something(self):
        """A row with neither label nor locator would be a silently empty citation."""
        for entry in ('https://example.com', 'analytics', '[[a-note]]',
                      'https://e.com (x — fetched 2026-09-30)'):
            html = m.references_html([entry])
            self.assertTrue('ref-label' in html or 'ref-loc' in html, entry)

    def test_a_reference_cannot_inject_markup(self):
        self.assertNotIn('<script>', m.references_html(['<script>alert(1)</script>']))

    def test_a_contents_list_appears_only_once_a_note_is_long_enough(self):
        few = [{'level': 2, 'id': f's{i}', 'name': f'S{i}'} for i in range(3)]
        many = [{'level': 2, 'id': f's{i}', 'name': f'S{i}'} for i in range(m.TOC_MIN_HEADINGS)]
        self.assertEqual(m.toc_html(few), '')
        self.assertIn('nav class="toc"', m.toc_html(many))

    def test_h2s_nested_under_an_h1_are_still_found(self):
        """`toc_tokens` is a tree. A flat scan finds nothing whenever the note has a title."""
        tree = [{'level': 1, 'id': 't', 'name': 'Title', 'children': [
            {'level': 2, 'id': f's{i}', 'name': f'S{i}', 'children': []}
            for i in range(m.TOC_MIN_HEADINGS)]}]
        self.assertEqual(len(m.flatten_toc(tree)), m.TOC_MIN_HEADINGS + 1)
        self.assertIn('S0', m.toc_html(tree))

    def test_a_body_references_heading_does_not_produce_a_second_one(self):
        """The template no longer scaffolds one, but a hand-written note might.

        Two `<h2 id="references">` means the contents anchor resolves to whichever
        came first — the prose, not the citations. Caught twice in review.
        """
        import tempfile
        # Above TOC_MIN_HEADINGS on purpose: with a one-heading fixture `toc_html`
        # returns '' and the contents half of this defect goes unmeasured, which is
        # how the first version of the fix shipped listing References twice.
        note = ('---\nsources: ["https://example.com/x"]\n---\n# T\n\n'
                + ''.join(f'## S{i}\n\ntext\n\n' for i in range(m.TOC_MIN_HEADINGS))
                + '## References\n\nSee the appendix.\n')
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'n.md'
            path.write_text(note, encoding='utf-8')
            html, _, _ = m.build_html(path, with_mermaid=False)
        self.assertEqual(html.count('id="references"'), 1)
        self.assertIn('Cited sources', html)
        # and the contents lists References once, not twice
        nav = html.split('</nav>')[0]
        self.assertEqual(nav.count('href="#references"'), 1)

    def test_the_generated_references_appear_in_the_contents(self):
        """The appendix is appended after the contents is built, so it is invisible to
        `toc_tokens` — without this the citations are the one section a reader cannot
        navigate to, and the anchor lands on whatever else is called References."""
        tokens = [{'level': 2, 'id': f's{i}', 'name': f'S{i}'} for i in range(m.TOC_MIN_HEADINGS)]
        self.assertNotIn('#references', m.toc_html(tokens))
        self.assertIn('<a href="#references">References</a>',
                      m.toc_html(tokens, with_references=True))

    def test_subheadings_are_listed_nested_under_their_section(self):
        """A reader navigating a 30-page note needs the sub-sections, not just the
        chapters — but nested, so the two levels stay distinguishable."""
        tokens = [{'level': 2, 'id': f's{i}', 'name': f'S{i}', 'children': []}
                  for i in range(m.TOC_MIN_HEADINGS)]
        tokens[0]['children'] = [{'level': 3, 'id': 'sub', 'name': 'A subsection'}]
        out = m.toc_html(tokens)
        self.assertIn('toc-sub', out)
        self.assertIn('A subsection', out)

    def test_a_stray_subheading_outside_any_section_is_not_listed(self):
        tokens = [{'level': 2, 'id': f's{i}', 'name': f'S{i}'} for i in range(m.TOC_MIN_HEADINGS)]
        tokens.append({'level': 3, 'id': 'deep', 'name': 'Too deep'})
        self.assertNotIn('Too deep', m.toc_html(tokens))

    def test_the_contents_is_unordered_because_the_headings_carry_numbers(self):
        """An <ol> rendered its own numbers on top of "0. How to read this",
        so the first entry read "1. 0. How to read this"."""
        tokens = [{'level': 2, 'id': f's{i}', 'name': f'{i}. S{i}'}
                  for i in range(m.TOC_MIN_HEADINGS)]
        out = m.toc_html(tokens)
        self.assertNotIn('<ol', out)
        self.assertIn('<ul', out)

    def test_the_contents_list_lands_after_the_title_not_before_it(self):
        out = m.insert_toc('<h1>T</h1><p>body</p>', '<nav class="toc"></nav>')
        self.assertTrue(out.startswith('<h1>T</h1><nav'))

    def test_a_note_with_no_h1_still_gets_its_contents_list(self):
        out = m.insert_toc('<p>body</p>', '<nav class="toc"></nav>')
        self.assertTrue(out.startswith('<nav'))

    def test_note_without_frontmatter_is_untouched(self):
        src = "# Heading\n\nno frontmatter here\n"
        self.assertEqual(m.strip_frontmatter(src), (src, None))

    def test_a_later_horizontal_rule_is_not_mistaken_for_frontmatter(self):
        src = "# H\n\ntext\n\n---\n\nmore\n"
        body, _ = m.strip_frontmatter(src)
        self.assertEqual(body, src)

    def test_multiline_frontmatter_with_nested_lists(self):
        body, _ = m.strip_frontmatter("---\nrelated:\n  - \"[[a]]\"\n  - \"[[b]]\"\n---\nX\n")
        self.assertEqual(body, "X\n")


class TestWikilinks(unittest.TestCase):
    def test_alias_form_keeps_only_the_alias(self):
        self.assertEqual(m.convert_wikilinks("see [[some_note|the note]] now"),
                         "see the note now")

    def test_plain_form_keeps_the_target_text(self):
        self.assertEqual(m.convert_wikilinks("see [[mobile_ops]]"), "see mobile_ops")

    def test_several_on_one_line(self):
        self.assertEqual(m.convert_wikilinks("[[a]] and [[b|B]] and [[c]]"),
                         "a and B and c")

    def test_ordinary_markdown_links_are_untouched(self):
        src = "a [link](https://example.com) and `[[code]]`"
        self.assertEqual(m.convert_wikilinks(src),
                         "a [link](https://example.com) and `code`")

    def test_no_brackets_survive_a_realistic_line(self):
        out = m.convert_wikilinks("carried in [[tracelet_migration]] / [[mobile_ops|ops]]")
        self.assertNotIn("[[", out)
        self.assertNotIn("]]", out)


@unittest.skipUnless(HAS_MARKDOWN, "python-markdown not installed")
class TestCallouts(unittest.TestCase):
    def test_kind_and_title_become_a_styled_box(self):
        out = m.convert_callouts("> [!warning] Window bases differ\n> the body line\n")
        self.assertIn('class="callout callout-warning"', out)
        self.assertIn("Window bases differ", out)
        self.assertIn("the body line", out)

    def test_missing_title_falls_back_to_the_kind(self):
        out = m.convert_callouts("> [!note]\n> body\n")
        self.assertIn("Note", out)

    def test_accepts_obsidian_spacing_and_fold_markers(self):
        for src in ("> [!tip] T\n> b\n", ">[!tip] T\n>b\n", "> [!tip]- T\n> b\n",
                    "> [!tip]+ T\n> b\n"):
            with self.subTest(src=src):
                self.assertIn("callout-tip", m.convert_callouts(src))

    def test_kind_is_lowercased_for_the_class(self):
        self.assertIn("callout-warning", m.convert_callouts("> [!WARNING] t\n> b\n"))

    def test_plain_blockquote_is_left_alone(self):
        src = "> just a quotation\n> second line\n"
        self.assertEqual(m.convert_callouts(src), src)

    def test_body_markdown_is_rendered(self):
        out = m.convert_callouts("> [!note] T\n> has **bold** text\n")
        self.assertIn("<strong>bold</strong>", out)

    def test_title_is_html_escaped(self):
        out = m.convert_callouts("> [!note] a <script> & b\n> body\n")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)


class TestMermaidExtraction(unittest.TestCase):
    def test_fence_is_replaced_by_a_placeholder_and_captured(self):
        text, blocks = m.extract_mermaid("a\n\n```mermaid\ngraph TD\nA-->B\n```\n\nb\n")
        self.assertEqual(len(blocks), 1)
        self.assertIn("graph TD", blocks[0])
        self.assertIn("@@MERMAID0@@", text)
        self.assertNotIn("```mermaid", text)

    def test_several_diagrams_are_numbered_in_order(self):
        text, blocks = m.extract_mermaid(
            "```mermaid\nfirst\n```\ntext\n```mermaid\nsecond\n```\n")
        self.assertEqual(len(blocks), 2)
        self.assertIn("first", blocks[0])
        self.assertIn("second", blocks[1])
        self.assertIn("@@MERMAID0@@", text)
        self.assertIn("@@MERMAID1@@", text)

    def test_other_code_fences_are_not_touched(self):
        src = "```python\nprint(1)\n```\n"
        text, blocks = m.extract_mermaid(src)
        self.assertEqual(blocks, [])
        self.assertEqual(text, src)

    def test_note_without_diagrams(self):
        self.assertEqual(m.extract_mermaid("no diagrams\n"), ("no diagrams\n", []))


class TestPageCount(unittest.TestCase):
    def test_counts_pages_and_excludes_the_pages_node(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "x.pdf"
            p.write_bytes(pdf_bytes(7))
            self.assertEqual(m.page_count(p), 7)

    def test_handles_the_unspaced_variant(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "x.pdf"
            p.write_bytes(b"%PDF\n<</Type/Pages>>" + b"<</Type/Page>>" * 3)
            self.assertEqual(m.page_count(p), 3)

    def test_unparseable_file_reports_zero_rather_than_raising(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "x.pdf"
            p.write_bytes(b"not a pdf")
            self.assertEqual(m.page_count(p), 0)


class TestChromeDiscovery(unittest.TestCase):
    def test_returns_the_first_candidate_that_exists(self):
        with tempfile.TemporaryDirectory() as d:
            real = pathlib.Path(d) / "chrome"
            real.write_text("#!/bin/sh\n")
            with mock.patch.object(m, "CHROME_CANDIDATES", ["/nope/missing", str(real)]):
                self.assertEqual(m.find_chrome(), str(real))

    def test_exits_with_a_message_when_no_browser_is_installed(self):
        with mock.patch.object(m, "CHROME_CANDIDATES", ["/nope/missing"]):
            with self.assertRaises(SystemExit) as cm:
                m.find_chrome()
            self.assertIn("Chrome", str(cm.exception))


class TestMermaidBundle(unittest.TestCase):
    """The fetch is the one impure path; it must cache, and must fail soft."""

    def test_cached_file_is_used_without_touching_the_network(self):
        with tempfile.TemporaryDirectory() as d:
            cache = pathlib.Path(d) / "m.js"
            cache.write_text("CACHED", encoding="utf-8")
            with mock.patch.object(m, "MERMAID_CACHE", cache), \
                 mock.patch("urllib.request.urlopen",
                            side_effect=AssertionError("network must not be used")):
                self.assertEqual(m.mermaid_js(), "CACHED")

    def test_offline_returns_none_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as d:
            cache = pathlib.Path(d) / "absent.js"
            with mock.patch.object(m, "MERMAID_CACHE", cache), \
                 mock.patch("urllib.request.urlopen", side_effect=OSError("offline")), \
                 contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertIsNone(m.mermaid_js())
            self.assertIn("mermaid unavailable", err.getvalue())
            self.assertFalse(cache.exists())


@unittest.skipUnless(HAS_MARKDOWN, "python-markdown not installed")
class TestBuildHtml(unittest.TestCase):
    """End to end over the text pipeline — still no Chrome and no network."""

    NOTE = (
        "---\n"
        "tags: [sprint]\n"
        "related:\n  - \"[[mobile_ops]]\"\n"
        "---\n\n"
        "# Sprint note\n\n"
        "Carried in [[tracelet_migration]] and [[mobile_ops|ops]].\n\n"
        "> [!warning] Mind this\n> a caveat\n\n"
        "<div style=\"break-after: page;\"></div>\n\n"
        "## Reliability\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "```mermaid\ngraph TD\nA-->B\n```\n"
    )

    def _build(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "note.md"
            p.write_text(self.NOTE, encoding="utf-8")
            html, diagrams, _structure = m.build_html(p, **kw)
            return html, diagrams

    def test_no_network_when_diagrams_are_disabled(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=AssertionError("network must not be used")):
            html, n = self._build(with_mermaid=False)
        self.assertEqual(n, 1)
        self.assertIn("mermaid-unrendered", html)

    def test_frontmatter_never_reaches_the_page(self):
        html, _ = self._build(with_mermaid=False)
        body = html.split("<body>", 1)[1]
        self.assertNotIn("tags: [sprint]", body)

    def test_wikilinks_are_flattened_in_the_body(self):
        html, _ = self._build(with_mermaid=False)
        body = html.split("<body>", 1)[1]
        self.assertNotIn("[[", body)
        self.assertIn("tracelet_migration", body)
        self.assertIn("ops", body)

    def test_callout_and_table_survive_as_elements(self):
        html, _ = self._build(with_mermaid=False)
        self.assertIn('class="callout callout-warning"', html)
        self.assertIn("<table>", html)

    def test_author_page_break_is_preserved(self):
        html, _ = self._build(with_mermaid=False)
        self.assertIn("break-after: page", html.split("<body>", 1)[1])

    def test_stylesheet_is_inlined_so_the_pdf_is_self_contained(self):
        html, _ = self._build(with_mermaid=False)
        self.assertIn("--pdf-heading-reserve", html)
        self.assertNotIn("<link", html)

    def test_diagram_becomes_a_mermaid_block_when_the_bundle_is_available(self):
        with mock.patch.object(m, "mermaid_js", return_value="/* bundle */"):
            html, n = self._build(with_mermaid=True)
        self.assertEqual(n, 1)
        self.assertIn('<pre class="mermaid">', html)
        self.assertIn("mermaid.initialize", html)
        self.assertNotIn("mermaid-unrendered", html.split("<body>", 1)[1])

    def test_diagram_degrades_to_visible_source_when_the_bundle_is_missing(self):
        with mock.patch.object(m, "mermaid_js", return_value=None):
            html, _ = self._build(with_mermaid=True)
        body = html.split("<body>", 1)[1]
        self.assertIn("mermaid-unrendered", body)
        self.assertIn("graph TD", body)
        self.assertNotIn("mermaid.initialize", body)

    def test_title_falls_back_to_the_filename(self):
        html, _ = self._build(with_mermaid=False)
        self.assertIn("<title>note</title>", html)


if __name__ == "__main__":
    unittest.main()
