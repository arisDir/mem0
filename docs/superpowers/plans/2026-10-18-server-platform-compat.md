# Self-Hosted OSS Server — Platform API Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Platform-compatible API surface to the self-hosted OSS server so the official Python/TS `MemoryClient`, the `mem0` CLI, and the Vercel provider work against it unchanged, without altering the existing unversioned OSS REST API.

**Architecture:** A new `server/memplatform/` package exposes an explicit FastAPI `APIRouter` with the Platform paths (`/v1/…`, `/v2/…`, `/v3/…`), delegating to the same core calls the OSS routes use. `server/auth.py` learns to treat `Authorization: Token <key>` like `X-API-Key`. A filter-translation module and envelope helpers cover the shape differences. `server/main.py` includes the router.

**Tech Stack:** Python, FastAPI, Pydantic v2, SQLAlchemy session in `server/auth.py`; pytest + `fastapi.testclient.TestClient` for tests (new `server/tests/`).

**Spec:** `docs/superpowers/specs/2026-10-18-server-platform-compat-design.md`

## Execution Protocol

**Before executing any task, every task in this plan MUST first be written to a to-do list.** This is mandatory and applies regardless of how the work is carried out.

## Global Constraints

- Do **not** change any existing OSS route path, request model, or response shape; the unversioned API must stay identical.
- All three auth forms must resolve to the same `User` + `request.state.auth_type`: `Authorization: Bearer <jwt>`, `Authorization: Token <api-key>`, `X-API-Key: <api-key>`.
- Platform paths are versioned and trailing-slash: `/v1/ping/`, `/v3/memories/add/`, `/v3/memories/search/`, `/v3/memories/`, `/v1/memories/{memory_id}/`, `/v1/memories/{memory_id}/history/`, `/v1/entities/`, `/v2/entities/{type}/{id}/`.
- The server is synchronous: `add` returns real results, never `PENDING`.
- Unsupported Platform surfaces (exports, summary, feedback, profiles, webhooks, orgs, batch) return `501` with a `detail` naming the surface.
- `app_id` is dropped with a warning (server supports only `user_id`/`agent_id`/`run_id`).
- Tests are hermetic: fake `get_memory_instance`; no Postgres, no Ollama, no network.

## Review Focus

- **Trailing slash:** clients request `/v1/memories/{id}/` with a trailing slash; a route declared without one returns `307`. Declare the trailing-slash form and assert the client path returns `200` directly (not a redirect).
- **Failure to authenticate on compat routes:** a `Token` header an unknown scheme consumes quietly surfaces as a confusing `401`; pin `Token` acceptance with a test before wiring routes.
- **Envelope drift:** `GET /v1/entities/` must return `{"results": [...]}`, not the bare list the OSS route returns; a client calling `.results` on a list breaks.
- **Filter logical operators:** the CLI emits `{"AND": [{...}]}`; passing that through unchanged silently returns nothing from the SDK — assert the flattening.
- **Delegation correctness:** every route must call the core object with the translated filters; a route that returns `200` without calling the core is a bug the status alone hides.

---

## File Structure

**Create:**
- `server/memplatform/__init__.py` — re-exports `router`
- `server/memplatform/filters.py` — `platform_filters_to_oss`
- `server/memplatform/links.py` — `wrap_results`, `ping_payload`
- `server/memplatform/routes.py` — the compat `APIRouter`
- `server/requirements-dev.txt` — `pytest`, `pytest-mock`, `httpx`
- `server/tests/__init__.py`
- `server/tests/conftest.py` — `client`, `fake_user`, `fake_memory`, `TOKEN` fixtures
- `server/tests/test_auth_token.py`
- `server/tests/test_filters.py`
- `server/tests/test_platform_routes.py`
- `server/scripts/verify_platform_compat.py`

**Modify:**
- `server/auth.py` — add the `Token` scheme to `verify_auth`
- `server/main.py` — `app.include_router(platform_router)`
- `docs/open-source/features/rest-api.mdx` — Platform-compat section

---

## Task 1: Test harness + `Token` auth

**Files:**
- Create: `server/requirements-dev.txt`, `server/tests/__init__.py`, `server/tests/conftest.py`, `server/tests/test_auth_token.py`
- Modify: `server/auth.py`

