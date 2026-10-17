# Self-Hosted Mem0 with Ollama (Complete Guide)

This guide walks you through setting up Mem0's self-hosted server to run exclusively with Ollama for LLMs, embeddings, and reranking. It includes all the features added in this branch (Ollama reranker provider, server defaults, Docker Compose wiring, etc.).

## What you'll get

- **API server** at `http://localhost:8888` (FastAPI) with authentication, API keys, and the `/search` endpoint with opt-in `rerank`
- **Dashboard** at `http://localhost:3000` for setup, keys, and exploration
- **Postgres + pgvector** for vector storage (dims 768)
- **Ollama** for LLM (`gemma4:e4b32k`), embedder (`nomic-embed-text-v2-moe`), and reranker (`dengcao/Qwen3-Reranker-8B:Q5_K_M`)

## Prerequisites

- [Ollama](https://ollama.com/download) installed and running on your host
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) (v2)
- Python 3.9–3.12 if you want to use the Python SDK locally
- `git`, `curl`, `openssl` (commonly available)

## 1) Check out the branch

Clone the repo and switch to this branch (or if you already have it):

```bash
git clone https://github.com/mem0ai/mem0.git
cd mem0
git checkout feat/ollama-self-hosted-server
```

All changes for Ollama self-hosting live in this branch.

## 2) Pull required Ollama models

The server defaults expect these models. Pull them now:

```bash
ollama pull gemma4:e4b32k
ollama pull nomic-embed-text-v2-moe:latest
ollama pull dengcao/Qwen3-Reranker-8B:Q5_K_M
```

Verify they are available:

```bash
ollama list
# or
curl -s http://localhost:11434/api/tags | jq '.models[].name'
```

## 3) Configure environment

Navigate to the server directory:

```bash
cd server
```

Create `.env` (gitignored). The easiest way is to copy `.env.example` and fill secrets, or generate them:

```bash
# Generate secure secrets
PG_PW=$(openssl rand -hex 24)
JWT=$(openssl rand -base64 48 | tr -d '\n')
cat > .env <<EOF
OPENAI_API_KEY=
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=${PG_PW}
POSTGRES_COLLECTION_NAME=memories
ADMIN_API_KEY=
JWT_SECRET=${JWT}
AUTH_DISABLED=false
DASHBOARD_URL=http://localhost:3000
APP_DB_NAME=mem0_app
MEM0_TELEMETRY=false
OLLAMA_BASE_URL=http://host.docker.internal:11434
MEM0_DEFAULT_LLM_MODEL=gemma4:e4b32k
MEM0_DEFAULT_EMBEDDER_MODEL=nomic-embed-text-v2-moe
MEM0_DEFAULT_RERANKER_MODEL=dengcao/Qwen3-Reranker-8B:Q5_K_M
MEM0_DEFAULT_EMBEDDING_DIMS=768
EOF
```

> Notes:
> - `OLLAMA_BASE_URL=http://host.docker.internal:11434` allows the Docker container to reach Ollama running on your host (via `extra_hosts` in `docker-compose.yaml`).
> - `MEM0_DEFAULT_EMBEDDING_DIMS=768` matches `nomic-embed-text-v2-moe` output dims and pgvector config.
> - The Ollama reranker uses yes/no logprobs (`top_logprobs: 20`) for scoring.

See `.env.example` for more context.

## 4) Build and start the stack

From the `server/` directory:

```bash
make up
```

This will:
- Build the images (mem0 API + dashboard)
- Start Postgres (pgvector), Mem0 API, and dashboard
- Wait for healthchecks
- Install the local editable SDK in the container (so your local changes take effect)

You should see:

```text
Stack is ready.
  Dashboard:  http://localhost:3000  <- open this to run the setup wizard
  API:        http://localhost:8888
```

Check health:

```bash
make health
# API: 200, Dashboard: 200, Postgres: ok
```

## 5) Complete setup and get an API key

1. Open `http://localhost:3000` and complete the setup wizard (create admin account).
2. Once logged in, go to **API Keys** and create a key. Copy it.

## 6) Smoke test (CLI/curl)

Test the API with reranking enabled:

```bash
API_KEY="your_api_key_here"

# Add a memory
curl -s -X POST http://localhost:8888/memories \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"I am allergic to peanuts"}],"user_id":"demo"}'

# Search with rerank
curl -s -X POST http://localhost:8888/search \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"what should I avoid eating?","filters":{"user_id":"demo"},"rerank":true}'
```

You should see results with a `rerank_score`. Values may be `0.5` depending on the model confidence for short inputs — this is expected behavior (fallback), not a regression. The important thing is `rerank` is accepted and scores are returned.

## 7) Use with Python SDK (optional)

The SDK is installed in editable mode in the container, but you can also use it locally from this repo.

```bash
# From repo root
pip install -e ".[test,llms,dev]"
```

Example using Ollama reranker:

```python
from mem0 import Memory

config = {
    "vector_store": {
        "provider": "pgvector",
        "config": {
            "host": "localhost",
            "port": 8432,
            "dbname": "postgres",
            "user": "postgres",
            "password": "your_pg_password",  # from .env
            "collection_name": "memories",
            "embedding_model_dims": 768,
        },
    },
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "gemma4:e4b32k",
            "ollama_base_url": "http://localhost:11434",
        },
    },
    "embedder": {
        "provider": "ollama",
        "config": {
            "model": "nomic-embed-text-v2-moe",
            "ollama_base_url": "http://localhost:11434",
        },
    },
    "reranker": {
        "provider": "ollama",
        "config": {
            "model": "dengcao/Qwen3-Reranker-8B:Q5_K_M",
            "ollama_base_url": "http://localhost:11434",
            "top_logprobs": 20,
        },
    },
}

m = Memory.from_config(config)
m.add("I am allergic to peanuts", user_id="alice")
results = m.search("what foods should I avoid?", filters={"user_id": "alice"}, rerank=True)
print(results)
```

## Useful commands (from `server/`)

| Command | Purpose |
|---|---|
| `make up` | Build and start everything (API 8888, Dashboard 3000, Postgres 8432) |
| `make down` | Stop containers |
| `make logs` | Tail logs |
| `make health` | Check service health |
| `make clean` | Stop and remove volumes (clears data) |

## Troubleshooting

- **Container can't reach Ollama**: Ensure Ollama is running on host and `OLLAMA_BASE_URL=http://host.docker.internal:11434` is set. The Compose file adds `extra_hosts: host.docker.internal:host-gateway`.
- **Wrong embedding dims**: `nomic-embed-text-v2-moe` produces 768-dim vectors. If you switch models, update `MEM0_DEFAULT_EMBEDDING_DIMS` and pgvector collection accordingly.
- **Rerank scores are always 0.5**: The yes/no logprob scorer falls back to 0.5 if the model doesn't return clear `yes`/`no` token probabilities for the inputs. Try longer/clearer queries or ensure `top_logprobs` is high enough (default 20). This is a model/score behavior, not a setup bug.
- **Port conflicts**: `make up` checks ports 3000 and 8888; stop anything using them first.
- **Auth issues**: With `AUTH_DISABLED=false`, you must use `X-API-Key` or a Bearer token. The dashboard handles this after setup.

## Where the server code lives

- **Server entrypoint/config**: [`server/main.py`](server/main.py) — defaults to Ollama, adds `rerank` to `SearchRequest`, wires defaults from env.
- **Compose/dev wiring**: [`server/docker-compose.yaml`](server/docker-compose.yaml), [`server/dev.Dockerfile`](server/dev.Dockerfile), [`server/requirements.txt`](server/requirements.txt).
- **Ollama reranker provider (SDK)**: [`mem0/reranker/ollama_reranker.py`](mem0/reranker/ollama_reranker.py), [`mem0/configs/rerankers/ollama.py`](mem0/configs/rerankers/ollama.py), registered in [`mem0/utils/factory.py`](mem0/utils/factory.py) and exported from [`mem0/reranker/__init__.py`](mem0/reranker/__init__.py).
- **Docs**: [`docs/components/rerankers/models/ollama.mdx`](docs/components/rerankers/models/ollama.mdx).

That's it. You now have a fully self-hosted Mem0 stack running entirely on Ollama with opt-in reranking!
