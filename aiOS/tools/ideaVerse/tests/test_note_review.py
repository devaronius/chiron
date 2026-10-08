"""note-review's research-note structure check.

A research note is the kind most likely to be read by someone who cannot ask the
author anything, and **Method** and **Limitations** are the two sections reliably
forgotten — a note reads finished without them. This check makes their absence
visible; whether they are honest stays a human review.

Notes are plain dicts in the shape `review_note` builds, so nothing here touches the
real vault.
"""
from __future__ import annotations

import importlib.util
import pathlib
import unittest

_PATH = pathlib.Path(__file__).resolve().parent.parent / 'note-review.py'
_spec = importlib.util.spec_from_file_location('note_review', _PATH)
nr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nr)

LONG = 'x' * (nr.MIN_BODY_CHARS + 50)


def note(path: str, body: str) -> dict:
    return {'path': path, 'basename': pathlib.PurePosixPath(path).stem,
            'frontmatter': {}, 'body': body}


class TestResearchStructure(unittest.TestCase):
    def messages(self, path: str, body: str) -> str:
        return ' '.join(i['message'] for i in nr.check_research_structure(note(path, body)))

    def test_a_research_note_with_both_sections_passes(self):
        body = f'## Method\n{LONG}\n## Limitations\nnone known\n'
        self.assertEqual(nr.check_research_structure(note('calendar/research/x.md', body)), [])

    def test_a_missing_section_is_named_rather_than_reported_generically(self):
        body = f'## Method\n{LONG}\n'
        self.assertIn('Limitations', self.messages('calendar/research/x.md', body))
        body = f'## Limitations\n{LONG}\n'
        self.assertIn('Method', self.messages('calendar/research/x.md', body))

    def test_both_missing_reports_one_finding_naming_both(self):
        issues = nr.check_research_structure(note('calendar/research/x.md', LONG))
        self.assertEqual(len(issues), 1)
        self.assertIn('Method', issues[0]['message'])
        self.assertIn('Limitations', issues[0]['message'])

    def test_it_points_at_the_template_rather_than_just_complaining(self):
        self.assertIn('research.template.md', self.messages('calendar/research/x.md', LONG))

    def test_only_research_notes_are_checked(self):
        for path in ('atlas/concepts/x.md', 'efforts/works/x.md', 'calendar/days/2026-09-30.md'):
            self.assertEqual(nr.check_research_structure(note(path, LONG)), [])

    def test_a_stub_is_left_alone_because_content_quality_already_flags_it(self):
        """Two findings on the same empty note is noise, not signal."""
        self.assertEqual(nr.check_research_structure(note('calendar/research/x.md', 'tiny')), [])

    def test_the_heading_is_matched_at_any_depth_and_any_case(self):
        for heading in ('## Method', '### method', '## 0. How — Method',
                        '## Method and evidence'):
            body = f'{heading}\n{LONG}\n## Limitations\nx\n'
            self.assertEqual(
                nr.check_research_structure(note('calendar/research/x.md', body)), [])

    def test_limitations_matches_the_singular_too(self):
        body = f'## Method\n{LONG}\n## Limitation\nx\n'
        self.assertEqual(nr.check_research_structure(note('calendar/research/x.md', body)), [])

    def test_the_word_in_prose_does_not_satisfy_the_check(self):
        """It must be a heading — a passing mention is not a section."""
        body = f'{LONG}\nWe discuss our method and its limitations in passing.\n'
        self.assertIn('Method', self.messages('calendar/research/x.md', body))


class TestWiredIntoReviewNote(unittest.TestCase):
    """Every other test calls the check directly, so deleting the one line that
    wires it into `review_note` left the suite green. That is how a check gets
    silently disconnected."""

    def review(self, body: str, audience=None) -> list[str]:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            # `.resolve()` on macOS turns /tmp into /private/tmp, and `review_note`
            # resolves before computing the vault-relative path — so the fixture root
            # must be resolved too or the note lands outside the vault and is skipped.
            d = str(pathlib.Path(d).resolve())
            research = pathlib.Path(d) / 'docs' / 'ideaVerse' / 'calendar' / 'research'
            research.mkdir(parents=True)
            # `known_personas()` reads the vault being reviewed, which this fixture
            # redirects — without one here the persona check cannot fire at all.
            personas = pathlib.Path(d) / 'docs' / 'ideaVerse' / 'atlas' / 'personas'
            personas.mkdir(parents=True)
            (personas / 'guest-driver.md').write_text('# p\n', encoding='utf-8')
            note_path = research / 'x.md'
            aud = f'audience: {audience}\n' if audience else ''
            note_path.write_text(
                '---\nup: []\nrelated: []\ncreated: 2026-09-30\n' + aud + '---\n' + body,
                encoding='utf-8')
            original = nr.V.IDEAVERSE_DIR
            try:
                nr.V.IDEAVERSE_DIR = pathlib.Path(d) / 'docs' / 'ideaVerse'
                return [i['message'] for i in nr.review_note(note_path)['issues']]
            finally:
                nr.V.IDEAVERSE_DIR = original

    def test_review_note_runs_every_check_that_was_added(self):
        """Each of these could be unwired from `review_note` with the suite staying
        green — the tests called them directly. This holds their attachment."""
        body = ('# X\n\n' + LONG + '\n\nA previous revision was wrong. The '
                'guest-driver matters here.\n\n- [ ] a task\n')
        messages = ' '.join(self.review(body, audience=['mobile', 'backend']))
        self.assertIn('Method', messages, 'check_research_structure is unwired')
        self.assertIn('persona note', messages, 'check_persona_sources is unwired')
        self.assertIn('narrating', messages.replace('Reads as', 'narrating')
                      if 'Reads as' in messages else messages,
                      'check_process_voice is unwired')

    def test_review_note_actually_runs_the_research_check(self):
        self.assertTrue(any('Method' in m for m in self.review(f'# X\n\n{LONG}\n')))

    def test_a_note_carrying_both_sections_raises_no_research_finding(self):
        body = f'# X\n\n## Method\n{LONG}\n\n## Limitations\nnone\n'
        self.assertFalse(any('Research note has no' in m for m in self.review(body)))