**Interfaces:**
- Produces: `api_token_scheme = HTTPBearer(scheme_name="Token", auto_error=False)` and a new `token_credentials` parameter on `verify_auth`.
- Produces (conftest): `raw_client` fixture (a `TestClient(app)` **without** auth overrides), `client` fixture (with `verify_auth` overridden), `fake_user` fixture, `fake_memory` fixture, `TOKEN` header constant.

- [ ] **Step 1: Write the failing test**

Uses `GET /configure` (auth via `verify_auth`, needs no DB and no memory instance) to prove `Token` resolves. **Use `raw_client`, not `client`** — the `client` fixture overrides `verify_auth`, which would make this pass trivially.

```python
# server/tests/test_auth_token.py
def test_token_scheme_authenticates(raw_client, monkeypatch, fake_user):
    monkeypatch.setattr("auth._resolve_user_from_api_key", lambda key, db: fake_user)
    monkeypatch.setattr("auth.SessionLocal", _noop_session)
    resp = raw_client.get("/configure", headers={"Authorization": "Token m0sk_test"})
    assert resp.status_code == 200

def test_missing_auth_still_401(raw_client):
    assert raw_client.get("/configure").status_code == 401
```

`_noop_session` is a context-manager factory returning a dummy object (defined in `conftest.py`).

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd server && python -m pytest tests/test_auth_token.py -v`
Expected: FAIL — the first test gets `401` (`Token` is not a recognized scheme, `auto_error=False` drops it).

- [ ] **Step 3: Add the Token scheme to `verify_auth`**

In `server/auth.py`, next to `api_key_header` (line 105):

```python
api_token_scheme = HTTPBearer(scheme_name="Token", auto_error=False)
```

Add the parameter and fold it into the existing key branch:

```python
async def verify_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Depends(api_key_header),
    token_credentials: HTTPAuthorizationCredentials | None = Depends(api_token_scheme),
) -> User | None:
    ...
    effective_key = x_api_key or (token_credentials.credentials if token_credentials else None)
    if effective_key is not None:
        if ADMIN_API_KEY and secrets.compare_digest(effective_key, ADMIN_API_KEY):
            _mark_auth_type(request, "admin_api_key")
            return None
        _mark_auth_type(request, "api_key")
        with SessionLocal() as db:
            return _resolve_user_from_api_key(effective_key, db)
```

Leave the `credentials` (Bearer/JWT) branch and the `AUTH_DISABLED` branch unchanged.

- [ ] **Step 4: Set up `conftest.py`**

```python
# server/tests/conftest.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import contextlib
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from auth import verify_auth

@contextlib.contextmanager
def _noop_session():
    yield MagicMock()

@pytest.fixture()
def fake_user():
    from models import User
    u = MagicMock(spec=User)
    u.email = "admin@example.com"
    u.role = "admin"
    return u

@pytest.fixture()
def fake_memory(monkeypatch):
    from server_state import get_memory_instance as real
    m = MagicMock()
    # monkeypatch where it is looked up, not only where it is defined
    monkeypatch.setattr("server_state.get_memory_instance", lambda: m)
    return m

@pytest.fixture()
def client(fake_user):
    import main
    from auth import verify_auth as _v
    main.app.dependency_overrides[_v] = lambda: fake_user
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()

@pytest.fixture()
def raw_client():
    """No auth overrides — exercises the real verify_auth stack."""
    import main
    with TestClient(main.app) as c:
        yield c

