---
up: []
tags: ["runbook", "api-note"]
related: ["[[api-note.template]]", "[[vault-map]]"]
created: {{date}}
updated: {{date}}
sources: []
aliases: ["API Note Runbook", "api-note"]
---

# API Note — Capture Runbook

How to document a backend API in the ideaVerse. This is the **runbook**; the output skeletons it fills live in [[api-note.template]].

An API note is **two paired artifacts** — keep the `<name>_api` / `<name>-api` naming so they pair up (and every basename is unique across the vault):

1. **Raw clipping** (source) → `ideaVerse/atlas/apis/<name>_api.md` — the full Swagger/OpenAPI dump, verbatim, for offline fidelity.
2. **Entity note** (compiled) → `wiki/entities/<name>-api.md` — a short, queryable summary that **cites the clipping** so it stays covered.

## Steps

1. **Fetch the spec:** `curl -s <swagger-json-url> -o /tmp/<name>.json`, then sanity-check — `title`, `version`, path count, controller `tags`.
2. **Write the clipping** (§A of [[api-note.template]]). Build it with a shell heredoc + `cat` rather than pasting the JSON by hand.
3. **Write the entity note** (§B of [[api-note.template]]) — summarise; do **not** restate the whole spec. Index the endpoints and inline only the contract(s) the app actually integrates against.
4. **Add a catalog row** for the entity note (`wiki/wiki.catalog.jsonl`): `type:"entity"`, `sources:["<name>_api"]`, and rich `aliases` (service slug, key endpoint names, controller tags) so lookups hit it.
5. **Validate + coverage:** run `aiOS/tools/wiki/wiki-sync.py`. The clipping should appear under **NEW** but **never UNCOVERED** (the entity note cites it). `--update` to re-baseline only once *all* drift is reconciled — it is global and will mask unrelated drift.
