# Self-hosted Mem0 server on local Ollama (LLM + embedder + reranker)

Date: 2026-10-16

## Problem

Stand up the self-hosted Mem0 server (`server/`, Docker Compose) so that it runs
entirely on a local Ollama instance, using:

- **LLM:** `gemma4:e4b32k`
- **Embedder:** `nomic-embed-text-v2-moe`
- **Reranker:** `dengcao/Qwen3-Reranker-8B` (Ollama tag `dengcao/Qwen3-Reranker-8B:Q5_K_M`)

Out of the box the server only bundles `openai`, `anthropic`, `gemini` for LLM and
`openai`, `gemini` for embedder. Ollama is rejected by
`_validate_bundled_providers` (`server/main.py:232`). The SDK supports Ollama for
the LLM and embedder, and has an LLM-backed reranker, but there is **no Ollama
reranker provider**, and the LLM reranker's numeric-score prompt does not fit a
sequence-scoring model like Qwen3-Reranker.

## Goals

1. Server runs on the local Ollama daemon for LLM, embedding, and reranking.
2. Reranking is implemented as a first-class SDK reranker provider (`ollama`),
   reusable outside the server and consistent with existing provider patterns.
3. Reranking is opt-in per `POST /search` request.
4. Local SDK source is live in the dev container so new provider code takes effect.

## Non-goals

- No native TypeScript SDK reranker parity (Python only).
- No changes to `docker-compose` production/prod image beyond what the dev server needs.
- No handling of the hosted (`MemoryClient`) path.

## Verified context

- Ollama listens on `0.0.0.0:11434` (`OLLAMA_HOST=0.0.0.0:11434`), so it is
  reachable from a container via `host.docker.internal` (`host-gateway`).
- Models present on host: `gemma4:e4b32k`, `nomic-embed-text-v2-moe:latest`,
  `dengcao/Qwen3-Reranker-8B:Q5_K_M`.
- `nomic-embed-text-v2-moe` output dimension is **768**.
- The Qwen3-Reranker GGUF returns `logprobs` through `/api/generate`, and emits a
  ` thinking…yes/no…` sequence. Ollama server is `0.30.10`.
- `ollama-python` gained `logprobs`/`top_logprobs` support recently; latest is
  `0.6.3`. We require `ollama>=0.6.3`.
- `PgvectorConfig.embedding_model_dims` defaults to **1536**
  (`mem0/configs/vector_stores/pgvector.py:9`). It is not inferred from the
  embedder, so it must be set explicitly to 768.
- The dev Compose bind is `server/ → /app`, and its startup command runs
  `pip install --force-reinstall --no-deps mem0ai`, so the repo's `mem0/` is
  **not** mounted and local SDK edits are **not** live today.
- `RerankerFactory` (`mem0/utils/factory.py:226`) resolves
  `config.reranker.provider` + `config.reranker.config`, wraps a dict config into
  the registered config class (`factory.py:270`), and instantiates the provider.
- `Memory.search(..., rerank: bool = False)` applies the configured reranker only
  when `rerank=True` and preserves original results if reranking raises
  (`mem0/memory/main.py:1513`).

## Architecture

### New SDK provider

| File | Purpose |
|------|---------|
| `mem0/configs/rerankers/ollama.py` | `OllamaRerankerConfig(BaseRerankerConfig)` |
| `mem0/reranker/ollama_reranker.py` | `OllamaReranker(BaseReranker)` |
| `mem0/utils/factory.py` | register `"ollama"` in `RerankerFactory.provider_to_class` + import config |
| `mem0/reranker/__init__.py` | export `OllamaReranker` |

`OllamaRerankerConfig` fields (inherits `provider`, `model`, `api_key`, `top_k`
from `BaseRerankerConfig`):

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `model` | `str` | required | e.g. `dengcao/Qwen3-Reranker-8B:Q5_K_M` |
| `ollama_base_url` | `Optional[str]` | `None` | `None` → Ollama client default (`http://localhost:11434`); server sets `http://host.docker.internal:11434` |
| `temperature` | `float` | `0.0` | deterministic scoring |
| `max_tokens` | `int` | `8` | generation cap |
| `top_logprobs` | `int` | `20` | candidates returned per position |
| `system_prompt` | `Optional[str]` | `None` | override default yes/no instruction |
| `top_k` | `Optional[int]` | `None` | inherited; max docs returned |

