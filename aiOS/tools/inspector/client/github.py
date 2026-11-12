"""
github — the inspector client's GitHub adapter. It fetches and it posts; `core` decides.

Everything goes through `gh` and nowhere else, so the identity is whatever `gh` is logged
in as — a bot account later is a different `GH_TOKEN`, not a code change.

**No code path can cast a vote.** A GitHub review carries an event, and `APPROVE` or
`REQUEST_CHANGES` is a vote; the event here is the constant `REVIEW_EVENT`, never a
parameter, so no caller can pass another one.
"""
from __future__ import annotations

import json
import re
import subprocess

from . import core

REVIEW_EVENT = 'COMMENT'

HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
CLOSES = re.compile(r'\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)', re.IGNORECASE)

THREADS_QUERY = '''
query($owner: String!, $name: String!, $pr: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { id isResolved comments(first: 100) { nodes { databaseId body } } }
      }
    }
  }
}'''

RESOLVE = 'mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id } } }'
UNRESOLVE = ('mutation($id: ID!) { unresolveReviewThread(input: {threadId: $id}) '
             '{ thread { id } } }')


def _gh(args: list[str], stdin: str | None = None) -> str:
    done = subprocess.run(['gh', *args], input=stdin, capture_output=True, text=True)
    if done.returncode != 0:
        raise core.InspectorError(f'gh {" ".join(args[:3])} failed: {done.stderr.strip()}')
    return done.stdout


def commentable_lines(diff: str) -> dict[str, set[int]]:
    """Per path, the new-side lines a review comment may anchor to: added and context."""
    out: dict[str, set[int]] = {}
    path, line = None, 0
    for raw in diff.splitlines():
        if raw.startswith('+++ '):
            path = raw[6:] if raw.startswith('+++ b/') else None
            if path:
                out.setdefault(path, set())
            continue
        hunk = HUNK.match(raw)
        if hunk:
            line = int(hunk.group(1))
            continue
        if path is None or raw.startswith(('--- ', 'diff ', 'index ', '\\')):
            continue
        if raw.startswith('+') or raw.startswith(' '):
            out[path].add(line)
            line += 1
    return out


def build_state(runs: list[dict]) -> str:
    """One word for a head commit's check runs: none, queued, running, approved, failed."""
    if not runs:
        return 'none'
    if any(r['status'] == 'queued' for r in runs):
        return 'queued'
    if any(r['status'] != 'completed' for r in runs):
        return 'running'
    ok = ('success', 'neutral', 'skipped')
    return 'approved' if all(r.get('conclusion') in ok for r in runs) else 'failed'


