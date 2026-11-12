"""
core — what the inspector's pull-request client does, with no tracker in it.

The agent decides *what* a finding is; this decides *how* a graded report becomes posts,
and nothing here talks to a tracker. An adapter (`github.py`, `ado.py`) fetches what is
already on the PR and carries out the plan this returns, so the one non-obvious
mechanism — idempotency — is written once for every tracker.

Every post ends in a hidden key derived from the *finding*, never from a line number,
which shifts under any edit above it:

    <!-- qa:<ticket>:<path>:<slug> -->

`plan_sync` reads the keys already on the PR and plans only the difference: post what is
new, rewrite what changed, reply once to what stopped reproducing, edit the summary in
place. A post without our key, or with it but by another account, is never touched.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

SIGNATURE = '— `inspector` (QA agent), run by {login}'
KEY_RE = re.compile(r'<!--\s*(qa:[^\s>]+)\s*-->')
SLUG_RE = re.compile(r'[^a-z0-9]+')

SEVERITIES = ('critical', 'high', 'medium', 'low', 'note')
POSTED = ('critical', 'high', 'medium', 'low')  # notes fold into the summary

# A finding is read in a narrow pane by someone deciding what to do next, so it is laid
# out in labelled blocks rather than trusting each report to format itself.
SECTIONS = (('failure', 'What happens'), ('evidence', 'Evidence'), ('why', 'Why'),
            ('impact', 'Impact'), ('fix', 'Fix'))

AC_HEADING = re.compile(r'^(#{2,3})\s+Acceptance(?:\s+criteria)?\s*$', re.IGNORECASE)
HEADING = re.compile(r'^(#{1,6})\s+(.*?)\s*$')
ITEM = re.compile(r'^\s*(?:[-*]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.+?)\s*$')
COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)


class InspectorError(RuntimeError):
    pass


# ---------------------------------------------------------------- keys


def finding_key(ticket: str, path: str, slug: str) -> str:
    """The stable identity of a finding. Line numbers are deliberately absent."""
    clean = SLUG_RE.sub('-', slug.lower()).strip('-')
    return f'qa:{ticket or "none"}:{path or "-"}:{clean}'


def summary_key(pr: int | str) -> str:
    return f'qa:summary:{pr}'


def key_of(body: str) -> str | None:
    found = KEY_RE.search(body or '')
    return found.group(1) if found else None


def same_body(posted: str, rendered: str) -> bool:
    """Whether a post already says what we would say now, whitespace aside."""
    return ' '.join((posted or '').split()) == ' '.join((rendered or '').split())


# ---------------------------------------------------------------- rendering


def signature(login: str) -> str:
    return SIGNATURE.format(login=login)


def render_finding(finding: dict, key: str, login: str) -> str:
    lines = [f'**{finding["severity"].upper()}** · `{finding["rule"]}` — {finding["summary"]}', '']
    if finding.get('ac'):
        lines += [f'Breaks **{finding["ac"]}**.', '']
    for name, label in SECTIONS:
        value = (finding.get(name) or '').strip()
        if value:
            lines += [f'**{label}**', '', value, '']
    lines += [signature(login), '', f'<!-- {key} -->']
    return '\n'.join(lines)


def _where(finding: dict) -> str:
    path = finding.get('path') or '-'
    return f'`{path}:{finding["line"]}`' if finding.get('line') else f'`{path}`'


def render_summary(report: dict, key: str, login: str, unanchored: list[dict]) -> str:
    counts = {s: sum(f['severity'] == s for f in report['findings']) for s in SEVERITIES}
    lines = [
        f'## QA — {report["recommendation"]}', '',
        f'**Verified against:** {report["basis"]}',
        f'**Tests:** {report["tests"]}',
    ]
    if report.get('coverage'):
        lines.append(f'**Coverage:** {report["coverage"]}')
    lines += ['', ' · '.join(f'{n} {s}' for s, n in counts.items())]
    if unanchored:
        # A tracker anchors a comment only where it can place it — GitHub only on a line
        # inside the diff — so a finding whose fix goes elsewhere is carried here rather
        # than dropped.
        lines += ['', '### Findings outside the diff', '']
        for f in unanchored:
            lines.append(f'- **{f["severity"].upper()}** · `{f["rule"]}` {_where(f)} — '
                         f'{f["summary"]} **Fix:** {(f.get("fix") or "").strip()}')
    if report.get('follow_ups'):
        lines += ['', '### Follow-ups', '']
        lines += [f'- **{u["target"]}** — {u["summary"]}' for u in report['follow_ups']]
    for name, heading in (('checked', 'Checked'), ('unverified', 'Not verified')):
        if report.get(name):
            lines += ['', f'### {heading}', '']
            lines += [f'- {item}' for item in report[name]]
    notes = [f for f in report['findings'] if f['severity'] == 'note']
    if notes:
        lines += ['', '<details><summary>Notes</summary>', '']
        lines += [f'- {_where(f)} — {f["summary"]}' for f in notes]
        lines += ['', '</details>']
    lines += ['', 'The vote is not mine to cast — a human decides this PR.', '',
              signature(login), '', f'<!-- {key} -->']
    return '\n'.join(lines)


# ---------------------------------------------------------------- the sync plan

# The client's replies. Every action it takes on a thread leaves one, because that is the
# only mark that tells its action from a human's: it posts as a person, so who resolved a
# thread carries the same login either way.
GONE = 'No longer reproduces as of'
NOTED = 'Now a note as of'
BACK = 'Reproduces again as of'


def last_action(post: 'Posted', login: str) -> str | None:
    """The client's latest action on the thread: 'closed', 'back', or None.

    Read from the whole thread, newest first, so a human comment after the client's
    reply hides nothing. Decisions follow from it: a thread the client closed and that is
    open again was reopened by a human, and is theirs.
    """
    for body in reversed(post.comments or []):
        if signature(login) not in body:
            continue
        if body.startswith((GONE, NOTED)):
            return 'closed'
        if body.startswith(BACK):
            return 'back'
    return None


@dataclass
class Posted:
    """One of our posts already on the PR. `thread` is set for an anchored comment."""
    key: str
    id: str
    body: str
    anchored: bool
    resolved: bool = False
    thread: str | None = None
    comments: list[str] = field(default_factory=list)  # the whole thread, oldest first


@dataclass
class Plan:
    new: list[dict] = field(default_factory=list)       # {key, path, line, body, resolve}
    edits: list[tuple[Posted, str]] = field(default_factory=list)
    stale: list[tuple[Posted, str]] = field(default_factory=list)  # (post, reply body)
    reopen: list[tuple[Posted, str]] = field(default_factory=list)  # (post, reply body)
    settle: list[tuple[Posted, str]] = field(default_factory=list)  # (post, reply body)
    summary: tuple[Posted | None, str] | None = None


def plan_sync(report: dict, pr: int | str, login: str, mine: list[Posted],
              can_anchor, rules: dict[str, dict]) -> Plan:
    """What it takes to bring the PR in line with `report`.

    `mine` is only our own posts — the adapter has already dropped everything without
    our key or not authored by `login`. `can_anchor(path, line)` says whether the tracker
    can anchor a comment there. `rules` supplies each rule's `ceiling`: a report-only
    rule's comment is resolved as it is posted.
    """
    plan = Plan()
    existing = {p.key: p for p in mine}
    ticket = str(report.get('ticket') or '')
    live, unanchored = set(), []
    commit = report.get('commit') or 'the latest push'
    back = f'{BACK} `{commit}`.\n\n{signature(login)}'
    noted = f'{NOTED} `{commit}` — nothing to change.\n\n{signature(login)}'
    for finding in report['findings']:
        key = finding_key(ticket, finding.get('path', ''), finding['slug'])
        body = render_finding(finding, key, login)
        post = existing.get(key)
        if finding['severity'] not in POSTED:
            # A note folds into the summary. If it was posted at a higher grade, its post
            # is rewritten to say note and its thread closed, since a note asks for
            # nothing — but never answered as fixed: it is still reported.
            if post and post.anchored:
                live.add(key)
                if not same_body(post.body, body):
                    plan.edits.append((post, body))
                if not post.resolved and last_action(post, login) != 'closed':
                    plan.settle.append((post, noted))
            continue
        if post and post.anchored:
            live.add(key)
            if not same_body(post.body, body):
                plan.edits.append((post, body))
            # A finding we closed is back — fixed or settled as a note: say so, and reopen
            # the thread if it is resolved, or the regression is invisible. Not after a
            # human resolved it by hand: the client's last action there was not a close.
            if last_action(post, login) == 'closed':
                plan.reopen.append((post, back))
            continue
        path, line = finding.get('path'), finding.get('line')
        if path and line and can_anchor(path, line):
            live.add(key)
            plan.new.append({'key': key, 'path': path, 'line': line, 'body': body,
                             'resolve': bool((rules.get(finding['rule']) or {}).get('ceiling'))})
        else:
            unanchored.append(finding)
    gone = f'{GONE} `{commit}`.\n\n{signature(login)}'
    for post in mine:
        if (post.anchored and post.key not in live and not post.resolved
                and last_action(post, login) != 'closed'):
            plan.stale.append((post, gone))
    key = summary_key(pr)
    plan.summary = (existing.get(key), render_summary(report, key, login, unanchored))
    return plan


# ---------------------------------------------------------------- the PR's own text


def release_gate(base: str, head: str, targets=(), sources=()) -> str | None:
    """Why this PR is release integration, or None for ordinary feature work.

    Merges into a release branch are already-reviewed work whose QA is the release
    pipeline, so the client refuses them rather than posting forty threads. Which
    branches those are is the project's (`agents.inspector.releaseTargets` and
    `releaseSources`); with none configured, nothing is gated.
    """
    if base in targets:
        return f'targets {base}'
    if head in sources:
        return f'merges {head}'
    return None


def acceptance_criteria(body: str) -> list[str] | None:
    """The top-level items under a ticket's Acceptance heading, or None when it has none.

    The section runs to the next heading of the same or a higher level. `-`, `*` and
    numbered (`1.`, `1)`) items all count, and a line wrapped onto the next one stays
    part of its item. A ticked box is returned like any other: it is the author's
    claim, not a verdict.
    """
    lines = (body or '').splitlines()
    for i, line in enumerate(lines):
        found = AC_HEADING.match(line.strip())
        if not found:
            continue
        level, items, indent, open_item = len(found.group(1)), [], None, False
        for rest in lines[i + 1:]:
            heading = HEADING.match(rest.strip())
            if heading and len(heading.group(1)) <= level:
                break
            if heading or not rest.strip():
                open_item = False
                continue
            depth = len(rest) - len(rest.lstrip())
            item = ITEM.match(rest)
            if not item:
                # A wrapped line continues the item above it — directly under it, or
                # indented past its marker after a blank line.
                if items and (open_item or depth > (indent or 0)):
                    items[-1] += ' ' + rest.strip()
                    open_item = True
                continue
            indent = depth if indent is None else indent
            # A nested item is part of the AC above it, so AC numbers keep matching the
            # ticket's own top-level criteria.
            if depth > indent and items:
                items[-1] += ' ' + item.group(1)
            else:
                items.append(item.group(1))
            open_item = True
        return items
    return None


def fingerprint(text: str) -> str:
    return hashlib.sha256(' '.join(text.split()).encode()).hexdigest()[:12]


def _sections(text: str) -> dict[str, tuple[str, str]]:
    """Each `## ` heading as lower-cased title → (title as written, its text)."""
    out, current = {}, None
    for line in text.splitlines():
        found = re.match(r'^##\s+(.+?)\s*$', line)
        if found:
            title = found.group(1).strip()
            current = title.lower()
            out[current] = (title, '')
        elif current is not None:
            out[current] = (out[current][0], out[current][1] + line + '\n')
    return out


def _empty(section: str) -> bool:
    """Nothing but HTML comments, bare bullets and whitespace."""
    left = COMMENT.sub('', section)
    return all(line.strip() in ('', '-', '*') for line in left.splitlines())


def body_problems(template: str, body: str, ci_checks_headings: bool = False) -> list[dict]:
    """Where a PR body breaks the repo's own PR template.

    Driven by the template rather than by rules written here, so it travels to any repo
    that has one. A **missing** heading is `low`, and is not reported at all when
    `ci_checks_headings`: a CI check that fails the PR for it has already said so. An
    **empty** one is `medium`: a heading left with nothing under it reads as answered.
    Whether the PR links its ticket is the tracker's question, so the CLI asks it.
    """
    problems = []
    wanted = _sections(COMMENT.sub('', template))
    have = _sections(body or '')
    for lowered, (title, _) in wanted.items():
        if lowered not in have:
            if ci_checks_headings:
                continue
            problems.append({'rule': 'pr-body', 'severity': 'low',
                             'summary': f'the `## {title}` section of the PR template is missing',
                             'fix': f'Add `## {title}`, or say in the body why it does not apply.'})
        elif _empty(have[lowered][1]):
            problems.append({'rule': 'pr-body', 'severity': 'medium',
                             'summary': f'`## {title}` is empty',
                             'fix': f'Fill in `## {title}` — write "None." where nothing applies.'})
    if 'type' in wanted and 'type' in have:
        ticked = len(re.findall(r'^\s*[-*]\s+\[[xX]\]', have['type'][1], re.MULTILINE))
        if ticked != 1:
            problems.append({'rule': 'pr-body', 'severity': 'low',
                             'summary': f'`## Type` has {ticked} boxes ticked, not one',
                             'fix': 'Tick exactly the one type that matches the commit prefix.'})
    return problems


# ---------------------------------------------------------------- the working tree


def test_affecting(paths, patterns=()) -> list[str]:
    """The subset of `paths` that could change a test result.

    `patterns` is `agents.inspector.testAffecting`: an entry ending in `/` matches a
    directory anywhere in the path, any other entry a path suffix. With none configured
    every dirty path counts — a guess that a file cannot matter is not this tool's.
    """
    dirs = tuple(p for p in patterns if p.endswith('/'))
    suffixes = tuple(p for p in patterns if not p.endswith('/'))
    if not patterns:
        return sorted(paths)
    return sorted(p for p in paths
                  if (suffixes and p.endswith(suffixes))
                  or any(p.startswith(d) or f'/{d}' in p for d in dirs))


def porcelain_paths(raw: str) -> list[str]:
    """Paths out of `git status --porcelain -uall`, the new side of a rename.

    `-uall` matters: plain `--porcelain` collapses an untracked directory to one entry
    ending in `/`, which matches no suffix, so an untracked package would read as clean.
    """
    paths = []
    for line in raw.splitlines():
        if len(line) < 4:
            continue
        entry = line[3:].strip()
        if ' -> ' in entry:
            entry = entry.split(' -> ', 1)[1]
        paths.append(entry.strip('"'))
    return paths
