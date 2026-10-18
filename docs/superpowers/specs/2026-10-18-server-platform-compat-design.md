# Self-Hosted OSS Server: Platform API Compatibility — Design

**Status:** design — awaiting review before implementation
**Date:** 2026-10-18
**Related:** `skills/mem0/references/self-hosted-server.md` (documents the current, real API)

## Problem

The hosted-Platform clients — Python `MemoryClient`, TypeScript `MemoryClient`, the `mem0` CLI, and
`@mem0/vercel-ai-provider` — cannot talk to the self-hosted OSS server in `server/`. Verified live
(2026-10-17):

| Request | Result |
|---|---|
| `X-API-Key: m0sk_…` → `GET /memories` | `200` |
| `Authorization: Token m0sk_…` → `GET /memories` | `401` |
| `Authorization: Bearer m0sk_…` → `GET /memories` | `401` |
| `X-API-Key` → `GET /v1/memories/` | `404` |
| `X-API-Key` → `POST /v3/memories/add/` | `404` |

The clients send `Authorization: Token <key>` to versioned paths (`/v1/…`, `/v3/…`); the server
uses unversioned paths and an `X-API-Key` header. `docs/open-source/features/rest-api.mdx:21` states
the OSS server deliberately does not use the `/v1/` prefix.

## Goal

Add a **Platform-compatibility surface** to the OSS server so the official Platform clients work
against it unchanged, while leaving the existing documented OSS REST API byte-for-byte identical.

## Non-goals

- No multi-tenancy / project model. The server is single-tenant; `org_id`/`project_id` are absent.
- No Platform endpoints with no OSS equivalent: exports, summary, feedback, user profiles, webhooks,
  orgs/projects, batch. These return `501` with a clear `detail` (or `404` if the client tolerates
  it) — documented as unsupported.
- No `app_id` scoping — the server's `MemoryCreate` and entities model only support
  `user_id` / `agent_id` / `run_id`.
- No async `add` semantics — the server's add is synchronous. The compat route returns the
  synchronous result; no `PENDING` event polling.
- No change to the Python/TS SDK, the CLI, or the Vercel provider.
- No change to the existing OSS routes' paths, request models, or response shapes.

## Approach (chosen)

An **explicit compatibility router** (`server/platform/`), not a path-rewrite middleware.

Rationale: most endpoints differ only by prefix, but several need different semantics or shapes —
`POST /v3/memories/` is a *list* (the OSS route is `GET /memories`), `GET /v1/entities/` must wrap a
list in `{"results": …}`, `POST /v3/memories/add/` splits add from list, and filter dicts differ.
A middleware would have to encode all of that as invisible rewriting; an explicit router is
readable, independently testable with FastAPI `TestClient`, and cannot regress the OSS API.

```
server/
  platform/
    __init__.py          # exports `platform_router`
    routes.py            # APIRouter with explicit /v1,/v2,/v3 paths, delegating to get_memory_instance()
    filters.py           # platform_filters_to_oss(filters) -> dict
    links.py             # envelope helpers (wrap_list, ping_payload)
```

`server/main.py` gains one line: `app.include_router(platform_router.router)` next to the existing
router includes (`main.py:184-187`).

## Auth

Extend the existing auth dependency so `Authorization: Token <key>` resolves exactly like
`X-API-Key` (`server/auth.py`). Today `server/auth.py` reads `X-API-Key` (line 105) and
`Authorization: Bearer <JWT>`; add a `Token` scheme that maps to the same per-user key lookup
(`_resolve_user_from_api_key`, auth.py:126) and the legacy `ADMIN_API_KEY`.

- `Authorization: Token m0sk_…` → resolve as API key.
- `Authorization: Bearer <jwt>` → unchanged (dashboard JWT).
- `X-API-Key: …` → unchanged.
- All three land on the same `User` + `auth_type` request state.

Because `models.py:25` defaults every user's role to `admin` on this single-tenant server, keys
issued in the dashboard already satisfy `require_admin`; the compat routes can reuse the existing
`verify_auth` / `require_admin` dependencies without new authorization logic.

## Endpoint mapping

`platform_router` declares the Platform paths; each delegates to the same core call the OSS route
uses.

| Platform path (client) | Delegates to | Notes |
|---|---|---|
| `GET /v1/ping/` | new `ping_payload()` | `{"org_id": null, "project_id": null, "user_email": <email>}`; 200 for any valid key |
| `POST /v3/memories/add/` | `get_memory_instance().add(...)` | body `{messages, user_id, agent_id, run_id, metadata, infer, …}`; returns the synchronous `{"results": [...]}` |
| `POST /v3/memories/search/` | `.search(query=..., filters=..., **params)` | filter translation (below) |
| `POST /v3/memories/` | `.get_all(filters=..., **params)` | **list**; returns `{"results": [...]}` |
| `GET /v1/memories/{id}/` | `.get(id)` | |
| `PUT /v1/memories/{id}/` | `.update(id, text=..., metadata=...)` | |
| `DELETE /v1/memories/{id}/` | `.delete(id)` | |
| `DELETE /v1/memories/` | `.delete_all(**entities)` | `require_admin`; every user is admin here |
| `GET /v1/memories/{id}/history/` | `.history(id)` | |
| `GET /v1/entities/` | `list_entities()` (routers/entities.py) | wrap list → `{"results": [...]}` |
| `DELETE /v2/entities/{type}/{id}/` | entities delete | type ∈ user/agent/run |
| `GET /v1/events/`, `GET /v1/event/{id}/` | requests router (best effort) | CLI `mem0 event`; map if the shapes align, else `501` |