`OllamaReranker.__init__` accepts a dict or a config object (mirrors
`LLMReranker`), imports `ollama`, and constructs `Client(host=ollama_base_url)`.

### Scoring data flow

`rerank(query, documents, top_k=None)`:

1. Extract per-document text: `memory` → `text` → `content` → `str(doc)`
   (same precedence as `LLMReranker`). Truncate query/document inputs to a
   fixed max length to avoid prompt flooding.
2. `_score(query, doc) -> float`:
   - Build the reranker prompt:
     - system: "Judge whether the Document meets the requirements based on the
       Query. Answer only yes or no." (overridable via `system_prompt`).
     - user: `<Query>: …\n<Document>: …`.
   - `client.generate(model, prompt, logprobs=True, top_logprobs=K, think=False,
     options={"temperature": 0.0, "num_predict": max_tokens})`.
   - Walk `response.logprobs`; find the first position whose `top_logprobs`
     (or own token) contains `yes`/`no` (case-insensitive). Compute
     `score = 1 / (1 + exp(logP_no - logP_yes))` i.e. `P(yes)/(P(yes)+P(no))`.
     - only `yes` present → `1.0`; only `no` present → `0.0`.
     - neither found → `0.5`.
   - Any exception → log a warning and return `0.5` (mirrors `LLMReranker`).
3. Copy each doc, attach `rerank_score`, sort descending, apply `top_k`
   (argument wins over `config.top_k`). Never mutate input documents.
   Note: `Memory.search` passes its own `limit` as the reranker `top_k`, so via
   `POST /search` the request's `top_k` governs; `config.top_k` only affects
   direct SDK calls to `rerank()`.

`Memory.search` already wraps the reranker call in try/except and falls back to
the original results on failure.

**Open risk:** precise extraction of the yes/no decision token from the Qwen3
GGUF (thinking wrapper, tokenization of `yes`/`no`). Mitigations: `think=False`,
a first-match scan across all positions, and a neutral `0.5` fallback. This will
be validated against the live model during implementation; the extraction helper
is isolated and unit-tested with synthetic `logprobs` payloads.

### Runtime config the server passes

```json
{
  "vector_store": {
    "provider": "pgvector",
    "config": { "...": "...", "embedding_model_dims": 768 }
  },
  "llm": {
    "provider": "ollama",
    "config": {
      "model": "gemma4:e4b32k",
      "ollama_base_url": "http://host.docker.internal:11434"
    }
  },
  "embedder": {
    "provider": "ollama",
    "config": {
      "model": "nomic-embed-text-v2-moe",
      "ollama_base_url": "http://host.docker.internal:11434"
    }
  },
  "reranker": {
    "provider": "ollama",
    "config": {
      "model": "dengcao/Qwen3-Reranker-8B:Q5_K_M",
      "ollama_base_url": "http://host.docker.internal:11434",
      "top_logprobs": 20
    }
  }
}
```

All values are sourced from env vars with these defaults, so operators can
repoint without editing code.

## Server & container changes

### `server/main.py`
- Add `"ollama"` to `BUNDLED_LLM_PROVIDERS` and `BUNDLED_EMBEDDER_PROVIDERS`.
- Read new env vars: `OLLAMA_BASE_URL`, `MEM0_DEFAULT_LLM_MODEL`,
  `MEM0_DEFAULT_EMBEDDER_MODEL`, `MEM0_DEFAULT_RERANKER_MODEL`.
- `DEFAULT_CONFIG`: llm/embedder → ollama; add `reranker`; add
  `embedding_model_dims: 768` to the vector store config.
