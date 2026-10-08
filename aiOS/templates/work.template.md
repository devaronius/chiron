---
up: []
tags: []
related: []
created: {{date}}
updated: {{date}}
status: active
shipped:
stub:
sources: []
aliases: []
---

<!--
`status` — the effort's lifecycle at a glance. One of:
  active      — in progress; may own open_items (a stuck one is a `[status:: blocked]` item, the effort stays active)
  shipped     — scope realized in code/process and verified; a deferred follow-on phase tracked elsewhere does NOT demote it
  superseded  — rolled up into / replaced by another note (link it via up:/related: and a prose callout)
  reference   — documents/records/points rather than tracking build work (audits, meta, fulfilled external requests)
`shipped` — the date status became `shipped` (YYYY-MM-DD). The note stays whole for 14 workdays
  after it (`efforts.stubAfterWorkdays` in aios.config.json); then vault-lint reports it as due.
`stub` — set to the commit hash of the last full version once the note is distilled into atlas and
  replaced by a stub (vault-map → "Retiring a shipped effort").
There is deliberately no `blocked` status — blockedness lives on the open_item task line, not the effort. See [[open_item]].
-->

# {{Title}}

Design decisions from a session ({{date}}) for <what this effort does>. Part of <[[project]]>.

<Body: the decisions, the domain facts, the journey. Cross-reference implementing code by `path` and link related notes with [[wikilinks]].>
