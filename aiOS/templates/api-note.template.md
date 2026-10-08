# API note template

The two output skeletons for an API note. The procedure that fills them is [[api-note.runbook]] — read it first; this file is skeletons only.

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