class TestHousePhrasing(unittest.TestCase):
    """"What I could not determine" is what the researcher runbook tells agents to
    write, and two real notes use it. Flagging those would teach renaming, not writing."""

    def test_what_i_could_not_determine_satisfies_limitations(self):
        body = f'## Method\n{LONG}\n## What I could not determine\nnothing\n'
        self.assertEqual(nr.check_research_structure(note('calendar/research/x.md', body)), [])

    def test_other_accepted_spellings(self):
        for limits in ('## Caveats', '## Limitations', '## Unknowns', '## Threats to validity',
                       "## What we could not determine"):
            body = f'## Method\n{LONG}\n{limits}\nx\n'
            self.assertEqual(
                nr.check_research_structure(note('calendar/research/x.md', body)), [],
                f'{limits} should satisfy the Limitations check')

    def test_method_alternatives(self):
        for method in ('## Method', '## Methodology', '## How I checked', '## Evidence',
                       '## Approach'):
            body = f'{method}\n{LONG}\n## Limitations\nx\n'
            self.assertEqual(
                nr.check_research_structure(note('calendar/research/x.md', body)), [],
                f'{method} should satisfy the Method check')


class TestProcessVoice(unittest.TestCase):
    """A deliverable should not contain the record of its own making. Four kinds of
    that reached one research note before a human objected to each in turn."""

    def voice(self, body: str, audience) -> list[str]:
        n = note('calendar/research/x.md', body)
        n['frontmatter']['audience'] = audience
        return [i['message'] for i in nr.check_process_voice(n)]

    def test_each_kind_is_caught(self):
        for body in ('A previous revision called this wrong.',
                     '> [!note] Decision 2026-10-01 — out of scope',
                     'Pass 1 recommended Firebase Hosting.',
                     '- [ ] do the thing',
                     'This was superseded by the constraint.',
                     'Corrected on a second look.'):
            with self.subTest(body=body):
                self.assertTrue(self.voice(body, ['mobile', 'backend']), body)

    def test_an_internal_note_is_left_alone(self):
        """A working note *should* record its own history; only a deliverable should not."""
        self.assertEqual(self.voice('A previous revision was wrong.', ['mobile']), [])
        self.assertEqual(self.voice('A previous revision was wrong.', []), [])

    def test_ordinary_prose_does_not_trip_it(self):
        self.assertEqual(
            self.voice('The driver taps a link. Android passes the referrer through.',
                       ['mobile', 'backend', 'product']), [])

    def test_the_message_names_which_kind(self):
        msg = self.voice('- [ ] a task', ['mobile', 'product'])[0]
        self.assertIn('task list', msg)


class TestPersonaSources(unittest.TestCase):
    """Every pass done from the persona's own note changed a design decision; every
    pass done from a summary trusted the summary."""

    def check(self, body: str, sources) -> list[str]:
        n = note('calendar/research/x.md', body)
        n['frontmatter']['sources'] = sources
        return [i['message'] for i in nr.check_persona_sources(n)]

    def test_naming_a_persona_without_citing_it_is_flagged(self):
        if not nr.known_personas():
            self.skipTest('no personas in this checkout')
        name = sorted(nr.known_personas())[0]
        self.assertTrue(self.check(f'The {name} persona matters here.', []))

    def test_citing_the_persona_note_satisfies_it(self):
        if not nr.known_personas():
            self.skipTest('no personas in this checkout')
        name = sorted(nr.known_personas())[0]
        self.assertEqual(
            self.check(f'The {name} persona matters here.',
                       [f'atlas/personas/{name}.md']), [])

    def test_a_note_naming_no_persona_is_not_flagged(self):
        self.assertEqual(self.check('No personas are discussed here.', []), [])

    def test_a_document_that_merely_looks_persona_shaped_is_not_one(self):
        """`driver-device-fleet` is a measurement note. Matching by shape flagged it."""
        self.assertNotIn('driver-device-fleet', ' '.join(nr.known_personas()))


if __name__ == '__main__':
    unittest.main()
