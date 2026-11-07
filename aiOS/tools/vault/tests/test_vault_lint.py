"""vault-lint's folder rules: [INBOX-LINK] (filed notes must not depend on `+/` inbox
notes) and [DOC-KIND] (atlas/documents/ notes must declare one of four kinds).

Notes are built as plain dicts in the shape `vault_lib.load_notes` returns, so nothing
here reads the real vault — the check is a pure function over the note list.
"""
from __future__ import annotations

import datetime
import importlib.util
import pathlib
import unittest
from unittest import mock

_PATH = pathlib.Path(__file__).resolve().parent.parent / 'vault-lint.py'
_spec = importlib.util.spec_from_file_location('vault_lint', _PATH)
lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lint)


def note(path: str, body: str = '', up=(), related=(), **frontmatter) -> dict:
    return {
        'path': path,
        'basename': pathlib.PurePosixPath(path).stem,
        'frontmatter': {'up': list(up), 'related': list(related), **frontmatter},
        'body': body,
    }


class TestInboxLinks(unittest.TestCase):
    def test_a_filed_note_linking_an_inbox_note_is_flagged(self):
        issues = lint.check_inbox_links([
            note('+/corax.md'),
            note('atlas/concepts/geofencing.md', body='See [[corax]].'),
        ])
        self.assertEqual(len(issues), 1)
        self.assertIn('[INBOX-LINK] [[corax]]', issues[0])
        self.assertIn('+/corax.md', issues[0])
        self.assertIn('atlas/concepts/geofencing.md', issues[0])

    def test_frontmatter_links_count(self):
        issues = lint.check_inbox_links([
            note('+/nail.md'),
            note('atlas/config/config.md', related=['[[nail]]']),
        ])
        self.assertEqual(len(issues), 1)

    def test_aliased_heading_and_path_style_links_resolve_to_the_inbox_note(self):
        issues = lint.check_inbox_links([
            note('+/nail.md'),
            note('atlas/concepts/a.md', body='[[nail|NAIL]] [[nail#Setup]] [[+/nail]]'),
        ])
        self.assertEqual(len(issues), 1)
        self.assertIn('1 filed note(s)', issues[0])

    def test_one_line_per_inbox_note_however_many_link_it(self):
        issues = lint.check_inbox_links([
            note('+/corax.md'),
            note('atlas/concepts/a.md', body='[[corax]]'),
            note('atlas/concepts/b.md', body='[[corax]]'),
        ])
        self.assertEqual(len(issues), 1)
        self.assertIn('2 filed note(s)', issues[0])

    def test_inbox_notes_linking_each_other_are_not_flagged(self):
        # Both are unfiled; the link moves with them when they are processed.
        self.assertEqual(lint.check_inbox_links([
            note('+/a.md', body='[[b]]'),
            note('+/b.md'),
        ]), [])

    def test_links_to_filed_notes_are_not_its_concern(self):
        self.assertEqual(lint.check_inbox_links([
            note('atlas/documents/failure_codes.md'),
            note('atlas/concepts/a.md', body='[[failure_codes]]'),
        ]), [])

    def test_it_is_part_of_the_default_run(self):
        issues = lint.run_checks([
            note('+/corax.md', body='x' * 100),
            note('atlas/concepts/a.md', body='[[corax]] ' + 'x' * 100),
        ], with_wiki=False)
        self.assertTrue(any(i.startswith('[INBOX-LINK]') for i in issues))



class TestDocumentKinds(unittest.TestCase):
    def test_each_allowed_kind_passes(self):
        for kind in ('external', 'process', 'stakeholder-reference', 'backend-request'):
            with self.subTest(kind=kind):
                self.assertEqual(lint.check_note_kinds(
                    [note('atlas/documents/a.md', kind=kind)]), [])

    def test_a_document_without_a_kind_is_flagged(self):
        issues = lint.check_note_kinds([note('atlas/documents/corax.md')])
        self.assertEqual(len(issues), 1)
        self.assertIn('[DOC-KIND] atlas/documents/corax.md', issues[0])
        self.assertIn('missing `kind:`', issues[0])

    def test_a_kind_outside_the_list_is_flagged(self):
        issues = lint.check_note_kinds(
            [note('atlas/documents/a.md', kind='architecture')])
        self.assertEqual(len(issues), 1)
        self.assertIn('`kind: architecture` is not allowed', issues[0])

    def test_notes_outside_kinded_folders_need_no_kind(self):
        self.assertEqual(lint.check_note_kinds([
            note('atlas/config/a.md'),
            note('+/b.md'),
            note('atlas/documents_old/c.md'),
        ]), [])

    def test_it_is_part_of_the_default_run(self):
        issues = lint.run_checks(
            [note('atlas/documents/a.md', body='x' * 100)], with_wiki=False)
        self.assertTrue(any(i.startswith('[DOC-KIND]') for i in issues))