- `SearchRequest`: add `rerank: Optional[bool] = None`.
- `search_memories` (`server/main.py:453`): pass `rerank` through when set.

### `server/requirements.txt`
- Add `ollama>=0.6.3` (logprobs + `think` support).

### `server/docker-compose.yaml` (mem0 service)
- `extra_hosts: ["host.docker.internal:host-gateway"]`.
- Environment: `OLLAMA_BASE_URL`, `MEM0_DEFAULT_LLM_MODEL`,
  `MEM0_DEFAULT_EMBEDDER_MODEL`, `MEM0_DEFAULT_RERANKER_MODEL`.

### Local SDK live in the container
- Mount the repo root (e.g. `..:/workspace`).
- Change the startup command to install the local SDK editable:
  `pip install -q --no-deps -e /workspace && alembic upgrade head && uvicorn main:app …`
  (replacing the `rm -rf /app/packages && pip install … mem0ai` line). This
  restores the hot-reload behavior `server/AGENTS.md` documents.

### `server/.env` / `.env.example`
- Create `server/.env` (gitignored) with `POSTGRES_PASSWORD`, `JWT_SECRET`,
  empty `OPENAI_API_KEY`, and the Ollama vars.
- Update `.env.example` with the Ollama vars as documented placeholders.

## Error handling

- Reranker scoring errors → warning + `0.5`; `Memory.search` keeps original order
  if the reranker raises.
- Ollama unreachable from the container → per-doc warnings + neutral scores;
  search still returns vector results.
- `rerank=true` with no reranker configured → flag is a no-op (unranked results).
- Wrong embedding dims → prevented by explicit `embedding_model_dims: 768`.

## Testing

- `tests/rerankers/test_ollama_reranker.py` (mock `ollama.Client`, never the code
  under test):
  - yes/no logprob → correct score (yes-dominant high, no-dominant low).
  - missing yes/no tokens → `0.5`.
  - generate raises → `0.5` + no crash.
  - sort descending, `top_k` limiting (arg + config), non-mutation of inputs.
  - text extraction precedence (`memory`/`text`/`content`).
- Mock fixture for the `ollama` client module added to
  `tests/rerankers/conftest.py`.
- Registration covered by existing exports/factory tests (extend if they assert
  a full provider list).
- Run `ruff check` (line length 120) and `pytest tests/rerankers/` in the mem0
  hatch env; server changes verified by bringing up the stack and exercising
  `POST /search` with `rerank: true`.

## Documentation

- New `docs/components/rerankers/models/ollama.mdx` with config table + example.
- Add the page to `docs/docs.json` navigation.
- Add an `llms.txt` entry (`[OSS]`, description starting `Use when …`); run
  `python scripts/check-llms-txt-coverage.py --write` and clean up placeholders.
- Update `docs/components/rerankers/config.mdx` provider-specific table.
- Document the `ollama>=0.6.3` requirement.

Docs are required only if this becomes a PR; local use does not depend on them.

## Rollout / verification

1. Fill `server/.env`.
2. `cd server && make up` (browser-first); confirm API + dashboard healthy.
3. Complete the setup wizard at `http://localhost:3000`.
4. `POST /memories` then `POST /search` with `rerank: true`; confirm reranked
   ordering and that scores reflect yes/no logprobs.
5. `make health` reports API, dashboard, and Postgres OK.

## Decisions log

- **Reranker implementation:** native SDK provider (Approach 1), not server-side
  or config-only. Config-only `llm_reranker` is non-viable because Qwen3-Reranker
  emits `yes`/`no`, not a `0.0–1.0` number.
- **Reranker trigger:** opt-in per request (`rerank` flag), default off.
- **Reranker model:** user-selected `dengcao/Qwen3-Reranker-8B:Q5_K_M`.
- **Ollama reachability:** host-gateway + `OLLAMA_BASE_URL`, since models live on
  the host and Ollama already binds `0.0.0.0`.
- **SDK liveness:** mount repo root and pip-install editable, because the current
  Compose shadows the SDK with a PyPI install.