Trailing slashes are declared explicitly (FastAPI `redirect_slashes` gives 307 by default; the merge
path should accept both by declaring the canonical trailing-slash route).

Trailing-slash + prefix specifics: the clients request `/v1/memories/{id}/` etc. with a **trailing
slash**. Declare the trailing-slash form and let FastAPI's default redirect handle the unslashed
form.

## Filter translation

Platform clients send `filters` as a dict that may contain logical operators (the CLI builds
`{"AND": [{"user_id": "x"}, …]}` via `_build_filters`, platform.py:134). The OSS server's
`SearchRequest.filters` is passed straight into the SDK, which expects the entity keys.

`platform_filters_to_oss(filters) -> dict`:

1. If `filters` is empty/None → `{}`.
2. If it contains no `AND`/`OR`, pass through unchanged (already `{"user_id": …}` form).
3. If it is `{"AND": [ {k: v}, … ]}` with only entity keys (`user_id`, `agent_id`, `run_id`,
   `app_id`) → flatten to `{k: v}`.
4. Otherwise (logical, range, or category filters the OSS server cannot express) → pass through
   unchanged and let the SDK handle or reject; log a warning.

`app_id` is dropped (server has no `app_id`), with a warning.

## Response shapes

The clients read `response.json()` and mostly look for `results`. The OSS routes already return
`{"results": [...]}` for add/search/get_all. Differences handled in the compat router:

- `GET /v1/entities/` — OSS returns a bare list; compat wraps it as `{"results": [...]}`.
- `GET /v1/ping/` — new.
- Errors — reuse the server's existing `{"detail": …}` (FastAPI default); the clients read `detail`
  on error (Python `_validate_api_key`, CLI `_request`), so this already matches.

## Error handling

- Unknown Platform endpoint (exports, summary, feedback, profiles, webhooks, orgs, batch) → `501`
  with `detail` naming the unsupported surface.
- Invalid key on any compat route → `401` `{"detail": "Authentication required…"}` (unchanged).
- `delete_all` without any entity id → `400` (unchanged server behavior).
- Upstream SDK errors → the existing `upstream_error()` mapper.

## Testing

The `server/` tree has **no test suite today** (`find server -name 'test_*.py'` → none; no pytest in
`server/requirements.txt`). Add `server/tests/` with pytest + `fastapi.testclient.TestClient`,
monkeypatching `server_state.get_memory_instance` with a fake so no Postgres/LLM is needed.

Cases:
- Auth: `Token`, `X-API-Key`, and `Bearer` all authenticate; bad key → `401`.
- Each mapped route returns the expected status + envelope, and **delegates to the right core call**
  (assert the fake was called with translated filters/params).
- `platform_filters_to_oss`: passthrough, AND-flatten, unsupported passthrough, `app_id` drop.
- `GET /v1/entities/` → `{"results": [...]}` (not a bare list).
- `GET /v1/ping/` → 200 with `user_email`.
- Unsupported platforms endpoints → `501`.
- Regression: the existing unversioned routes keep their current shapes (same fake).

End-to-end (manual / scripted, against a running stack — see the parent spec's rollout):
1. Python: `MemoryClient(api_key=<m0sk>, host="http://localhost:8888")` → `add`, `search`,
   `get_all`, `delete`.
2. TypeScript: `new MemoryClient({ apiKey, host })` → add/search.
3. CLI: `mem0 config set platform.base_url http://localhost:8888` + `mem0 add/search/list`.

## Documentation

- `docs/open-source/features/rest-api.mdx` — replace the flat "does not use `/v1/`" warning
  (line 21) with: the native OSS API is unversioned, **and** a Platform-compatibility surface
  (`/v1`, `/v2`, `/v3` + `Authorization: Token`) is available so the official clients work.
- Add a "Platform compatibility" section listing supported routes and the unsupported (`501`) ones.
- Update `skills/mem0/references/self-hosted-server.md` once the surface ships (it currently says
  the SDKs "do not work" — that stays true until this lands).

## Decisions log

- **Explicit router over middleware** — several routes need different semantics/shapes; explicit is
  testable and non-regressive.
- **`Token` accepted alongside `X-API-Key`** — least-surprise for Platform clients; reuses the same
  key resolution.
- **Sync add** — the server is synchronous; no fake `PENDING` event loop is introduced.
- **`app_id` unsupported** — the server model has no `app_id`; documented, warned, dropped.
- **No SDK/CLI/provider changes** — the whole point is to accept them as-is.
- **New `server/tests/`** — the server had no tests; the compat surface needs them, and the fake
  `get_memory_instance` keeps them hermetic.
