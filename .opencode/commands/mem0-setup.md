---
description: Set up the self-hosted Mem0 + Ollama stack end-to-end (preflight, models, .env, admin credentials, smoke test) without prompting for input
---

# Self-hosted Mem0 + Ollama — non-interactive setup

Follow these steps **in order** from the repository root. This mirrors
`SELF_HOSTED_OLLAMA_GUIDE.md` and the "Agent-first (command line)" procedure in
`docs/open-source/setup.mdx`.

Hard rules:

- **Never ask the user for anything.** Generate every value you need (secrets,
  admin email/password) yourself and report what you chose at the end.
- **Stop at the first failed check** and report what failed, the evidence, and
  how to fix it. Do not improvise around a failure and do not continue to later
  steps.
- Ports are fixed by `server/docker-compose.yaml`: API `8888`, dashboard `3000`,
  Postgres host `8432`, Ollama `11434`. Do **not** reassign them.
- `server/.env` is gitignored. Credentials written there stay on this machine.
- Safe to re-run: every step checks current state first and skips work that is
  already done (running stack, present models, existing keys).
- This command assumes the agent may run `curl`, `make`, `docker`, `ollama`,
  `openssl`, `ss`/`lsof`, `sed` and `python3`. This repo's `opencode.json` asks
  for approval on unmatched bash commands (`"*": "ask"`), so add allow rules for
  the ones you want fully unattended — otherwise the agent will prompt once per
  command, which is the only input the user would have to give.

All shell below runs from `server/`:

```bash
cd "$(git rev-parse --show-toplevel)/server"
```

## 1. Preflight — is Mem0 already running?

```bash
docker ps --filter label=com.docker.compose.project=mem0-dev \
  --format '{{.Names}} {{.Status}} {{.Ports}}'
```

If the output lists both a `mem0` container and a `postgres` container, the
stack is already running. **Do not restart it.** Verify and report instead with
these `.env`-independent checks (they work even when `server/.env` is absent):

```bash
printf 'API /docs:        %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8888/docs)"
printf 'Dashboard health: %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/api/health)"
pg=$(docker ps --filter label=com.docker.compose.project=mem0-dev --format '{{.Names}}' | grep postgres | head -1)
printf 'Postgres (%s): %s\n' "$pg" "$(docker exec "$pg" pg_isready -q && echo ok || echo down)"
printf 'setup-status:     %s\n' "$(curl -fsS http://localhost:8888/auth/setup-status)"
grep -A6 '^# --- generated credentials' .env 2>/dev/null || echo "(no saved credentials block in server/.env)"
```

Report the health codes, the dashboard URL (`http://localhost:3000`), the API
URL (`http://localhost:8888`), whether setup is already complete, and where any
credentials are stored — then **stop**. Do not re-run bootstrap.

## 2. Preflight — are the required ports free?

```bash
for port in 8888 3000 8432; do
  if ss -ltn 2>/dev/null | grep -q "[:.]$port " || lsof -iTCP:$port -sTCP:LISTEN >/dev/null 2>&1; then
    owner=$( (command -v ss >/dev/null && ss -ltnp 2>/dev/null | grep "[:.]$port " | head -1) \
             || lsof -iTCP:$port -sTCP:LISTEN 2>/dev/null | tail -1 )
    echo "BUSY $port  $owner"
  else
    echo "FREE $port"
  fi
done
```

Every line must print `FREE` (the "Mem0 already running" case was handled in
step 1). Ollama's `11434` is deliberately absent from this list — it must be in
use by the daemon, which step 3 handles. If any port is `BUSY`, **stop
immediately** and tell the user:

- which port is taken and, if known, by which process/container,
- that the ports are fixed by `server/docker-compose.yaml`, so they must free
  the port (or stop the service that owns it),
- that they can re-run `/mem0-setup` once the port is free.

Do not continue to later steps.

## 3. Ollama daemon

Ollama is the one required listener. Start it if it is down:

```bash
curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1 || {
  command -v ollama >/dev/null 2>&1 || {
    echo "ollama is not installed — get it from https://ollama.com/download"; exit 1; }
  mkdir -p /tmp/opencode
  nohup ollama serve >/tmp/opencode/ollama.log 2>&1 &
  for _ in $(seq 1 30); do curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
}
curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1 \
  && echo "ollama: ok" \
  || { echo "ollama: not reachable on :11434 — see /tmp/opencode/ollama.log"; exit 1; }
```

If Ollama never becomes reachable, stop and show the log tail.

## 4. Pull only the models that are missing

```bash
present=$(curl -fsS http://localhost:11434/api/tags \
  | python3 -c 'import json,sys; print("\n".join(m["name"] for m in json.load(sys.stdin).get("models", [])))')

for model in gemma4:e4b32k nomic-embed-text-v2-moe dengcao/Qwen3-Reranker-8B:Q5_K_M; do
  if printf '%s\n' "$present" | grep -qxE "${model}(:latest)?"; then
    echo "present  $model"
  else
    echo "pulling  $model"
    ollama pull "$model" || { echo "failed to pull $model"; exit 1; }
  fi
done
```

An untagged requirement (e.g. `nomic-embed-text-v2-moe`) is satisfied by the
`:latest` tag. Report which models were already present and which were pulled.

## 5. Create or repair `server/.env`

Every key in `server/.env.example` must exist in `server/.env` with a usable
value. Create the file when missing, then reconcile keys and values:

```bash
[ -f .env ] || { umask 077; install -m 600 .env.example .env; echo "created server/.env"; }

# 5a. add any key from .env.example that is missing from .env
while IFS= read -r line; do
  key=${line%%=*}
  grep -qE "^${key}=" .env || { printf '%s\n' "$line" >> .env; echo "added  $key"; }
done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' .env.example)

# 5b. generate secrets that are blank
if ! grep -qE '^POSTGRES_PASSWORD=.+' .env; then
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" .env; echo "generated POSTGRES_PASSWORD"; fi
if ! grep -qE '^JWT_SECRET=.+' .env; then
  sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$(openssl rand -base64 48 | tr -d '\n')|" .env; echo "generated JWT_SECRET"; fi

# 5c. the dashboard is fixed at :3000, so its URL must match
sed -i 's|^DASHBOARD_URL=.*|DASHBOARD_URL=http://localhost:3000|' .env
chmod 600 .env
```

Then validate the values and stop if anything is still unusable:

```bash
python3 - <<'PY'
import sys
env = {}
for raw in open(".env"):
    raw = raw.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        continue
    k, v = raw.split("=", 1)
    env[k] = v

need = ["POSTGRES_PASSWORD", "JWT_SECRET", "POSTGRES_HOST", "POSTGRES_PORT",
        "POSTGRES_DB", "POSTGRES_USER", "DASHBOARD_URL", "OLLAMA_BASE_URL",
        "MEM0_DEFAULT_LLM_MODEL", "MEM0_DEFAULT_EMBEDDER_MODEL",
        "MEM0_DEFAULT_RERANKER_MODEL", "MEM0_DEFAULT_EMBEDDING_DIMS"]
want = {"POSTGRES_HOST": "postgres", "POSTGRES_PORT": "5432",
        "DASHBOARD_URL": "http://localhost:3000", "APP_DB_NAME": "mem0_app",
        "MEM0_DEFAULT_EMBEDDING_DIMS": "768"}

problems = [f"{k} is empty" for k in need if not env.get(k)]
problems += [f"{k}={env[k]!r} (expected {v!r})" for k, v in want.items()
             if k in env and env[k] and env[k] != v]
problems += [f"{k}={env[k]!r} must be true or false" for k in ("AUTH_DISABLED", "MEM0_TELEMETRY")
             if env.get(k) not in (None, "true", "false")]

print("env: FAIL — " + "; ".join(problems) if problems else "env: ok")
sys.exit(1 if problems else 0)
PY
```

If it fails, **stop** and report the listed problems (do not guess at values the
user may have set deliberately, such as `AUTH_DISABLED`).

## 6. Start the stack and create the admin (Agent-first)

```bash
make up
curl -fsS http://localhost:8888/auth/setup-status; echo
```