TOKEN = {"Authorization": "Token m0sk_test"}
```

**Important:** `routes.py` (Task 3) must call `get_memory_instance()` via module attribute lookup (e.g. `from server_state import get_memory_instance` and call it) — but monkeypatching `server_state.get_memory_instance` only takes effect if `routes.py` resolves it at call time through the module. Have `routes.py` do `import server_state` and call `server_state.get_memory_instance()` so the `fake_memory` fixture works. (The existing OSS routes import the symbol directly; do not change them.)

- [ ] **Step 5: Run tests → PASS.**

Run: `cd server && python -m pytest tests/test_auth_token.py -v`

- [ ] **Step 6: Commit**

```bash
git add server/requirements-dev.txt server/tests server/auth.py
git commit -m "test(server): pytest harness and Token auth support"
```

---

## Task 2: Filter translation + envelope helpers

**Files:**
- Create: `server/memplatform/__init__.py`, `server/memplatform/filters.py`, `server/memplatform/links.py`
- Test: `server/tests/test_filters.py`

**Interfaces:**
- Produces: `platform_filters_to_oss(filters: dict | None) -> dict`; `wrap_results(items: list) -> dict`; `ping_payload(user) -> dict`.
- Note: the package is `memplatform`, **not** `platform`, to avoid shadowing the stdlib `platform` module (which `uvicorn`/`fastapi` import).

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/test_filters.py
from memplatform.filters import platform_filters_to_oss
from memplatform.links import wrap_results, ping_payload

def test_passthrough_entity_filter():
    assert platform_filters_to_oss({"user_id": "a"}) == {"user_id": "a"}

def test_none_and_empty():
    assert platform_filters_to_oss(None) == {}
    assert platform_filters_to_oss({}) == {}

def test_flatten_and():
    assert platform_filters_to_oss({"AND": [{"user_id": "a"}, {"run_id": "r"}]}) == {"user_id": "a", "run_id": "r"}

def test_unsupported_passthrough():
    f = {"categories": {"contains": "x"}}
    assert platform_filters_to_oss(f) == f

def test_app_id_dropped():
    assert platform_filters_to_oss({"user_id": "a", "app_id": "z"}) == {"user_id": "a"}

def test_wrap_and_ping(fake_user):
    assert wrap_results([1, 2]) == {"results": [1, 2]}
    assert ping_payload(fake_user) == {"org_id": None, "project_id": None, "user_email": "admin@example.com"}
```

- [ ] **Step 2: Run and confirm failure**

Run: `cd server && python -m pytest tests/test_filters.py -v` — FAIL (module missing).

- [ ] **Step 3: Implement**

`platform_filters_to_oss`: empty → `{}`; no `AND`/`OR` → shallow copy with `app_id` removed, warning logged once; `{"AND": [ {k:v}, … ]}` containing only keys in `{"user_id","agent_id","run_id","app_id"}` → flatten (drop `app_id`); anything else → return the input unchanged (log a warning).

`wrap_results(items) -> {"results": items}`.

`ping_payload(user) -> {"org_id": None, "project_id": None, "user_email": getattr(user, "email", None)}`.

`memplatform/__init__.py` exports `router` from `.routes` (added in Task 3; keep it empty until then, or guard the import).

- [ ] **Step 4: Run tests → PASS.**

- [ ] **Step 5: Commit**

```bash
git add server/memplatform server/tests/test_filters.py
git commit -m "feat(server): platform filter translation and envelope helpers"
```

---

## Task 3: Compatibility router — memory endpoints

**Files:**
- Create: `server/memplatform/routes.py`
- Modify: `server/memplatform/__init__.py`, `server/main.py`
- Test: `server/tests/test_platform_routes.py`

**Interfaces:**
- Consumes: `platform_filters_to_oss`, `wrap_results`, `ping_payload`, `server_state.get_memory_instance()` (call through the module), `auth.verify_auth`, `auth.require_admin`.
- Produces: `router: APIRouter` (full explicit paths; no prefix).

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/test_platform_routes.py
from tests.conftest import TOKEN

def test_ping(client):
    r = client.get("/v1/ping/", headers=TOKEN)
    assert r.status_code == 200 and r.json()["user_email"] == "admin@example.com"

def test_add(client, fake_memory):
    r = client.post("/v3/memories/add/", headers=TOKEN,
                    json={"messages": [{"role": "user", "content": "hi"}], "user_id": "a"})
    assert r.status_code == 200
    fake_memory.add.assert_called_once()

def test_search_translates_and(client, fake_memory):
    client.post("/v3/memories/search/", headers=TOKEN,
                json={"query": "q", "filters": {"AND": [{"user_id": "a"}]}})
    assert fake_memory.search.call_args.kwargs["filters"] == {"user_id": "a"}

