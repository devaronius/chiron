"""
ado — the inspector client's Azure DevOps adapter. It fetches and it posts; `core` decides.

Talks to the Azure DevOps REST API directly, with the board's identity from the `ado`
section of `aios.config.json`: `org`, `project`, `repoName`, and optionally `repoId`,
which the API then uses in place of the name.
The token is read per invocation and never printed, from the first of:

  * `SYSTEM_ACCESSTOKEN` — a pipeline job's token, sent as a bearer token;
  * `AZURE_DEVOPS_EXT_PAT` — a PAT, the variable the `az devops` CLI already reads;
  * the macOS Keychain, service `ado-pat`, account `$USER`.

**No code path can cast a vote.** A vote on Azure DevOps is a PUT to the PR's
`reviewers` route; nothing here builds that URL, and nothing writes a work item.

Three Azure DevOps traps this adapter is written around:
  * a bad or under-scoped PAT is answered with `203` and an HTML sign-in page, never `401`;
  * a thread's `filePath` must start with `/`, or the anchor is silently dropped;
  * a PATCH on a thread that does not exist succeeds with an empty body, so a status
    change is checked for the thread it claims to have changed.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from . import core

API = '7.1'
API_POLICY = '7.1-preview.1'  # policy evaluations have no 7.1 route
# A thread still asking for something. Every other status reads as resolved.
OPEN = ('active', 'pending')
TEMPLATE_DIRS = ('.azuredevops', '.vsts', 'docs', '')
# A policy evaluation's status, in the words `core`'s callers read.
BUILD_STATES = {'approved': 'approved', 'running': 'running', 'queued': 'queued',
                'rejected': 'failed', 'broken': 'failed'}
# Each commit a build policy validated, and the PR field that must still hold it.
VALIDATED = (('lastMergeSourceCommitId', 'lastMergeSourceCommit'),
             ('lastMergeTargetCommitId', 'lastMergeTargetCommit'),
             ('lastMergeCommitId', 'lastMergeCommit'))


# ---------------------------------------------------------------- auth and transport


def _keychain_pat() -> str:
    try:
        done = subprocess.run(['security', 'find-generic-password', '-s', 'ado-pat',
                               '-a', os.environ.get('USER', ''), '-w'],
                              capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise core.InspectorError(
            'no Azure DevOps token: set AZURE_DEVOPS_EXT_PAT, or on macOS store a PAT in the '
            'Keychain under service `ado-pat`, account $USER.') from None
    return done.stdout.strip()


def authorization() -> str:
    """The Authorization header value. Never logged."""
    if token := os.environ.get('SYSTEM_ACCESSTOKEN'):
        return f'Bearer {token}'
    pat = os.environ.get('AZURE_DEVOPS_EXT_PAT') or _keychain_pat()
    return 'Basic ' + base64.b64encode(f':{pat}'.encode()).decode()


def http(method: str, url: str, body: object = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', authorization())
    req.add_header('Accept', 'application/json')
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            if resp.status == 203 or raw.lstrip().startswith('<'):
                raise core.InspectorError(
                    'Azure DevOps answered with a sign-in page, not JSON: the token is '
                    'expired, revoked, or lacks the Code (read & write) and Work Items '
                    '(read) scopes.')
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise core.InspectorError(f'HTTP {e.code} on {method} {url}: '
                                  f'{e.read().decode()[:300]}') from None


def git(*args: str, auth: str | None = None) -> str:
    """Run git. With `auth`, the header goes in through the environment, never argv,
    so `ps` cannot show the token, and a prompt fails instead of hanging."""
    env = None
    if auth:
        env = {**os.environ, 'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'http.extraheader',
               'GIT_CONFIG_VALUE_0': f'AUTHORIZATION: {auth}', 'GIT_TERMINAL_PROMPT': '0'}
    done = subprocess.run(['git', *args], capture_output=True, text=True, env=env)
    if done.returncode != 0:
        raise core.InspectorError(f'git {args[0]} failed: {done.stderr.strip()}')
    return done.stdout


# ---------------------------------------------------------------- work-item HTML


class _Text(HTMLParser):
    """A work-item field's HTML as markdown-ish text: lists keep their nesting as `-`
    items, links and images keep their targets, so a criterion pointing at a design is
    still one fetch away."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.depth, self.href = [], 0, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('ul', 'ol'):
            self.depth += 1
        elif tag == 'li':
            self.out.append('\n' + '  ' * max(self.depth - 1, 0) + '- ')
        elif tag in ('br', 'p', 'div', 'h1', 'h2', 'h3', 'h4', 'tr'):
            self.out.append('\n')
        elif tag == 'a':
            self.href = attrs.get('href')
        elif tag == 'img' and attrs.get('src'):
            self.out.append(f'[image] ({attrs["src"]})')

    def handle_endtag(self, tag):
        if tag in ('ul', 'ol'):
            self.depth -= 1
            self.out.append('\n')
        elif tag in ('p', 'div', 'li'):
            self.out.append('\n')
        elif tag == 'a' and self.href:
            self.out.append(f' ({self.href})')
            self.href = None

    def handle_data(self, data):
        self.out.append(data)


