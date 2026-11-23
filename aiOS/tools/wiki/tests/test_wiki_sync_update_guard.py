"""wiki-sync --update refuses to baseline sources the wiki does not reflect.

The baseline means "this is compiled". A NEW source that no wiki note cites, or a
NOT RECONCILED one, would be hidden from every later run once baselined. The vault
layout is stubbed: these tests pin the decision, not the scanning.
"""
from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

_PATH = pathlib.Path(__file__).resolve().parent.parent / 'wiki-sync.py'
_spec = importlib.util.spec_from_file_location('wiki_sync', _PATH)
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)


def h(x):
    return {'sha256': x}


class TestUpdateGuard(unittest.TestCase):
    def run_main(self, argv, current, manifest, cover, stale=()):
        tmp = pathlib.Path(tempfile.mkdtemp())
        man = tmp / '.wiki-sync.json'
        if manifest is not None:
            man.write_text(json.dumps({'files': manifest}))
        out = io.StringIO()
        with mock.patch.object(ws, 'MANIFEST', man), \
             mock.patch.object(ws, 'scan_sources', return_value=current), \
             mock.patch.object(ws, 'load_manifest', return_value=manifest or {}), \
             mock.patch.object(ws, 'load_catalog_coverage', return_value=cover), \
             mock.patch.object(ws, 'notes_for', side_effect=lambda k, c: c.get(k, [])), \
             mock.patch.object(ws, 'unreconciled', return_value=list(stale)), \
             mock.patch.object(sys, 'argv', ['wiki-sync.py', *argv]), redirect_stdout(out):
            code = ws.main()
        snap = json.loads(man.read_text())['files'] if man.exists() else None
        return code, out.getvalue(), snap

    def test_refuses_a_new_source_no_wiki_note_cites(self):
        code, out, snap = self.run_main(['--update'], {'a.md': h('1'), 'b.md': h('2')},
                                        {'a.md': h('1')}, {'a.md': ['a']})
        self.assertEqual(code, 1)
        self.assertIn('NEW, no wiki note cites it: b.md', out)
        self.assertEqual(snap, {'a.md': h('1')})  # baseline untouched

    def test_refuses_a_not_reconciled_source(self):
        code, out, _ = self.run_main(['--update'], {'a.md': h('2')}, {'a.md': h('1')},
                                     {'a.md': ['a']}, stale=[('a.md', 'a (updated 1 < source 2)')])
        self.assertEqual(code, 1)
        self.assertIn('NOT RECONCILED: a.md', out)

    def test_allows_a_new_source_that_is_compiled(self):
        code, _, snap = self.run_main(['--update'], {'a.md': h('1'), 'b.md': h('2')},
                                      {'a.md': h('1')}, {'a.md': ['a'], 'b.md': ['b']})
        self.assertEqual(code, 0)
        self.assertIn('b.md', snap)

    def test_force_overrides(self):
        code, _, snap = self.run_main(['--update', '--force'], {'a.md': h('1'), 'b.md': h('2')},
                                      {'a.md': h('1')}, {'a.md': ['a']})
        self.assertEqual(code, 0)
        self.assertIn('b.md', snap)

    def test_first_run_is_exempt(self):
        code, _, snap = self.run_main(['--update'], {'a.md': h('1')}, None, {})
        self.assertEqual(code, 0)
        self.assertIn('a.md', snap)


if __name__ == '__main__':
    unittest.main()
