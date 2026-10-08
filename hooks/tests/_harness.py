"""Import bootstrap for the hook tests.

Not named `test_*`, so `unittest discover` imports it but never runs it.

Hook filenames are hyphenated and therefore not legal module names, so each is loaded
by path. Every hook reads stdin and exits with a code; nothing here invokes one as a
subprocess — the functions are called directly, so the tests neither shell out nor
touch a tracker, the remote or the vault.
"""
from __future__ import annotations

import importlib.util
import pathlib

HOOKS_DIR = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = HOOKS_DIR.parents[1]


def _load(name: str, filename: str):
    path = HOOKS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: PreToolUse — bounds the `researcher` agent a dispatcher sends off unattended.
scope = _load('researcher_scope', 'researcher-scope.py')

#: PreToolUse — bounds the `inspector` QA agent that reviews code and PRs.
inspector_scope = _load('inspector_scope', 'inspector-scope.py')

#: SessionStart — injects the ripe open-item digest.
lane = _load('open_items_lane', 'open-items-lane.py')


def settings() -> dict | None:
    """`.claude/settings.json`, or None when the hooks are not wired here.

    chiron ships the hooks but never writes a consumer's settings file — wiring a hook
    is a decision a human makes, not one an installer makes for them. So every wiring
    assertion is conditional: it verifies the wiring a repo *has*, and says plainly that
    there is none rather than passing silently or failing a fresh install.
    """
    import json
    path = REPO_ROOT / '.claude' / 'settings.json'
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
