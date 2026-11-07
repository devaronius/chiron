"""open-items' lane routing and note ownership.

**Lane routing** — which lane an item falls into, when it is ripe, and the one
ordering rule every view sorts by. The routing table is the whole point of
`assignee::`: it decides what an unattended queue may pick up and what the
session-start hook puts in front of a human. Two rules carry the risk and are pinned
directly — absence must never resolve to `agent`, and `blocked` must outrank the lane
whoever the item is assigned to.

**Ownership** — which note is treated as an item's owner. A time-boxed calendar note
(a day, briefing, meeting or sprint) mentions items that belong somewhere else, so the
ledger shows it unlinked and lets any other note win the same description. A research
note is not that: it is the durable origin of the items raised in it, and nothing else
carries them until they are distilled. That split was wrong once, which left the two
items raised by the deep-linking research note with no clickable owner.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import unittest
from unittest import mock

_PATH = pathlib.Path(__file__).resolve().parent.parent / 'open-items.py'
_spec = importlib.util.spec_from_file_location('open_items', _PATH)
oi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oi)

TODAY = dt.date(2026, 9, 30)


def item(desc='an item', status='open', assignee='', due='', raised=''):
    return oi.Item(desc=desc, status=status, due=due, raised=raised,
                   owner='mobile_ops', src='efforts/projects/mobile_ops.md',
                   assignee=assignee)


class TestLaneOf(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(oi, 'SELF', 'stefan')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_agent_literal_routes_to_the_queue(self):
        self.assertEqual(oi.lane_of(item(assignee='agent')), 'agent')

    def test_configured_self_routes_to_the_human(self):
        self.assertEqual(oi.lane_of(item(assignee='stefan')), 'mine')

    def test_assignee_is_matched_case_insensitively(self):
        self.assertEqual(oi.lane_of(item(assignee='Agent')), 'agent')
        self.assertEqual(oi.lane_of(item(assignee=' Stefan ')), 'mine')

    def test_any_other_name_is_silent(self):
        self.assertEqual(oi.lane_of(item(assignee='willem')), 'other')

    def test_absent_assignee_is_unrouted_never_agent(self):
        # The load-bearing one: if absence resolved to `agent`, the queue would start
        # work nobody delegated.
        self.assertEqual(oi.lane_of(item(assignee='')), 'unrouted')

    def test_blocked_outranks_the_lane(self):
        # Unblocking is a human act, so a blocked item is the human's whoever holds it.
        for who in ('agent', 'willem', ''):
            with self.subTest(assignee=who):
                self.assertEqual(oi.lane_of(item(status='blocked', assignee=who)), 'mine')

    def test_done_leaves_the_lanes_entirely(self):
        self.assertEqual(oi.lane_of(item(status='done', assignee='agent')), 'done')

    def test_unconfigured_self_claims_nothing(self):
        # An unconfigured vault must show items as someone else's, not silently as mine.
        with mock.patch.object(oi, 'SELF', ''):
            self.assertEqual(oi.lane_of(item(assignee='stefan')), 'other')


class TestIsRipe(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(oi, 'SELF', 'stefan')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_unrouted_is_always_ripe(self):
        self.assertTrue(oi.is_ripe(item(assignee=''), TODAY))

    def test_overdue_is_ripe(self):
        self.assertTrue(oi.is_ripe(item(assignee='stefan', due='2026-09-27'), TODAY))

    def test_due_today_is_ripe(self):
        self.assertTrue(oi.is_ripe(item(assignee='stefan', due='2026-09-30'), TODAY))

    def test_future_due_is_parked(self):
        self.assertFalse(oi.is_ripe(item(assignee='stefan', due='2026-10-06'), TODAY))

    def test_undated_is_never_ripe(self):
        # This is what keeps the session-start prompt short enough to answer.
        self.assertFalse(oi.is_ripe(item(assignee='stefan'), TODAY))

    def test_malformed_due_does_not_crash(self):
        oi.is_ripe(item(assignee='stefan', due='not-a-date'), TODAY)

    def test_malformed_due_is_ripe_so_the_typo_gets_fixed(self):
        # Changed deliberately: this used to assert False, i.e. an unreadable date was
        # treated as no date and parked silently. Nobody was ever told to fix it.
        self.assertTrue(oi.is_ripe(item(assignee='stefan', due='2026-10-32'), TODAY))
        self.assertIn('unreadable due date',
                      oi.why_ripe(item(assignee='stefan', due='2026-10-32'), TODAY))


class TestIsReady(unittest.TestCase):
    """The agent lane's predicate. Deliberately not is_ripe(): for a human an undated
    item is not ripe (don't nag), for the queue it is ready now."""

    def setUp(self):
        patcher = mock.patch.object(oi, 'SELF', 'stefan')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_undated_agent_item_is_ready_now(self):
        self.assertTrue(oi.is_ready(item(assignee='agent'), TODAY))

    def test_future_due_parks_an_agent_item(self):
        # The regression that prompted this: a re-check deliberately deferred to next
        # week was otherwise executed the day it was written.
        deferred = item('re-check next week', assignee='agent', due='2026-10-06')
        self.assertFalse(oi.is_ready(deferred, TODAY))
        self.assertTrue(oi.is_ready(deferred, dt.date(2026, 10, 6)))

    def test_overdue_agent_item_is_ready(self):
        self.assertTrue(oi.is_ready(item(assignee='agent', due='2026-09-01'), TODAY))

    def test_queue_lane_excludes_parked_items(self):
        items = [item('ready now', assignee='agent'),
                 item('parked', assignee='agent', due='2026-10-06')]
        picked = oi.lane_items(items, 'agent', TODAY, show_all=False)
        self.assertEqual([i.desc for i in picked], ['ready now'])

    def test_unreadable_due_never_authorises_the_queue(self):
        # `[due:: 2026-10-32]` is a plausible typo, and due_date() collapses it to None
        # — which the queue read as "ready now". A deliberately deferred re-check ran
        # the day it was written, straight around test_future_due_parks_an_agent_item.
        typo = item('re-check next week', assignee='agent', due='2026-10-32')
        self.assertFalse(oi.is_ready(typo, TODAY))
        self.assertEqual(oi.lane_items([typo], 'agent', TODAY, show_all=False), [])

    def test_ripe_and_ready_disagree_on_an_unreadable_due(self):
        # Opposite directions on purpose: show the human so it gets fixed, refuse the
        # queue so a slip of the keyboard cannot authorise unattended work.
        typo = item(assignee='agent', due='2026-13-01')
        self.assertTrue(oi.is_ripe(typo, TODAY))
        self.assertFalse(oi.is_ready(typo, TODAY))


class TestWhyRipe(unittest.TestCase):
    def test_reasons_read_correctly_either_side_of_the_due_date(self):
        self.assertEqual(oi.why_ripe(item(assignee='agent', due='2026-09-27'), TODAY),
                         'overdue 3d (due 2026-09-27)')
        self.assertEqual(oi.why_ripe(item(assignee='agent', due='2026-09-30'), TODAY),
                         'due today (2026-09-30)')
        self.assertEqual(oi.why_ripe(item(assignee='agent', due='2026-10-06'), TODAY),
                         'due in 6d (2026-10-06)')

    def test_unrouted_says_so(self):
        with mock.patch.object(oi, 'SELF', 'stefan'):
            self.assertEqual(oi.why_ripe(item(assignee=''), TODAY),
                             'unrouted — needs an assignee')


class TestDerivedOrder(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(oi, 'SELF', 'stefan')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ripe_blocked_then_overdue_then_soonest_then_oldest(self):
        # Only 1 day overdue, against an open item 10 days overdue: ripe-blocked still
        # wins, which is the whole point of the first tier.
        ripe_blocked = item('blocked and ripe', status='blocked',
                            assignee='stefan', due='2026-09-29')
        overdue = item('overdue', assignee='stefan', due='2026-09-20')
        soon = item('due soon', assignee='stefan', due='2026-10-02')
        old_undated = item('undated, old', assignee='stefan', raised='2026-01-01')
        new_undated = item('undated, new', assignee='stefan', raised='2026-09-29')

        got = sorted([new_undated, soon, old_undated, overdue, ripe_blocked],
                     key=lambda i: oi.sort_key(i, TODAY))
        self.assertEqual([i.desc for i in got],
                         ['blocked and ripe', 'overdue', 'due soon',
                          'undated, old', 'undated, new'])

    def test_done_sorts_last(self):
        done = item('finished', status='done', assignee='stefan', due='2026-01-01')
        openish = item('still open', assignee='stefan', due='2026-12-01')
        got = sorted([done, openish], key=lambda i: oi.sort_key(i, TODAY))
        self.assertEqual([i.desc for i in got], ['still open', 'finished'])


class TestLaneRendering(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(oi, 'SELF', 'stefan')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.items = [
            item('overdue thing', assignee='stefan', due='2026-09-27'),
            item('parked thing', assignee='stefan', due='2026-10-30'),
            item('unrouted thing', assignee=''),
            item('willems thing', assignee='willem'),
            item('queued thing', assignee='agent'),
        ]

    def test_digest_shows_ripe_and_counts_parked(self):
        out = oi.render_lane(self.items, 'mine', TODAY, show_all=False)
        self.assertIn('overdue thing', out)
        self.assertIn('unrouted thing', out)
        self.assertNotIn('parked thing', out)
        self.assertIn('1 parked', out)

    def test_another_persons_item_never_appears(self):
        out = oi.render_lane(self.items, 'mine', TODAY, show_all=True)
        self.assertNotIn('willems thing', out)

    def test_all_shows_the_parked_items_too(self):
        out = oi.render_lane(self.items, 'mine', TODAY, show_all=True)
        self.assertIn('parked thing', out)

    def test_agent_lane_holds_only_open_agent_items(self):
        out = oi.render_lane(self.items, 'agent', TODAY, show_all=True)
        self.assertIn('queued thing', out)
        self.assertNotIn('overdue thing', out)


class TestMalformedDueIsSurfaced(unittest.TestCase):
    """The lint line, which had no test at all — the half of this whose own docstring
    calls its absence "the quietest possible failure"."""

    def setUp(self):
        patcher = mock.patch.object(oi, 'SELF', 'stefan')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_agent_item_with_a_bad_date_reaches_the_human(self):
        # It falls out of both lanes otherwise: the agent lane filters on is_ready,
        # which refuses it, and the human digest renders only mine and unrouted.
        typo = item('re-check', assignee='agent', due='2026-10-32')
        self.assertEqual(oi.malformed_due_items([typo]), [typo])
        out = oi.render_lane([typo], 'mine', TODAY, show_all=False)
        self.assertIn('unreadable due date', out)
        self.assertIn('2026-10-32', out)

    def test_a_done_item_is_not_nagged_about(self):
        self.assertEqual(
            oi.malformed_due_items([item(status='done', due='nonsense')]), [])

    def test_the_other_lane_stays_silent(self):
        # AGENTS.md: another dev's item is never raised unless asked for by name.
        theirs = item('their thing', assignee='jamie', due='2026-10-32')
        self.assertEqual(oi.render_lane([theirs], 'other', TODAY, show_all=False), '')

    def test_a_listed_item_is_not_also_warned_about(self):
        mine = item('mine', assignee='stefan', due='2026-10-32')
        out = oi.render_lane([mine], 'mine', TODAY, show_all=False)
        self.assertEqual(out.count('mine'), 1, f'listed twice:\n{out}')


class TestTicketAndPathsAreDerivedNotDeclared(unittest.TestCase):
    """The queue's machine surface, added after the first supervised run (2026-10-02).

    open_item.md rules out a `ticket::` inline field on purpose: the mapping is one line
    of prose and a field buys nothing the description does not already carry. Both of
    these parse conventions that already exist in the prose, so the item syntax is
    unchanged and `--json` gains the two things the queue's gates needed and never had.
    """

    def test_a_tracked_as_reference_yields_the_number(self):
        self.assertEqual(
            oi.ticket_of('Fix the thing. Tracked as [#44239](https://tracker.example.test/x)'),
            '44239')

    def test_no_reference_yields_empty_not_none(self):
        # The gate is `not item["ticket"]`; None and '' must not behave differently.
        self.assertEqual(oi.ticket_of('Fix the thing'), '')

    def test_a_bare_hash_number_is_not_a_ticket(self):
        # "#44239" appears in commit messages and PR titles all over the vault.
        self.assertEqual(oi.ticket_of('squash-merged as #44239'), '')

    def test_backticked_paths_are_found_in_order(self):
        self.assertEqual(
            oi.paths_in('Move `modules/a/lib/src/x.dart` into `modules/b/lib/`'),
            ['modules/a/lib/src/x.dart', 'modules/b/lib/'])

    def test_identifiers_are_not_paths(self):
        # The live item names `_intlSystemNotBuilt` and `'…'.t(` in backticks.
        self.assertEqual(
            oi.paths_in("Delete `_intlSystemNotBuilt` once the first `'…'.t(` call lands"),
            [])

    def test_a_root_filename_counts(self):
        # AGENTS.md is on the denylist and is named without a directory.
        self.assertEqual(oi.paths_in('Re-check the flavour naming in `AGENTS.md`'),
                         ['AGENTS.md'])

    def test_duplicates_collapse(self):
        self.assertEqual(oi.paths_in('`docs/a.md` then `docs/a.md` again'), ['docs/a.md'])

    def test_trailing_punctuation_is_stripped(self):
        self.assertEqual(oi.paths_in('see `docs/a.md`.'), ['docs/a.md'])

    def test_both_reach_the_json_surface(self):
        it = oi.Item(desc='Fix `apps/shop/lib/a.dart`. Tracked as [#9](u)',
                     status='open', due='', raised='2026-09-01',
                     owner='x', src='x.md', assignee='agent')
        with mock.patch.object(oi, 'scan', return_value=[it]):
            payload = oi.lane_json([it], 'agent', dt.date(2026, 10, 2), True)
        entry = json.loads(payload)['items'][0]
        self.assertEqual(entry['ticket'], '9')
        self.assertEqual(entry['paths'], ['apps/shop/lib/a.dart'])


class TestOwnerOf(unittest.TestCase):
    def test_research_note_is_a_real_owner(self):
        owner, is_view = oi.owner_of('calendar/research/deep_linking.md')
        self.assertEqual(owner, 'deep_linking')
        self.assertFalse(is_view)

    def test_research_owner_renders_as_a_wikilink(self):
        """`day:`-prefixed owners are printed bare; a real owner must link."""
        owner, _ = oi.owner_of('calendar/research/deep_linking.md')
        self.assertFalse(owner.startswith('day:'))

    def test_time_boxed_calendar_notes_stay_views(self):
        for rel in ('calendar/days/2026-10-01.md',
                    'calendar/briefings/2026-10-01.md',
                    'calendar/meetings/backend_sync.md',
                    'calendar/sprints/Q32026 sprint 3.md'):
            with self.subTest(rel=rel):
                owner, is_view = oi.owner_of(rel)
                self.assertTrue(is_view)
                self.assertTrue(owner.startswith('day:'))

    def test_a_loose_calendar_note_stays_a_view(self):
        """Only research/ is carved out; the default for calendar/ is unchanged."""
        _, is_view = oi.owner_of('calendar/stray.md')
        self.assertTrue(is_view)

    def test_atlas_notes_are_owners(self):
        owner, is_view = oi.owner_of('atlas/config/developer_tooling.md')
        self.assertEqual(owner, 'developer_tooling')
        self.assertFalse(is_view)


class TestDedupe(unittest.TestCase):
    """dedupe must use the same view rule as owner_of, not its own copy."""

    def item(self, src):
        return oi.Item(desc='wire release signing', status='open', due='',
                       raised='', owner=oi.owner_of(src)[0], src=src)

    def test_atlas_note_beats_a_day_note(self):
        kept = oi.dedupe([self.item('calendar/days/2026-10-01.md'),
                          self.item('atlas/config/developer_tooling.md')])
        self.assertEqual([i.src for i in kept], ['atlas/config/developer_tooling.md'])

    def test_research_note_beats_a_day_note(self):
        kept = oi.dedupe([self.item('calendar/days/2026-10-01.md'),
                          self.item('calendar/research/deep_linking.md')])
        self.assertEqual([i.src for i in kept], ['calendar/research/deep_linking.md'])

    def test_a_day_note_never_displaces_a_research_note(self):
        kept = oi.dedupe([self.item('calendar/research/deep_linking.md'),
                          self.item('calendar/days/2026-10-01.md')])
        self.assertEqual([i.src for i in kept], ['calendar/research/deep_linking.md'])


if __name__ == '__main__':
    unittest.main()
