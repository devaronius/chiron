#!/usr/bin/env python3
"""
pr — the inspector's pull-request client: the verbs its runbook's mode 2 asks for.

The verb list is the agent's capability boundary: there is deliberately **no verb that
votes and none that moves a ticket**, because approving a PR and signing it off are the
human's to keep. `sync` is the only verb that writes, and it posts nothing the grader
refuses.

The tracker is `agents.inspector.tracker` in aios.config.json — `github` (through `gh`)
or `ado` (Azure DevOps, configured under `ado`). Every adapter ships; the config picks
one, so `agents.inspector.scripts` always names this file whatever the tracker.

Usage:
  python3 aiOS/tools/inspector/pr.py show   --pr 207
  python3 aiOS/tools/inspector/pr.py story  --ticket 206
  python3 aiOS/tools/inspector/pr.py diff   --pr 207 [--name-only]
  python3 aiOS/tools/inspector/pr.py tree   --pr 207
  python3 aiOS/tools/inspector/pr.py body   --pr 207
  python3 aiOS/tools/inspector/pr.py policy --pr 207
  python3 aiOS/tools/inspector/pr.py sync   --pr 207 --report <scratchpad>/findings-207.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import grading  # noqa: E402
from client import core  # noqa: E402
from client.ado import Ado  # noqa: E402
from client.github import GitHub  # noqa: E402

CONFIG = HERE.parents[1] / 'aios.config.json'
ADAPTERS = {'github': GitHub, 'ado': Ado}


def load_config(path: pathlib.Path = CONFIG) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def settings(config: dict) -> dict:
    return (config.get('agents') or {}).get('inspector') or {}


def adapter_from_config(config: dict):
    tracker = settings(config).get('tracker')
    if tracker not in ADAPTERS:
        raise core.InspectorError(
            f'no adapter for {tracker!r} — set agents.inspector.tracker in aios.config.json '
            f'to one of {sorted(ADAPTERS)}')
    return ADAPTERS[tracker](config)


def story(client, number: int) -> dict:
    """A ticket's statement of intent, with its ACs numbered so a finding can cite one."""
    issue = client.ticket(number)
    # A tracker with a criteria field of its own hands them over; otherwise they are the
    # Acceptance section of the ticket's body.
    criteria = (issue['criteria'] if 'criteria' in issue
                else core.acceptance_criteria(issue['body']))
    out = {k: v for k, v in issue.items() if k != 'criteria'}
    out['acceptance_criteria'] = {f'#{number} AC{i}': text
                                  for i, text in enumerate(criteria or [], 1)}
    if criteria is None:
        out['reason'] = 'no acceptance criteria — review against the title and body'
    out['basis_fingerprint'] = core.fingerprint(json.dumps(out['acceptance_criteria']))
    return out


def cmd_show(client, config, args) -> dict:
    pr = client.pull_request(args.pr)
    gate = settings(config)
    return {
        **{k: pr[k] for k in ('number', 'title', 'state', 'url', 'author', 'base', 'head',
                              'head_sha')},
        'description': pr['body'],
        'release_pr': core.release_gate(pr['base'], pr['head'], gate.get('releaseTargets') or (),
                                        gate.get('releaseSources') or ()),
        'tickets': [story(client, n) for n in pr['tickets']],
        'basis': (', '.join(f'#{n}' for n in pr['tickets']) if pr['tickets']
                  else 'no linked ticket — review against the PR description'),
        'existing': sorted(p.key for p in client.mine(args.pr)),
    }


def _git(*args: str) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True, check=True).stdout