def html_text(raw: str) -> str:
    parser = _Text()
    parser.feed(raw or '')
    lines = [line.rstrip() for line in ''.join(parser.out).splitlines()]
    return '\n'.join(line for line in lines if line.strip())


def criteria_items(raw: str) -> list[str] | None:
    """The acceptance-criteria field as one item per criterion, or None when empty.

    The field's HTML says where each criterion starts. A line that is not a list item
    starts one, and the list under it belongs to it — a Gherkin `Scenario:` with its
    Given/When/Then is one criterion, not four. A list item with no such line above it is
    a criterion of its own, and a nested item joins its parent.
    """
    items, labelled = [], False
    for line in html_text(raw).splitlines():
        item = re.match(r'^( *)- (.*)$', line)
        if not item:
            items.append(line.strip())
            labelled = True
        elif items and (item.group(1) or labelled):
            items[-1] += ' ' + item.group(2).strip()
        else:
            items.append(item.group(2).strip())
    return items or None


# ---------------------------------------------------------------- the adapter


class Ado:
    # How to link the ticket, for the `missing-work-item` problem `body` reports.
    LINK_FIX = 'Link the work item to the PR (Work items → Add), so the PR names what it answers.'

    def __init__(self, config: dict, request=http, run_git=git, auth=authorization):
        section = config.get('ado') or {}
        missing = [k for k in ('org', 'project', 'repoName') if not section.get(k)]
        if missing:
            raise core.InspectorError(
                'the ado tracker needs ' + ', '.join(f'`ado.{k}`' for k in missing) +
                ' in aios.config.json')
        self.org, self.project = section['org'], section['project']
        self.repo_name = section['repoName']  # the web URL needs the name; the API takes either
        repo = urllib.parse.quote(section.get('repoId') or section['repoName'])
        self.web = f'https://dev.azure.com/{self.org}/{urllib.parse.quote(self.project)}'
        self.base = f'{self.web}/_apis'
        self.repo_api = f'{self.base}/git/repositories/{repo}'
        self.request, self.run_git, self.auth = request, run_git, auth
        self._login = None

    def _get(self, url: str, api: str = API) -> dict:
        sep = '&' if '?' in url else '?'
        return self.request('GET', f'{url}{sep}api-version={api}')

    def _send(self, method: str, url: str, body: dict) -> dict:
        return self.request(method, f'{url}?api-version={API}', body)

    def _pr(self, pr: int) -> str:
        return f'{self.repo_api}/pullRequests/{pr}'

    # ---------------------------------------------------------------- reads

    def login(self) -> str:
        if self._login is None:
            data = self._get(f'https://dev.azure.com/{self.org}/_apis/connectionData',
                             '7.1-preview')
            self._login = data['authenticatedUser']['properties']['Account']['$value']
        return self._login

    def pull_request(self, pr: int) -> dict:
        data = self._get(self._pr(pr))
        items = self._get(f'{self._pr(pr)}/workitems').get('value') or []
        return {
            'number': data['pullRequestId'], 'title': data['title'],
            'body': data.get('description') or '', 'state': data.get('status'),
            'url': f'{self.web}/_git/{urllib.parse.quote(self.repo_name)}/pullrequest/{pr}',
            'author': (data.get('createdBy') or {}).get('uniqueName'),
            'base': data['targetRefName'].removeprefix('refs/heads/'),
            'head': data['sourceRefName'].removeprefix('refs/heads/'),
            'head_sha': (data.get('lastMergeSourceCommit') or {}).get('commitId') or '',
            # Only what Azure DevOps links. A number in the branch name may name a ticket
            # the PR merely relates to, and reviewing against it would be guessing.
            'tickets': [int(w['id']) for w in items],
            'raw': data,
        }

    def ticket(self, number: int) -> dict:
        fields = self._get(f'{self.base}/wit/workitems/{number}')['fields']
        # A Bug keeps its prose in Repro Steps, not the description; reading only the
        # description reports a well-documented bug as blank.
        parts = [html_text(fields.get('System.Description') or '')]
        repro = html_text(fields.get('Microsoft.VSTS.TCM.ReproSteps') or '')
        if repro:
            parts.append(f'## Repro steps\n\n{repro}')
        return {
            'number': number, 'title': fields.get('System.Title'),
            'state': fields.get('System.State'),
            'url': f'{self.web}/_workitems/edit/{number}',
            'labels': [t.strip() for t in (fields.get('System.Tags') or '').split(';') if t.strip()],
            'type': fields.get('System.WorkItemType'),
            'body': '\n\n'.join(p for p in parts if p),
            'criteria': criteria_items(fields.get('Microsoft.VSTS.Common.AcceptanceCriteria') or ''),
        }

    def _fetch(self, pr: dict) -> tuple[str, str]:
        """Fetch both branches into `refs/inspector/*` — never moving `origin/*` or a
        branch a human is standing on — and return (merge base, source ref)."""
        source, target = (f'refs/inspector/{pr["head"]}', f'refs/inspector/{pr["base"]}')
        url = f'{self.web}/_git/{urllib.parse.quote(self.repo_name)}'
        self.run_git('fetch', '--no-tags', url, f'+refs/heads/{pr["head"]}:{source}',
                     f'+refs/heads/{pr["base"]}:{target}', auth=self.auth())
        return self.run_git('merge-base', target, source).strip(), source

    def diff(self, pr: int, name_only: bool = False) -> str:
        """The PR's diff, three-dot against the merge base, computed with git: the API's
        diff route lists changed files, not their content."""
        base, source = self._fetch(self.pull_request(pr))
        return self.run_git('diff', *(['--name-only'] if name_only else []), base, source)

    def anchors(self, pr: int):
        """Azure DevOps anchors a thread to any line of a file the PR changes."""
        changed = set(self.diff(pr, name_only=True).split())
        return lambda path, line: path in changed

    def template(self) -> str | None:
        """The repo's PR template, where Azure DevOps looks for it."""
        root = pathlib.Path(self.run_git('rev-parse', '--show-toplevel').strip())
        for folder in TEMPLATE_DIRS:
            directory = root / folder
            if not directory.is_dir():
                continue
            for path in directory.iterdir():
                if path.name.lower() == 'pull_request_template.md':
                    return path.read_text(encoding='utf-8')
        return None

    def links_ticket(self, pr: dict) -> bool:
        return bool(pr['tickets'])

    def body_checked_by_ci(self, pr: dict) -> bool:
        return False

    def build(self, pr: dict) -> dict:
        """The PR's one blocking build policy, and whether it validated the PR as it is now.

        An `approved` build of an older head proves nothing about this one, so `current`
        requires the source, target and merge commits it validated to be the PR's own.
        """
        raw = pr['raw']
        project = (raw.get('repository') or {}).get('project', {}).get('id', '')
        artifact = urllib.parse.quote(f'vstfs:///CodeReview/CodeReviewId/{project}/{pr["number"]}',
                                      safe='')
        evaluations = self._get(f'{self.base}/policy/evaluations?artifactId={artifact}',
                                API_POLICY).get('value') or []
        out = {'head': pr['head_sha'], 'state': 'none', 'current': False, 'build_id': None,
               'reason': ''}
        builds = [e for e in evaluations if (e.get('configuration') or {}).get('isBlocking')
                  and (e.get('context') or {}).get('buildId')]
        if not builds:
            return {**out, 'reason': 'no blocking policy carries a build'}
        if len(builds) > 1:
            return {**out, 'state': 'ambiguous',
                    'reason': f'{len(builds)} blocking policies carry a build'}
        context = builds[0]['context']
        status = str(builds[0].get('status'))
        out.update(state=BUILD_STATES.get(status, status), build_id=context['buildId'])
        for key, name in VALIDATED:
            commit = (raw.get(name) or {}).get('commitId')
            if not commit or context.get(key) != commit:
                return {**out, 'reason': f'build {context["buildId"]} validated {key} '
                                         f'{str(context.get(key))[:7]}, but the PR is at '
                                         f'{str(commit)[:7]}; queue it again'}
        return {**out, 'current': True}

    def worktree_hint(self, pr: dict) -> str:
        return f'git worktree add <scratchpad>/wt refs/inspector/{pr["head"]}'

    def mine(self, pr: int) -> list[core.Posted]:
        """Our own threads: the first real comment carries our key and is by our login.

        The key alone is not ownership — another account's inspector run plants the
        same marker, and only a comment's author may edit it. System threads (votes,
        pushes, policy events) carry no content and are skipped.
        """
        me, out = self.login().lower(), []
        for thread in self._get(f'{self._pr(pr)}/threads').get('value') or []:
            if thread.get('isDeleted'):
                continue
            comments = [c for c in thread.get('comments') or []
                        if c.get('content') and not c.get('isDeleted')]
            if not comments:
                continue
            lead = comments[0]
            key = core.key_of(lead['content'])
            if not key or ((lead.get('author') or {}).get('uniqueName') or '').lower() != me:
                continue
            out.append(core.Posted(key, str(lead['id']), lead['content'],
                                   bool(thread.get('threadContext')),
                                   thread.get('status') not in OPEN, str(thread['id']),
                                   [c['content'] for c in comments]))
        return out

    # ---------------------------------------------------------------- writes

    def apply(self, pr: dict, plan: core.Plan) -> list[str]:
        """Carry out a sync plan. Returns one line per action taken."""
        number, done = pr['number'], []
        for n in plan.new:
            # A ceilinged rule reports before it may block, and an active thread blocks
            # completion under a comment-resolution policy: it lands closed, still visible.
            self._post(number, n['body'], n['path'], n['line'],
                       'closed' if n['resolve'] else 'active')
            done.append(f'posted {n["key"]}' + (' (report-only rule, closed)' if n['resolve'] else ''))
        for post, body in plan.edits:
            self._edit(number, post, body)
            done.append(f'updated {post.key}')
        for post, reply in plan.reopen:
            if post.resolved:
                self._status(number, post, 'active')
            self._reply(number, post, reply)
            done.append(f'reopened {post.key}')
        for post, reply in plan.settle:
            self._reply(number, post, reply)
            self._status(number, post, 'closed')
            done.append(f'resolved {post.key} (now a note)')
        for post, reply in plan.stale:
            self._reply(number, post, reply)
            self._status(number, post, 'fixed')
            done.append(f'fixed {post.key}')
        existing, body = plan.summary
        if existing is None:
            self._post(number, body)
            done.append('summary posted')
        elif not core.same_body(existing.body, body):
            self._edit(number, existing, body)
            done.append('summary updated')
        return done

    def _post(self, pr: int, body: str, path: str | None = None, line: int | None = None,
              status: str = 'active') -> None:
        thread = {'comments': [{'parentCommentId': 0, 'content': body, 'commentType': 'text'}],
                  'status': status}
        if path and line:
            spot = {'line': line, 'offset': 1}
            thread['threadContext'] = {'filePath': path if path.startswith('/') else f'/{path}',
                                       'rightFileStart': spot, 'rightFileEnd': spot}
        self._send('POST', f'{self._pr(pr)}/threads', thread)

    def _reply(self, pr: int, post: core.Posted, body: str) -> None:
        self._send('POST', f'{self._pr(pr)}/threads/{post.thread}/comments',
                   {'content': body, 'commentType': 'text', 'parentCommentId': int(post.id)})

    def _edit(self, pr: int, post: core.Posted, body: str) -> None:
        self._send('PATCH', f'{self._pr(pr)}/threads/{post.thread}/comments/{post.id}',
                   {'content': body})

    def _status(self, pr: int, post: core.Posted, status: str) -> None:
        updated = self._send('PATCH', f'{self._pr(pr)}/threads/{post.thread}', {'status': status})
        if not (updated or {}).get('id'):
            raise core.InspectorError(
                f'thread {post.thread} on PR {pr} was not updated — Azure DevOps accepted the '
                'PATCH and changed nothing, which means the thread does not exist.')
