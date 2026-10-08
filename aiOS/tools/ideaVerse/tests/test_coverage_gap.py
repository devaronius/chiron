"""coverage-gap's config wiring and its blind-spot reporting.

Both exist because of the same failure. `kanban-sync.py` reconciled a board this repo
never had, from three call sites, for months — nothing flagged it, because a check that
finds no input reports success. The audit that followed found the same shape in this
script: aios.config.json declared `apiClassMarker`, `sourceExt` and friends while the
script carried its own hardcoded copies, so the config was dead and could not have
changed anything.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import unittest

_HERE = pathlib.Path(__file__).resolve()
_PATH = _HERE.parent.parent / 'coverage-gap.py'
_spec = importlib.util.spec_from_file_location('coverage_gap', _PATH)
cg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cg)

CONFIG = json.loads((_HERE.parents[3] / 'aios.config.json').read_text(encoding='utf-8'))
CODE = CONFIG['code']


#: Each `code` key and how to read its value off the module. A key present in the config
#: must appear here, and every entry here must reach a constant — a config key that
#: cannot change behaviour is worse than none, because it reads as though it can.
CONSUMERS = {
    'sourceExt': lambda: cg.SOURCE_EXT,
    'testSuffix': lambda: cg.TEST_SUFFIX,
    'apiClassMarker': lambda: cg.API_CLASS_MARKER,
    'featureDir': lambda: cg.FEATURE_DIR,
    'appNoteSuffix': lambda: cg.APP_NOTE_SUFFIX,
    'packagePattern': lambda: cg.PACKAGE_PATTERN,
    'apiClassExclude': lambda: sorted(cg.API_CLASS_EXCLUDE),
    'packageDir': lambda: cg.MODULES_DIR.name if cg.MODULES_DIR else '',
    'appDir': lambda: cg.APPS_DIR.name if cg.APPS_DIR else '',
    # Read by verify-claims, not by coverage-gap; listed so it is not an orphan.
    'testCommand': None,
}


class TestConfigIsLive(unittest.TestCase):
    """The `code` block and the module that reads it cannot drift apart.

    Written against whatever this vault actually configures, not against a fixed key
    set: a vault with no code to scan configures nothing, and the checks it would drive
    are off by design rather than broken.
    """

    def test_every_config_key_drives_a_constant(self):
        for key, value in CODE.items():
            read = CONSUMERS.get(key)
            with self.subTest(key=key):
                self.assertIn(key, CONSUMERS, f'`code.{key}` reaches no constant')
                if read is None:
                    continue
                expected = sorted(value) if isinstance(value, list) else value
                self.assertEqual(read(), expected)

    def test_no_orphan_keys(self):
        # A key the config carries that nothing consumes is decorative; the next reader
        # has to learn that before trusting it, and this is where they learn it.
        self.assertEqual(set(CODE) - set(CONSUMERS), set())


class TestBlindSpotReporting(unittest.TestCase):
    def test_a_marker_matching_nothing_is_reported(self):
        lines = cg.vacuous_lines()
        if not lines:
            self.skipTest('every detector matched something in this repo')
        self.assertIn('matched nothing', lines[0])

    def test_blind_spots_appear_in_a_complete_report(self):
        report = cg.format_report([], note_count=1)
        self.assertIn('Health: COMPLETE', report)
        for line in cg.vacuous_lines():
            self.assertIn(line, report)

    def test_blind_spots_appear_alongside_real_gaps_too(self):
        gap = [{'type': 'x', 'item': 'y', 'severity': 'high', 'detail': 'd'}]
        report = cg.format_report(gap, note_count=1)
        self.assertIn('NEEDS ATTENTION', report)
        for line in cg.vacuous_lines():
            self.assertIn(line, report)

    def test_an_empty_marker_is_not_reported_as_blind(self):
        # An empty marker means "this project has no such pattern", which is a
        # statement, not an oversight.
        original = cg.API_CLASS_MARKER
        try:
            cg.API_CLASS_MARKER = ''
            self.assertFalse(any('apiClassMarker' in l for l in cg.vacuous_lines()))
        finally:
            cg.API_CLASS_MARKER = original


if __name__ == '__main__':
    unittest.main()