class TestConceptKinds(unittest.TestCase):
    def test_domain_and_behaviour_pass(self):
        for kind in ('domain', 'behaviour'):
            with self.subTest(kind=kind):
                self.assertEqual(lint.check_note_kinds(
                    [note('atlas/concepts/stop.md', kind=kind)]), [])

    def test_a_concept_without_a_kind_is_flagged_with_its_own_tag(self):
        issues = lint.check_note_kinds([note('atlas/concepts/stop.md')])
        self.assertEqual(len(issues), 1)
        self.assertTrue(issues[0].startswith('[CONCEPT-KIND] atlas/concepts/stop.md'))

    def test_a_document_kind_is_not_a_concept_kind(self):
        issues = lint.check_note_kinds([note('atlas/concepts/a.md', kind='process')])
        self.assertIn('`kind: process` is not allowed in atlas/concepts/', issues[0])

    def test_nested_concept_folders_are_covered(self):
        issues = lint.check_note_kinds([note('atlas/concepts/guest_drivers/a.md')])
        self.assertEqual(len(issues), 1)

    def test_open_item_is_exempt_as_a_framework_root_note(self):
        self.assertEqual(lint.check_note_kinds([note('atlas/concepts/open_item.md')]), [])



class TestRetireDue(unittest.TestCase):
    """Shipped efforts are reported for a stub once they pass the workday window."""

    MONDAY = datetime.date(2026, 9, 28)

    def due(self, **frontmatter) -> list:
        return lint.check_retire_due(
            [note('efforts/works/x.md', **frontmatter)], today=self.MONDAY)

    def test_workdays_skip_weekends(self):
        friday = datetime.date(2026, 9, 25)
        self.assertEqual(lint.workdays_between(friday, self.MONDAY), 1)
        self.assertEqual(lint.workdays_between(self.MONDAY, self.MONDAY), 0)

    def test_due_at_exactly_the_threshold(self):
        # 14 workdays before Monday 2026-09-28 is Wednesday 2026-09-08.
        issues = self.due(status='shipped', shipped='2026-09-08')
        self.assertEqual(len(issues), 1)
        self.assertIn('14 workdays ago', issues[0])
        self.assertTrue(issues[0].startswith('[INFO] RETIRE efforts/works/x.md'))

    def test_not_due_one_workday_earlier(self):
        self.assertEqual(self.due(status='shipped', shipped='2026-09-09'), [])

    def test_a_stubbed_note_is_never_reported(self):
        self.assertEqual(self.due(status='shipped', shipped='2026-01-01', stub='abc1234'), [])

    def test_active_efforts_are_not_its_concern(self):
        self.assertEqual(self.due(status='active', shipped='2026-01-01'), [])

    def test_a_shipped_note_without_a_date_asks_for_one(self):
        issues = self.due(status='shipped')
        self.assertIn('`shipped:` is missing', issues[0])

    def test_notes_outside_efforts_works_are_ignored(self):
        self.assertEqual(lint.check_retire_due(
            [note('atlas/concepts/x.md', status='shipped', shipped='2026-01-01')],
            today=self.MONDAY), [])

    def test_the_window_comes_from_config(self):
        with mock.patch.dict(lint.V.CONFIG, {'efforts': {'stubAfterWorkdays': 1}}):
            self.assertEqual(len(self.due(status='shipped', shipped='2026-09-25')), 1)

    def test_it_is_informational_not_blocking(self):
        issues = self.due(status='shipped', shipped='2026-01-01')
        self.assertTrue(all(i.startswith('[INFO]') for i in issues))


if __name__ == '__main__':
    unittest.main()