- **`needsSetup` is `false`** — an admin already exists. Do not create or
  regenerate credentials. If `server/.env` holds a saved password in its
  credentials block, log in (`POST /auth/login`) with it and mint a fresh key
  (`POST /api-keys`) for the smoke test. If no password was saved, stop and tell
  the user to re-run with a known password
  (`make reset-admin-password EMAIL=<email> PASSWORD=<password>`) or start over
  with `make clean && make bootstrap` (wipes data).
- **`needsSetup` is `true`** — generate credentials and seed the admin
  non-interactively. This is the second half of `make bootstrap` (which is
  `make up` + `make seed`); `make up` already ran, so call `make seed` directly
  and avoid a redundant port check:

```bash
EMAIL="admin@mem0.dev"
PASSWORD="$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | cut -c1-20)"
mkdir -p /tmp/opencode
make seed EMAIL="$EMAIL" PASSWORD="$PASSWORD" NAME=Admin OUTPUT=json | tee /tmp/opencode/mem0-seed.json
API_KEY="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["api_key"])' < /tmp/opencode/mem0-seed.json)"
```

`seed.sh` prints a warning that no cloud provider API key is set. That is
expected here — the server defaults to Ollama, which needs no key, and the smoke
test in step 8 is the real provider check. If seeding fails, show
`docker compose logs --tail=50 mem0` and stop.

## 7. Save the credentials in `server/.env` (as comments) and tell the user

Values live in `/tmp/opencode/mem0-seed.json`, so re-derive them here instead of
relying on shell state:

```bash
EMAIL=$(python3 -c 'import json; print(json.load(open("/tmp/opencode/mem0-seed.json"))["email"])')
PASSWORD=$(python3 -c 'import json; print(json.load(open("/tmp/opencode/mem0-seed.json"))["password"])')
API_KEY=$(python3 -c 'import json; print(json.load(open("/tmp/opencode/mem0-seed.json"))["api_key"])')

{
  echo ""
  echo "# --- generated credentials ($(date -Iseconds)) ---"
  echo "# Dashboard:      http://localhost:3000"
  echo "# API:            http://localhost:8888"
  echo "# Admin email:    $EMAIL"
  echo "# Admin password: $PASSWORD"
  echo "# API key:        $API_KEY"
} >> .env
chmod 600 .env
```

Tell the user explicitly: **the generated admin credentials and API key were
appended as comments to `server/.env`**, which is gitignored, so they are not in
version control. Never append a second block for the same run, and never append
when `needsSetup` was already `false`.

## 8. Smoke test

```bash
API_KEY=$(python3 -c 'import json; print(json.load(open("/tmp/opencode/mem0-seed.json"))["api_key"])')  # or the key in the .env credentials block
curl -s -X POST http://localhost:8888/memories \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"I am allergic to peanuts and I live in Berlin"}],"user_id":"mem0-setup"}'; echo
curl -s -X POST http://localhost:8888/search \
  -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"query":"what should I avoid eating?","filters":{"user_id":"mem0-setup"},"rerank":true}'; echo
```

Use a statement that contains an actual fact: a content-free sentence legitimately
extracts nothing, so an empty `results` list from `/memories` is not a failure by
itself (the example above yields an `ADD` and a `rerank_score` on this branch).

The search response must contain a `rerank_score`. If either call returns
`provider_auth_failed`, the container is not reaching Ollama — check that
`OLLAMA_BASE_URL=http://host.docker.internal:11434` is set in `server/.env` and
that `extra_hosts` maps `host.docker.internal` in `docker-compose.yaml`, then
`docker compose up -d --force-recreate mem0` and retry.

## 9. Final report

Give the user a short summary:

- **Stack**: dashboard URL, API URL, `make health` result.
- **Preflight**: whether Mem0 was already running, and that all required ports
  were free.
- **Models**: which of the three were already present, which were pulled.
- **`.env`**: created or validated, which keys were added, which secrets were
  generated, and that `DASHBOARD_URL` was kept at `http://localhost:3000`.
- **Credentials**: the admin email and API key (the password is in `.env`), and
  the reminder that they were appended as comments at the end of the gitignored
  `server/.env`.
- **Smoke test**: whether the memory was stored and `rerank_score` came back.
