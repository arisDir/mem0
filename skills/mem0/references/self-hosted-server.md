# Self-Hosted Mem0 REST Server (OSS)

The mem0 repo ships a FastAPI server plus a local dashboard in the [`server/`](https://github.com/mem0ai/mem0/tree/main/server) directory. This is a **third** way to run mem0, distinct from the hosted Platform and from the in-process OSS `Memory` class.

> **Read this before writing any client code for a self-hosted server.** The OSS server is **not** Platform-SDK-compatible: it uses **unversioned paths** (no `/v1/`, no `/v3/`) and a different auth header. `MemoryClient`, the `mem0` CLI, and the Vercel provider will fail against it with `401`/`404`.

## Three ways to run mem0

| Mode | What talks to it | Storage |
|------|------------------|---------|
| **Hosted Platform** | `MemoryClient` (Python/TS), `mem0` CLI, Vercel provider → `api.mem0.ai` (`/v1`, `/v3`) | Mem0-managed |
| **OSS in-process `Memory`** | Your app, directly (no HTTP) | Your vector DB (pgvector, Qdrant, …) |
| **OSS REST server** (this file) | Any HTTP client (`curl`, `requests`, `httpx`, `fetch`) with `X-API-Key` | Postgres + pgvector |

An app can also run the in-process `Memory` class against the **same** Postgres/pgvector the server uses ([client/python.md](../client/python.md) → Open Source / Self-Hosted), so both see the same memories. The server adds auth, API keys, a dashboard, and request logging on top.

## Run it

```bash
cd server
cp .env.example .env      # set POSTGRES_PASSWORD (required); add provider keys or point at Ollama
make bootstrap            # starts Compose, waits for API + dashboard, creates admin, issues first API key
```

- API: `http://localhost:8888`  · Dashboard: `http://localhost:3000`  · Postgres: internal `5432`, host `8432`
- Generated credentials print once in the `=== Ready ===` block; the API key cannot be recovered afterwards.
- Machine-readable bootstrap: `make seed EMAIL=... PASSWORD=... NAME=... OUTPUT=json` (or `OUTPUT=json make seed`).
- Health: `make health` (needs `.env`), or `curl -s localhost:8888/docs` and `curl -s localhost:8888/auth/setup-status`.
- Stop: `make down`. Wipe all data: `make clean`.

Minimum `.env`: `POSTGRES_PASSWORD` is required. LLM/embedder come from `OPENAI_API_KEY`, or from Ollama via `OLLAMA_BASE_URL` + `MEM0_DEFAULT_*_MODEL` (see [`SELF_HOSTED_OLLAMA_GUIDE.md`](../../../SELF_HOSTED_OLLAMA_GUIDE.md) for a fully local Ollama setup).

## Authentication

| Mode | Header |
|------|--------|
| Per-user API key (issued by the dashboard) | `X-API-Key: m0sk_...` |
| Dashboard session JWT (`POST /auth/login`) | `Authorization: Bearer <jwt>` |
| Legacy admin key (`ADMIN_API_KEY` env) | `X-API-Key: <ADMIN_API_KEY value>` |
| Auth disabled (`AUTH_DISABLED=true`) | none |

`GET /`, `GET /docs`, and `GET /openapi.json` are always open. Everything else is protected when auth is on.

> Setting `MEM0_API_KEY=m0sk_...` does **not** make `MemoryClient` work here. `MemoryClient` sends `Authorization: Token <key>` to `/v1|/v3` paths.

## Endpoints (unversioned)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/memories` | Add memories from messages (synchronous) |
| `GET` | `/memories` | List memories (filter by `user_id` etc.) |
| `GET` | `/memories/{memory_id}` | Get one memory |
| `PUT` | `/memories/{memory_id}` | Update text/metadata |
| `DELETE` | `/memories/{memory_id}` | Delete one memory |
| `DELETE` | `/memories` | Delete all (scoped by entity) |
| `GET` | `/memories/{memory_id}/history` | Change history |
| `POST` | `/search` | Semantic search; `"rerank": true` opts into reranking |
| `POST` | `/reset` | Wipe all memories |
| `GET`/`POST` | `/configure` | Read/write runtime mem0 config |
| `GET` | `/configure/providers` | Bundled LLM/embedder providers |
| `POST` | `/generate-instructions` | Draft custom extraction instructions |
| `GET`/`POST` | `/api-keys` | List / create API keys |
| `DELETE` | `/api-keys/{key_id}` | Revoke a key |
| `GET` | `/entities` | List users/agents/runs with memory counts |
| `DELETE` | `/entities/{entity_type}/{entity_id}` | Delete an entity and its memories |
| `GET` | `/requests` | Request log |
| `POST` | `/auth/register`, `/auth/login`, `/auth/refresh` | Session management |
| `GET` | `/auth/setup-status` | Whether the first admin exists (`{"needsSetup": bool}`) |

Interactive schema: `http://localhost:8888/docs`.

## Verified examples

```bash
API_KEY=m0sk_...
BASE=http://localhost:8888

# Add (synchronous — returns results immediately, unlike the Platform's PENDING event)
curl -s -X POST $BASE/memories \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"I am allergic to peanuts"}],"user_id":"alice"}'
# -> {"results":[{"id":"...","memory":"User is allergic to peanuts","event":"ADD"}]}

# Search, with reranking
curl -s -X POST $BASE/search \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"what should I avoid eating?","filters":{"user_id":"alice"},"rerank":true}'
# -> {"results":[{"id":"...","memory":"...","score":0.23,"rerank_score":0.5,...}]}

# List
curl -s "$BASE/memories?user_id=alice" -H "X-API-Key: $API_KEY"
```

Python (no SDK needed):

```python
import requests

BASE, KEY = "http://localhost:8888", "m0sk_..."
h = {"X-API-Key": KEY, "Content-Type": "application/json"}

requests.post(f"{BASE}/memories", headers=h, json={
    "messages": [{"role": "user", "content": "I am allergic to peanuts"}],
    "user_id": "alice",
}).json()  # {"results": [{"id", "memory", "event"}]}

requests.post(f"{BASE}/search", headers=h, json={
    "query": "what should I avoid eating?", "filters": {"user_id": "alice"}, "rerank": True,
}).json()  # {"results": [{... "score", "rerank_score"}]}
```

TypeScript:

```typescript
const BASE = "http://localhost:8888";
const h = { "X-API-Key": "m0sk_...", "Content-Type": "application/json" };

await fetch(`${BASE}/memories`, {
  method: "POST", headers: h,
  body: JSON.stringify({ messages: [{ role: "user", content: "I like hiking" }], user_id: "alice" }),
});
```

## Getting an API key

- Printed once by `make bootstrap` / `make seed ... OUTPUT=json`.
- Dashboard → **API keys** at `http://localhost:3000`.
- `POST /api-keys` with a dashboard JWT (returns the key once).

## Canonical sources

- Self-hosted setup: <https://docs.mem0.ai/open-source/setup>
- REST API + auth modes: <https://docs.mem0.ai/open-source/features/rest-api>
- Repo `server/README.md`, `server/Makefile`, and `server/openapi.json` (live at `/openapi.json`)