def cmd_tree(client, config, args) -> str:
    """Can the working tree serve as the test bed? Computed, not judged: the inspector is
    the party with an incentive to answer yes."""
    pr = client.pull_request(args.pr)
    patterns = settings(config).get('testAffecting') or []
    head, source = _git('rev-parse', 'HEAD').strip(), pr['head_sha']
    root = _git('rev-parse', '--show-toplevel').strip()
    dirty = core.test_affecting(core.porcelain_paths(_git('status', '--porcelain', '-uall')),
                                patterns)
    reasons = []
    if not source:
        reasons.append('the PR reports no head commit, so there is nothing to match')
    elif head != source:
        reasons.append(f'HEAD {head[:9]} != PR head {source[:9]}')
    if dirty:
        reasons.append(f'{len(dirty)} test-affecting path(s) dirty: {", ".join(dirty[:5])}'
                       + (' …' if len(dirty) > 5 else ''))
    if reasons:
        return '\n'.join(['in-place: NO', f'  measured: {root}', *(f'  - {r}' for r in reasons),
                          '', f'Use a worktree: {client.worktree_hint(pr)}'])
    matched = (', '.join(patterns) if patterns
               else 'any path (no agents.inspector.testAffecting configured)')
    return '\n'.join([
        'in-place: OK', f'  measured: {root}', f'  - HEAD {head[:9]} == PR head',
        f'  - no dirty path matches {matched} (untracked files expanded)', '',
        f'Tests: ran in place at {head[:9]} (matches PR head; tree clean of test-affecting '
        'paths) — <packages>, <result>'])


def cmd_body(client, config, args) -> list[dict]:
    template = client.template()
    if template is None:
        return [{'rule': 'pr-body', 'severity': 'note',
                 'summary': 'the repo has no PR template — the body was not checked',
                 'fix': ''}]
    pr = client.pull_request(args.pr)
    problems = core.body_problems(template, pr['body'],
                                  ci_checks_headings=client.body_checked_by_ci(pr))
    if not client.links_ticket(pr):
        problems.append({'rule': 'missing-work-item', 'severity': 'medium',
                         'summary': 'the PR links no ticket', 'fix': client.LINK_FIX})
    return problems


def cmd_policy(client, config, args) -> dict:
    return client.build(client.pull_request(args.pr))


def cmd_sync(client, config, args) -> str:
    pr = client.pull_request(args.pr)
    gate = core.release_gate(pr['base'], pr['head'],
                             settings(config).get('releaseTargets') or (),
                             settings(config).get('releaseSources') or ())
    if gate and not args.force:
        raise core.InspectorError(
            f'PR {args.pr} is release integration ({gate}). Its QA is the release '
            'pipeline, not a per-finding review. Pass --force only if you mean it.')
    report = grading.load_report(args.report, args.pr)
    plan = core.plan_sync(report, args.pr, client.login(), client.mine(args.pr),
                          client.anchors(args.pr), grading.load_rules())
    done = client.apply(pr, plan)
    return '\n'.join([*done, f'vote left to the human: {pr["url"]}'])


def main(argv: list[str] | None = None, client=None, config: dict | None = None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False, description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('show', 'tree', 'body', 'policy'):
        sub.add_parser(name).add_argument('--pr', type=int, required=True)
    sub.add_parser('story').add_argument('--ticket', type=int, required=True)
    diff = sub.add_parser('diff')
    diff.add_argument('--pr', type=int, required=True)
    diff.add_argument('--name-only', action='store_true')
    sync = sub.add_parser('sync')
    sync.add_argument('--pr', type=int, required=True)
    sync.add_argument('--report', required=True)
    sync.add_argument('--force', action='store_true')
    args = ap.parse_args(argv)
    try:
        config = load_config() if config is None else config
        client = client or adapter_from_config(config)
        if args.cmd == 'story':
            out = story(client, args.ticket)
        elif args.cmd == 'diff':
            out = client.diff(args.pr, args.name_only)
        else:
            out = {'show': cmd_show, 'tree': cmd_tree, 'body': cmd_body,
                   'policy': cmd_policy, 'sync': cmd_sync}[args.cmd](client, config, args)
    except (core.InspectorError, grading.InspectorError, OSError, json.JSONDecodeError,
            subprocess.CalledProcessError) as e:
        print(f'✗ {e}', file=sys.stderr)
        return 1
    print(out if isinstance(out, str) else json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
