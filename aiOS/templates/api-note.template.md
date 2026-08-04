# API note template

How to document a backend API in the ideaVerse. An API note is **two paired artifacts** — keep the `<name>_api` / `<name>-api` naming so they pair up (and every basename is unique across the vault):

1. **Raw clipping** (source) → `ideaVerse/atlas/apis/<name>_api.md` — the full Swagger/OpenAPI dump, verbatim, for offline fidelity.
2. **Entity note** (compiled) → `wiki/entities/<name>-api.md` — a short, queryable summary that **cites the clipping** so it stays covered.

## Steps

1. **Fetch the spec:** `curl -s <swagger-json-url> -o /tmp/<name>.json`, then sanity-check — `title`, `version`, path count, controller `tags`.
2. **Write the clipping** (§A). Build it with a shell heredoc + `cat` rather than pasting the JSON by hand.
3. **Write the entity note** (§B) — summarise; do **not** restate the whole spec. Index the endpoints and inline only the contract(s) the app actually integrates against.
4. **Add a catalog row** for the entity note (`wiki/wiki.catalog.jsonl`): `type:"entity"`, `sources:["<name>_api"]`, and rich `aliases` (service slug, key endpoint names, controller tags) so lookups hit it.
5. **Validate + coverage:** run `wiki-sync.py`. The clipping should appear under **NEW** but **never UNCOVERED** (the entity note cites it). `--update` to re-baseline only once *all* drift is reconciled — it is global and will mask unrelated drift.

---

## §A — Raw clipping → `ideaVerse/atlas/apis/<name>_api.md`

````markdown
---
title: <service> swagger api
source: <swagger-json-url>
created: {{date}}
description: Raw OpenAPI/Swagger dump of the <Service> API (served under /<basepath>, v<N>) — <controllers>. Captured {{date}}; <what the app consumes>. Summarized in the entity note (basename <name>-api).
tags:
  - clippings
  - api
  - <domain tag, e.g. tracking>
---

> Raw clipping — the exact wire contract; treat the code (DTOs/API classes) as final authority for field shapes. Refetch: `curl -s <swagger-json-url>`.

### Endpoints

#### <Tag>

| Method | Path | Summary |
|---|---|---|
| METHOD | `/api/v1/...` | <short summary> |

#### <Tag2>

| Method | Path | Summary |
|---|---|---|
| METHOD | `/api/v1/...` | <short summary> |

```json
<the full swagger JSON, verbatim>
```
````

## §B — Entity note → `wiki/entities/<name>-api.md`

````markdown
---
up: ["[[data-layer]]"]
related: ["[[<consumer concept/module>]]", "[[api-client]]"]
created: {{date}}
---

# <Service> API (entity)

<One sentence: what the API is, base path + version, who calls it (via [[api-client]]), and the auth note — e.g. the JWT it carries also identifies the caller.>

## Endpoint index (<N> paths, <M> controllers)

**`<Tag>`** (<n>) — <who/what uses it>:
- `METHOD /api/v1/.../path` — <short summary; link the consuming concept/module>.

## <key endpoint> request/response contract

<Only the contract(s) the app integrates against — not every schema. Field list with `[R]` required markers, object-vs-scalar shapes, and nullable notes. Note any gotcha the client must satisfy (e.g. a field the SDK doesn't emit natively). The clipping holds the full spec.>

> Source is a raw Swagger dump — treat the code as the final authority on field shapes; the dev-endpoint contract can change, so re-clip to refresh.

**Sources:** [<name>_api.md](../../ideaVerse/atlas/apis/<name>_api.md)
````

---

**Worked example:** [tmsmobile_api.md](../../ideaVerse/atlas/apis/tmsmobile_api.md) (clipping) + [tmsmobile-api.md](../../wiki/entities/tmsmobile-api.md) (entity).