def test_get_all_route(client, fake_memory):
    r = client.post("/v3/memories/", headers=TOKEN, json={"filters": {"user_id": "a"}})
    assert "results" in r.json()

def test_get_memory_trailing_slash(client, fake_memory):
    assert client.get("/v1/memories/abc/", headers=TOKEN).status_code == 200

def test_entities_wrapped(client, fake_memory):
    fake_memory.get_all.return_value = {"results": []}
    r = client.get("/v1/entities/", headers=TOKEN)
    assert isinstance(r.json()["results"], list)
```

- [ ] **Step 2: Run and confirm failure**

Run: `cd server && python -m pytest tests/test_platform_routes.py -v` — FAIL (`404`s).

- [ ] **Step 3: Implement the router**

`routes.py` uses `import server_state` and calls `server_state.get_memory_instance()` at request time (so the test fake works). Routes (trailing slash explicit):

| Method + path | Core call |
|---|---|
| `GET /v1/ping/` | return `ping_payload(_auth)` |
| `POST /v3/memories/add/` | `server_state.get_memory_instance().add(**body)` |
| `POST /v3/memories/search/` | `.search(query=body.query, filters=platform_filters_to_oss(body.filters), **params)` |
| `POST /v3/memories/` | `.get_all(filters=platform_filters_to_oss(body.filters), **params)` |
| `GET /v1/memories/{memory_id}/` | `.get(memory_id)` |
| `PUT /v1/memories/{memory_id}/` | `.update(memory_id, text=…, metadata=…, expiration_date=…)` |
| `DELETE /v1/memories/{memory_id}/` | `.delete(memory_id)` |
| `DELETE /v1/memories/` | `.delete_all(**entities)` with `_auth=Depends(require_admin)` |
| `GET /v1/memories/{memory_id}/history/` | `.history(memory_id)` |
| `GET /v1/entities/` | `wrap_results(<entities list from routers.entities logic>)` |

Wrap each core call in the same `try/except` → `upstream_error()` used by `server/main.py`, and map `ValueError` → `400` (`_client_error` pattern). Define local Pydantic request models mirroring `MemoryCreate`/`MemoryUpdate`/`SearchRequest` but tolerating extra fields (Platform payloads carry `source`, `immutable`, `custom_instructions`, …).

- [ ] **Step 2b: Include the router in `main.py`**

Add beside the existing `include_router` lines (main.py:184-187):

```python
from memplatform.routes import router as platform_router
app.include_router(platform_router)
```

- [ ] **Step 3: Run tests → PASS.**

Run: `cd server && python -m pytest tests/ -v`

- [ ] **Step 4: Commit**

```bash
git add server/memplatform server/main.py server/tests/test_platform_routes.py
git commit -m "feat(server): platform-compatible /v1,/v3 memory routes"
```

---

## Task 4: Compatibility router — entities delete, events, and 501 stubs

**Files:**
- Modify: `server/memplatform/routes.py`
- Test: `server/tests/test_platform_routes.py`

**Interfaces:**
- Produces: `DELETE /v2/entities/{entity_type}/{entity_id}/`; `GET /v1/events/`; `GET /v1/event/{event_id}/`; `501` stubs for `POST /v1/exports/`, `POST /v1/exports/get/`, `POST /v1/summary/`, `POST /v1/feedback/`, `GET /v2/entities/user/{id}/profile/`, `PUT|DELETE /v1/batch/`, `GET|POST /api/v1/orgs/...`, `GET|POST|PUT|DELETE /api/v1/webhooks/...`.

- [ ] **Step 1: Write the failing tests**

```python
def test_delete_entity(client, fake_memory):
    r = client.delete("/v2/entities/user/alice/", headers=TOKEN)
    assert r.status_code == 200

def test_unsupported_summary_501(client):
    r = client.post("/v1/summary/", headers=TOKEN, json={"filters": {"user_id": "a"}})
    assert r.status_code == 501 and "summary" in r.json()["detail"].lower()

def test_unsupported_batch_501(client):
    assert client.put("/v1/batch/", headers=TOKEN, json={"memories": []}).status_code == 501
