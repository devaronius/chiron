---
up: []
related: []
created: {{date}}
---

# {{PROJECT_NAME}} — Wiki Index

The compiled, concept-organized wiki for {{PROJECT_NAME}}. Notes are short, single-purpose, and source-traceable (each links the raw vault note it was compiled from). **Source content is never overwritten** — this wiki only summarizes it.

## How to query

1. **Grep the catalog first** — [`wiki.catalog.jsonl`](wiki.catalog.jsonl), one JSON object per note, before opening broad context. Schema:
   `{id, type, path, title, desc, sources[], related[], aliases[]}` where `type ∈ {concept, topic, entity, project}`.
   Examples: `grep '"type":"concept"' wiki.catalog.jsonl` · `grep <term> wiki.catalog.jsonl`.
2. **Start from a topic hub** below, then follow `[[wikilinks]]` to the specific note.
3. Open the linked vault source only when you need the full detail.

## Topics (hubs)

_None yet — add topic hubs as the wiki grows._

## Concepts

- [[open-item]] — the owned-once, viewed-everywhere unit of tracked work, and the lanes its `assignee::` routes it to.

## Entities

_None yet._

## Projects

_None yet._

## Cross-source discrepancies

_None recorded. When a source contradicts the code or another source, flag it here (the code is the final authority)._