class GitHub:
    # How to link the ticket, for the `missing-work-item` problem `body` reports.
    LINK_FIX = 'Write `Closes #<ticket>`, so the PR links the ticket it answers.'

    def __init__(self, config: dict | None = None, run=_gh):
        self.run = run
        self.body_check = ((config or {}).get('agents', {}).get('inspector', {})
                           .get('bodyCheck') or '')
        self._login = self._repo = None

    def _json(self, args: list[str], stdin: str | None = None):
        return json.loads(self.run(args, stdin) or 'null')

    # ---------------------------------------------------------------- reads

    def login(self) -> str:
        if self._login is None:
            self._login = self.run(['api', 'user', '--jq', '.login']).strip()
        return self._login

    def repo(self) -> tuple[str, str]:
        if self._repo is None:
            data = self._json(['repo', 'view', '--json', 'owner,name'])
            self._repo = (data['owner']['login'], data['name'])
        return self._repo

    def pull_request(self, pr: int) -> dict:
        data = self._json(['pr', 'view', str(pr), '--json',
                           'number,title,body,state,url,author,baseRefName,headRefName,'
                           'headRefOid,closingIssuesReferences'])
        return {
            'number': data['number'], 'title': data['title'], 'body': data.get('body') or '',
            'state': data['state'], 'url': data['url'],
            'author': (data.get('author') or {}).get('login'),
            'base': data['baseRefName'], 'head': data['headRefName'],
            'head_sha': data['headRefOid'],
            # Only what the PR formally closes. A number in the title or branch may name
            # a ticket the PR merely relates to, and reviewing against it would be guessing.
            'tickets': [ref['number'] for ref in data.get('closingIssuesReferences') or []],
        }

    def ticket(self, number: int) -> dict:
        data = self._json(['issue', 'view', str(number), '--json',
                           'number,title,body,state,url,labels'])
        return {'number': data['number'], 'title': data['title'], 'state': data['state'],
                'url': data['url'], 'labels': [label['name'] for label in data.get('labels') or []],
                'body': data.get('body') or ''}

    def diff(self, pr: int, name_only: bool = False) -> str:
        return self.run(['pr', 'diff', str(pr), *(['--name-only'] if name_only else [])])

    def anchors(self, pr: int):
        lines = commentable_lines(self.diff(pr))
        return lambda path, line: line in lines.get(path, ())

    def template(self) -> str | None:
        try:
            return self.run(['api', 'repos/{owner}/{repo}/contents/.github/PULL_REQUEST_TEMPLATE.md',
                             '-H', 'Accept: application/vnd.github.raw'])
        except core.InspectorError:
            return None

    def links_ticket(self, pr: dict) -> bool:
        return bool(pr['tickets']) or bool(CLOSES.search(core.COMMENT.sub('', pr['body'])))

    def body_checked_by_ci(self, pr: dict) -> bool:
        """Whether the configured `bodyCheck` ran on the head and already judged headings."""
        return bool(self.body_check) and any(
            r['name'] == self.body_check for r in self.check_runs(pr['head_sha']))

    def check_runs(self, sha: str) -> list[dict]:
        raw = self.run(['api', f'repos/{{owner}}/{{repo}}/commits/{sha}/check-runs',
                        '--paginate', '--jq', '.check_runs[] | {name, status, conclusion}'])
        return [json.loads(line) for line in raw.splitlines() if line.strip()]

    def build(self, pr: dict) -> dict:
        runs = self.check_runs(pr['head_sha'])
        # Asked for by the head SHA, so every run returned is current by construction; a
        # head with no runs yet is `none`, never approved.
        return {'head': pr['head_sha'], 'state': build_state(runs), 'current': bool(runs),
                'checks': runs}

    def worktree_hint(self, pr: dict) -> str:
        return (f'git fetch origin pull/{pr["number"]}/head && '
                f'git worktree add <scratchpad>/wt {pr["head_sha"][:12]}')

    def _threads(self, pr: int) -> dict[int, tuple[str, bool, list[str]]]:
        """First comment id → (thread node id, resolved?, every comment body in order)."""
        owner, name = self.repo()
        out, after = {}, None
        while True:
            args = ['api', 'graphql', '-f', f'query={THREADS_QUERY}', '-f', f'owner={owner}',
                    '-f', f'name={name}', '-F', f'pr={pr}']
            if after:
                args += ['-f', f'after={after}']
            page = self._json(args)['data']['repository']['pullRequest']['reviewThreads']
            for node in page['nodes']:
                comments = node['comments']['nodes']
                if comments:
                    out[comments[0]['databaseId']] = (node['id'], node['isResolved'],
                                                      [c['body'] for c in comments])
            if not page['pageInfo']['hasNextPage']:
                return out
            after = page['pageInfo']['endCursor']

    def _lines(self, path: str) -> list[dict]:
        raw = self.run(['api', path, '--paginate', '--jq', '.[] | {id, body, user: .user.login}'])
        return [json.loads(line) for line in raw.splitlines() if line.strip()]

    def mine(self, pr: int) -> list[core.Posted]:
        """Our own posts on the PR: carrying our key, and authored by the current login.

        The key alone is not ownership — another account's inspector run plants the
        same marker. Its posts are left standing beside ours.
        """
        me, out = self.login(), []
        threads = self._threads(pr)
        for c in self._lines(f'repos/{{owner}}/{{repo}}/pulls/{pr}/comments'):
            key = core.key_of(c['body'])
            if key and c['user'] == me and c['id'] in threads:
                thread, resolved, comments = threads[c['id']]
                out.append(core.Posted(key, str(c['id']), c['body'], True, resolved, thread,
                                       comments))
        for c in self._lines(f'repos/{{owner}}/{{repo}}/issues/{pr}/comments'):
            key = core.key_of(c['body'])
            if key and c['user'] == me:
                out.append(core.Posted(key, str(c['id']), c['body'], False))
        return out

    # ---------------------------------------------------------------- writes

    def apply(self, pr: dict, plan: core.Plan) -> list[str]:
        """Carry out a sync plan. Returns one line per action taken."""
        number, done = pr['number'], []
        if plan.new:
            review = {
                'commit_id': pr['head_sha'],
                'event': REVIEW_EVENT,
                'body': f'{len(plan.new)} new finding(s); the summary is in the '
                        f'conversation.\n\n{core.signature(self.login())}',
                'comments': [{'path': n['path'], 'line': n['line'], 'side': 'RIGHT',
                              'body': n['body']} for n in plan.new],
            }
            self.run(['api', '--method', 'POST', f'repos/{{owner}}/{{repo}}/pulls/{number}/reviews',
                      '--input', '-'], json.dumps(review))
            done += [f'posted {n["key"]}' for n in plan.new]
            ceilinged = {n['key'] for n in plan.new if n['resolve']}
            if ceilinged:
                for post in self.mine(number):
                    if post.key in ceilinged and post.thread and not post.resolved:
                        self._resolve(post.thread)
                        done.append(f'resolved {post.key} (report-only rule)')
        for post, body in plan.edits:
            self._edit(post, body)
            done.append(f'updated {post.key}')
        for post, reply in plan.reopen:
            if post.resolved:
                self.run(['api', 'graphql', '-f', f'query={UNRESOLVE}', '-f',
                          f'id={post.thread}'])
            self._reply(number, post, reply)
            done.append(f'reopened {post.key}')
        for post, reply in plan.settle:
            self._reply(number, post, reply)
            self._resolve(post.thread)
            done.append(f'resolved {post.key} (now a note)')
        for post, reply in plan.stale:
            self._reply(number, post, reply)
            self._resolve(post.thread)
            done.append(f'fixed {post.key}')
        existing, body = plan.summary
        if existing is None:
            self.run(['api', '--method', 'POST',
                      f'repos/{{owner}}/{{repo}}/issues/{number}/comments', '-f', f'body={body}'])
            done.append('summary posted')
        elif not core.same_body(existing.body, body):
            self._edit(existing, body)
            done.append('summary updated')
        return done

    def _reply(self, pr: int, post: core.Posted, body: str) -> None:
        self.run(['api', '--method', 'POST',
                  f'repos/{{owner}}/{{repo}}/pulls/{pr}/comments/{post.id}/replies',
                  '-f', f'body={body}'])

    def _edit(self, post: core.Posted, body: str) -> None:
        kind = 'pulls' if post.anchored else 'issues'
        self.run(['api', '--method', 'PATCH', f'repos/{{owner}}/{{repo}}/{kind}/comments/{post.id}',
                  '-f', f'body={body}'])

    def _resolve(self, thread: str) -> None:
        self.run(['api', 'graphql', '-f', f'query={RESOLVE}', '-f', f'id={thread}'])