```

- [ ] **Step 2: Run → FAIL (404s).**

- [ ] **Step 3: Implement**

Delegate `DELETE /v2/entities/{type}/{id}/` to the same core call `routers/entities.py` uses (`get_memory_instance().delete_all(**{field: id})`). Map `GET /v1/events/` and `/v1/event/{id}/` to the `requests` router data **if** the shapes align (check `routers/requests.py`); otherwise register them as `501`. Add a shared `def _unsupported(surface: str) -> HTTPException: return HTTPException(501, detail=f"The '{surface}' endpoint is not available on the self-hosted OSS server.")` and register one route per unsupported path.

- [ ] **Step 4: Run tests → PASS.**

- [ ] **Step 5: Commit**

```bash
git add server/memplatform/routes.py server/tests/test_platform_routes.py
git commit -m "feat(server): platform entities/events routes and 501 stubs"
```

---

## Task 5: Docs — Platform compatibility section

**Files:**
- Modify: `docs/open-source/features/rest-api.mdx`

- [ ] **Step 1:** Replace the flat warning at line 21 ("the OSS server does not use the `/v1/` prefix") with: the native API is unversioned, **and** a Platform-compatibility surface (`/v1`, `/v2`, `/v3` + `Authorization: Token`) exists so the official clients work.
- [ ] **Step 2:** Add a supported-routes table (Task 3 + 4) and the `501` unsupported list.
- [ ] **Step 3:** Note `app_id` unsupported, `add` synchronous, single-tenant (`org_id`/`project_id` null).
- [ ] **Step 4:** Commit

```bash
git add docs/open-source/features/rest-api.mdx
git commit -m "docs: document platform compatibility on the OSS server"
```

---

## Task 6: End-to-end verification with the real clients

**Files:**
- Create: `server/scripts/verify_platform_compat.py`

**Interfaces:**
- Consumes: a running server at `http://localhost:8888` and an `m0sk_…` key (env `MEM0_API_URL`, `MEM0_API_KEY`).

- [ ] **Step 1:** Bring the stack up (`cd server && make up && make wait-api`); this plan does **not** create `server/.env` — stop and ask if it is absent.
- [ ] **Step 2:** Write `verify_platform_compat.py` doing, with the real Python client:

```python
from mem0 import MemoryClient
import os
c = MemoryClient(api_key=os.environ["MEM0_API_KEY"], host=os.environ["MEM0_API_URL"])
uid = "platform-compat-smoke"
c.add([{"role": "user", "content": "I prefer aisle seats"}], user_id=uid)
hits = c.search("seat preference", filters={"user_id": uid})["results"]
assert any("aisle" in h.get("memory", "") for h in hits), hits
c.delete_all(user_id=uid)
print("python client OK")
```

- [ ] **Step 3:** TypeScript smoke: `new MemoryClient({ apiKey, host })` → same add/search (a `node -e` one-liner or a temp script under `/tmp`).
- [ ] **Step 4:** CLI smoke: `mem0 config set platform.base_url "$MEM0_API_URL"` then `mem0 add "..."`, `mem0 search "..."`, `mem0 list`.
- [ ] **Step 5:** Commit the script and record the observed results in the commit body.

```bash
git add server/scripts/verify_platform_compat.py
git commit -m "test(server): end-to-end platform-compat verification"
```

---

## Self-Review

- **Spec coverage:** auth (T1), filter translation + envelopes (T2), memory routes (T3), entities/events + 501 (T4), docs (T5), E2E (T6). Nothing touches `mem0/`, `mem0-ts/`, or `cli/`, honoring the spec's non-goal.
- **Type/name consistency:** the package is `memplatform` everywhere; `platform_filters_to_oss`, `wrap_results`, `ping_payload`, `_unsupported`, `TOKEN` are used with the same names in tests and code.
- **Review Focus → tests:** trailing slash (T3 `test_get_all_route`/`GET /v1/memories/{id}/`), Token auth (T1), entities envelope (T3), AND-flatten (T2 + T3), delegation (T3 `assert_called_once`).
- **Carried decisions:** `memplatform` name avoids the stdlib `platform` shadow; events map-or-501 is resolved by inspecting `routers/requests.py` in T4.
