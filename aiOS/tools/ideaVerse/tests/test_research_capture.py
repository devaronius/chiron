"""research-capture's per-note gate: the [DOC-KIND] rule and the folder vocabulary.

`check` is what the Stop hook runs on every touched note, so the kind rule has to live
here as well as in vault-lint — otherwise filing a note into atlas/documents/ without a
kind would pass the turn and only surface on the next full lint.
"""
from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

_PATH = pathlib.Path(__file__).resolve().parent.parent / 'research-capture.py'
_spec = importlib.util.spec_from_file_location('research_capture', _PATH)
capture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capture)

BODY = 'A body long enough to pass the empty-note check, and then some more.\n'


class TestCheckDocumentKind(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self._dir.name) / 'ideaVerse'
        self.addCleanup(self._dir.cleanup)
        patcher = mock.patch.object(capture.V, 'IDEAVERSE_DIR', self.vault)
        patcher.start()
        self.addCleanup(patcher.stop)
        known = mock.patch.object(capture.V, 'resolvable_basenames', return_value=set())
        known.start()
        self.addCleanup(known.stop)

    def write(self, relative: str, extra: str = '') -> pathlib.Path:
        path = self.vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'---\nup: []\nrelated: []\ncreated: 2026-09-29\n{extra}---\n\n{BODY}')
        return path

    def kind_issues(self, path: pathlib.Path) -> list:
        return [i for i in capture.check_note_ready(path) if i.startswith('[DOC-KIND]')]

    def test_a_document_without_a_kind_is_not_ready(self):
        self.assertEqual(len(self.kind_issues(self.write('atlas/documents/corax.md'))), 1)

    def test_a_document_with_an_allowed_kind_is_ready(self):
        path = self.write('atlas/documents/corax.md', 'kind: external\n')
        self.assertEqual(capture.check_note_ready(path), [])

    def test_a_kind_outside_the_list_is_not_ready(self):
        path = self.write('atlas/documents/a.md', 'kind: guide\n')
        self.assertIn('`kind: guide` is not allowed', self.kind_issues(path)[0])

    def test_other_folders_need_no_kind(self):
        self.assertEqual(self.kind_issues(self.write('atlas/config/a.md')), [])
        self.assertEqual(self.kind_issues(self.write('+/b.md')), [])

    def concept_issues(self, path: pathlib.Path) -> list:
        return [i for i in capture.check_note_ready(path) if i.startswith('[CONCEPT-KIND]')]

    def test_a_concept_without_a_kind_is_not_ready(self):
        self.assertEqual(len(self.concept_issues(self.write('atlas/concepts/stop.md'))), 1)

    def test_a_concept_with_a_kind_is_ready(self):
        path = self.write('atlas/concepts/stop.md', 'kind: domain\n')
        self.assertEqual(capture.check_note_ready(path), [])

    def test_open_item_needs_no_kind(self):
        self.assertEqual(self.concept_issues(self.write('atlas/concepts/open_item.md')), [])


class TestSuggestVocabulary(unittest.TestCase):
    """The generic words that used to route design notes into documents/."""

    def best(self, text: str) -> str:
        return next(iter(capture.suggest_location(text)))

    def test_architecture_and_structure_point_at_concepts(self):
        self.assertEqual(self.best('the offline architecture and its structure'),
                         'atlas/concepts')

    def test_an_external_vendor_points_at_documents(self):
        self.assertEqual(self.best('an external system from a third party vendor'),
                         'atlas/documents')

    def test_a_dated_upgrade_check_points_at_research(self):
        self.assertEqual(
            self.best('does bumping flutter force an upgrade? bottom line: nothing changes'),
            'calendar/research')

    def test_generic_guide_words_no_longer_score_documents(self):
        scores = capture.suggest_location('a guide to the build setup')
        self.assertNotIn('atlas/documents', scores)


if __name__ == '__main__':
    unittest.main()
