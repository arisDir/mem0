# Self-hosted Mem0 Server on Ollama Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the self-hosted Mem0 server with Ollama as the LLM, embedder, and reranker, adding a first-class `ollama` reranker provider to the SDK.

**Architecture:** Add `OllamaReranker` (a yes/no logprob scorer) to the Python SDK and register it in `RerankerFactory`. Point the server's default config at Ollama, add an opt-in `rerank` flag to `POST /search`, and make the dev Compose stack reach the host's Ollama and run the local SDK editable so the new provider is live.

**Tech Stack:** Python 3.9–3.12, Pydantic v2, `ollama` Python client >= 0.6.3, FastAPI, Docker Compose, pytest + pytest-mock, ruff (line length 120).

## Execution Protocol

**Before executing any task, every task in this plan MUST first be written to a to-do list.** This is mandatory and applies regardless of how the work is carried out.

- The executor (whether one agent or a coordinating orchestrator) must create a to-do list containing all seven tasks with their names and statuses, and keep exactly one task `in_progress` at a time, updating it as tasks complete.
- In multi-agent execution (e.g. subagent-driven-development), the orchestrator owns the master to-do list covering all tasks; each subagent must additionally create its own to-do list for the specific task(s) it is assigned before starting work.
- No code, tests, commits, or other task actions may begin until the to-do list for the upcoming task(s) exists.
- Mark a task completed only after its own tests and lint pass and its commit is made.

## Global Constraints

- Python must run on 3.9 through 3.12; use no 3.10+-only syntax in `mem0/`.
- Ruff line length **120**; Pydantic v2 for all models/config.
- Tests mock the provider SDK, never the code under test.
- `ollama` Python client must be **>= 0.6.3** (adds `logprobs`/`top_logprobs` and `think` to `generate`).
- Reranker model: `dengcao/Qwen3-Reranker-8B:Q5_K_M`.
- LLM model: `gemma4:e4b32k`; embedder model: `nomic-embed-text-v2-moe`.
- Embedding dimension is **768**; pgvector must be created with `embedding_model_dims: 768`.
- Ollama base URL from the container: `http://host.docker.internal:11434`.
- Never commit `server/.env` (gitignored).

---

## File Structure

**Create:**
- `mem0/configs/rerankers/ollama.py` — `OllamaRerankerConfig`
- `mem0/reranker/ollama_reranker.py` — `OllamaReranker`
- `tests/rerankers/test_ollama_reranker.py` — provider unit tests
- `tests/rerankers/test_ollama_reranker_registration.py` — factory wiring test
- `docs/components/rerankers/models/ollama.mdx` — provider docs page
- `server/.env` — local secrets/config (gitignored, not committed)

**Modify:**
- `tests/rerankers/conftest.py` — add `mock_ollama` fixture
- `mem0/utils/factory.py` — register provider + import config
- `mem0/reranker/__init__.py` — export `OllamaReranker`
- `tests/rerankers/test_reranker_public_exports.py` — include `OllamaReranker`
- `server/main.py` — bundled providers, default config, `rerank` flag
- `server/requirements.txt` — add `ollama>=0.6.3`
- `server/docker-compose.yaml` — `extra_hosts`, env defaults, live SDK mount/install
- `server/.env.example` — document Ollama vars
- `docs/docs.json` — nav entry
- `docs/llms.txt` — index entry
- `docs/components/rerankers/config.mdx` — provider config table

---

## Task 1: Ollama reranker provider (config + scorer)

**Files:**
- Create: `mem0/configs/rerankers/ollama.py`
- Create: `mem0/reranker/ollama_reranker.py`
- Create: `tests/rerankers/test_ollama_reranker.py`
- Modify: `tests/rerankers/conftest.py`

**Interfaces:**
- Consumes: `BaseRerankerConfig` (`mem0/configs/rerankers/base.py`), `BaseReranker` (`mem0/reranker/base.py`).
- Produces:
  - `OllamaRerankerConfig(BaseRerankerConfig)` fields: `ollama_base_url: Optional[str] = None`, `temperature: float = 0.0`, `max_tokens: int = 8`, `top_logprobs: int = 20`, `system_prompt: Optional[str] = None`; inherits `provider`, `model`, `api_key`, `top_k`.
  - `OllamaReranker(config: Union[BaseRerankerConfig, OllamaRerankerConfig, Dict])` with `rerank(query: str, documents: List[Dict[str, Any]], top_k: int = None) -> List[Dict[str, Any]]`; each output dict gets a `rerank_score: float` in `[0.0, 1.0]`.

- [ ] **Step 1: Add the `mock_ollama` fixture to `tests/rerankers/conftest.py`**

Add to the end of the file:

```python
@pytest.fixture
def mock_ollama(monkeypatch):
    """Patch the ``ollama.Client`` used by OllamaReranker so tests never hit the network."""
    import mem0.reranker.ollama_reranker as ollama_reranker

    fake_client = MagicMock()
    monkeypatch.setattr(ollama_reranker, "Client", MagicMock(return_value=fake_client))
    return ollama_reranker, fake_client
```

- [ ] **Step 2: Write the failing tests**

Create `tests/rerankers/test_ollama_reranker.py`:

```python
import math

import pytest

from mem0.reranker.ollama_reranker import OllamaReranker


def _logprobs(yes=None, no=None):
    """Build an Ollama-style logprobs payload with yes/no candidates at one position."""
    candidates = []
    if yes is not None:
        candidates.append({"token": "yes", "logprob": yes})
    if no is not None:
        candidates.append({"token": "no", "logprob": no})
    return [{"token": " ", "logprob": -0.1, "top_logprobs": candidates}]


def _client_returning(mock_client, payloads):
    mock_client.generate.side_effect = [{"logprobs": p} for p in payloads]


class TestInit:
    def test_requires_model(self, mock_ollama):
        with pytest.raises(ValueError, match="model"):
            OllamaReranker({"provider": "ollama"})

    def test_accepts_config_object(self, mock_ollama):
        from mem0.configs.rerankers.ollama import OllamaRerankerConfig

        reranker = OllamaReranker(OllamaRerankerConfig(model="m", ollama_base_url="http://x:1"))
        assert reranker.config.model == "m"


class TestScoring:
    @pytest.mark.parametrize("yes,no,expected", [(0.0, -3.0, 0.95), (-3.0, 0.0, 0.05)])
    def test_yes_no_ratio(self, mock_ollama, yes, no, expected):
        _, client = mock_ollama
        _client_returning(client, [_logprobs(yes=yes, no=no)])
        reranker = OllamaReranker({"model": "m"})
        assert reranker.rerank("q", [{"memory": "d"}])[0]["rerank_score"] == pytest.approx(expected, abs=0.01)

    def test_only_yes_scores_one(self, mock_ollama):
        _, client = mock_ollama
        _client_returning(client, [_logprobs(yes=-0.01)])
        assert OllamaReranker({"model": "m"}).rerank("q", [{"memory": "d"}])[0]["rerank_score"] == 1.0

    def test_only_no_scores_zero(self, mock_ollama):
        _, client = mock_ollama
        _client_returning(client, [_logprobs(no=-0.01)])
        assert OllamaReranker({"model": "m"}).rerank("q", [{"memory": "d"}])[0]["rerank_score"] == 0.0

    def test_last_decision_wins(self, mock_ollama):
        _, client = mock_ollama
        _client_returning(client, [_logprobs(yes=-0.01, no=-5.0), _logprobs(yes=-5.0, no=-0.01)])
        assert OllamaReranker({"model": "m"}).rerank("q", [{"memory": "d"}])[0]["rerank_score"] == pytest.approx(
            0.0, abs=0.01
        )

    def test_missing_tokens_is_neutral(self, mock_ollama):
        _, client = mock_ollama
        _client_returning(client, [[{"token": "foo", "logprob": -0.1, "top_logprobs": [{"token": "bar", "logprob": -1.0}]}]])
        assert OllamaReranker({"model": "m"}).rerank("q", [{"memory": "d"}])[0]["rerank_score"] == 0.5

    def test_generate_error_is_neutral(self, mock_ollama):
        _, client = mock_ollama
        client.generate.side_effect = RuntimeError("connection refused")
        assert OllamaReranker({"model": "m"}).rerank("q", [{"memory": "d"}])[0]["rerank_score"] == 0.5


class TestRerank:
    def test_sorted_descending(self, mock_ollama):
        _, client = mock_ollama
        _client_returning(client, [_logprobs(yes=-3.0, no=0.0), _logprobs(yes=0.0, no=-3.0), _logprobs(yes=-1.0, no=-1.0)])
        result = OllamaReranker({"model": "m"}).rerank("q", [{"memory": "a"}, {"memory": "b"}, {"memory": "c"}])
        assert [r["rerank_score"] for r in result] == sorted([r["rerank_score"] for r in result], reverse=True)

    def test_top_k_argument_limits(self, mock_ollama):
        _, client = mock_ollama
        _client_returning(client, [_logprobs(yes=0.0, no=-3.0)] * 3)
        result = OllamaReranker({"model": "m"}).rerank("q", [{"memory": str(i)} for i in range(3)], top_k=2)
        assert len(result) == 2

    def test_config_top_k_used_when_arg_absent(self, mock_ollama):
        _, client = mock_ollama
        _client_returning(client, [_logprobs(yes=0.0, no=-3.0)] * 3)
        result = OllamaReranker({"model": "m", "top_k": 1}).rerank("q", [{"memory": str(i)} for i in range(3)])
        assert len(result) == 1

    def test_empty_documents(self, mock_ollama):
        assert OllamaReranker({"model": "m"}).rerank("q", []) == []

    def test_does_not_mutate_input(self, mock_ollama):
        _, client = mock_ollama
        _client_returning(client, [_logprobs(yes=0.0, no=-3.0)])
        original = {"memory": "d", "id": "1"}
        result = OllamaReranker({"model": "m"}).rerank("q", [original])
        assert "rerank_score" not in original
        assert "rerank_score" in result[0]

    def test_text_extraction_precedence(self, mock_ollama):
        _, client = mock_ollama
        _client_returning(client, [_logprobs(yes=0.0, no=-3.0), _logprobs(yes=0.0, no=-3.0)])
        OllamaReranker({"model": "m"}).rerank("q", [{"text": "TEXT_MARKER"}, {"content": "CONTENT_MARKER"}])
        first_prompt = client.generate.call_args_list[0].kwargs["prompt"]
        assert "TEXT_MARKER" in first_prompt
        assert "CONTENT_MARKER" not in first_prompt
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `hatch run dev_py_3_11 pytest tests/rerankers/test_ollama_reranker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mem0.reranker.ollama_reranker'`.

- [ ] **Step 4: Create the config class**

Create `mem0/configs/rerankers/ollama.py`:

```python
from typing import Optional

from pydantic import Field

from mem0.configs.rerankers.base import BaseRerankerConfig


class OllamaRerankerConfig(BaseRerankerConfig):
    """Configuration for the Ollama reranker provider.

    Targets models that answer a relevance judgement with ``yes``/``no``
    (e.g. Qwen3-Reranker) and are scored from their output log probabilities.
    """

    ollama_base_url: Optional[str] = Field(
        default=None,
        description="Base URL of the Ollama server. None uses the Ollama client default.",
    )
    temperature: float = Field(default=0.0, description="Sampling temperature for scoring")
    max_tokens: int = Field(default=8, description="Maximum tokens to generate for a score")
    top_logprobs: int = Field(default=20, description="Number of candidate tokens returned per position")
    system_prompt: Optional[str] = Field(default=None, description="Override the default yes/no system prompt")
```

- [ ] **Step 5: Create the provider**

Create `mem0/reranker/ollama_reranker.py`:

```python
import logging
import math
from typing import Any, Dict, List, Union

from mem0.configs.rerankers.base import BaseRerankerConfig
from mem0.configs.rerankers.ollama import OllamaRerankerConfig
from mem0.reranker.base import BaseReranker

try:
    from ollama import Client
except ImportError:
    raise ImportError("The 'ollama' library is required. Please install it with 'pip install \"ollama>=0.6.3\"'.")

logger = logging.getLogger(__name__)


class OllamaReranker(BaseReranker):
    """Reranker backed by a yes/no scoring model served through Ollama.

    The relevance score is derived from the log probabilities of the ``yes`` and
    ``no`` tokens emitted after the judgement prompt, so no numeric generation is
    required from the model.
    """

    _DEFAULT_SYSTEM_PROMPT = (
        "Judge whether the Document meets the requirements based on the Query. "
        'Answer only "yes" or "no".'
    )
    _MAX_INPUT_LEN = 4000
    _YES = "yes"
    _NO = "no"

    def __init__(self, config: Union[BaseRerankerConfig, OllamaRerankerConfig, Dict]):
        if isinstance(config, dict):
            config = OllamaRerankerConfig(**config)
        elif isinstance(config, BaseRerankerConfig) and not isinstance(config, OllamaRerankerConfig):
            config = OllamaRerankerConfig(
                model=getattr(config, "model", None),
                top_k=getattr(config, "top_k", None),
            )

        if not config.model:
            raise ValueError("OllamaReranker requires a 'model' in its config.")

        self.config = config
        self._system_prompt = config.system_prompt or self._DEFAULT_SYSTEM_PROMPT
        self.client = Client(host=config.ollama_base_url)

    @staticmethod
    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _doc_text(doc: Dict[str, Any]) -> str:
        if "memory" in doc:
            return doc["memory"]
        if "text" in doc:
            return doc["text"]
        if "content" in doc:
            return doc["content"]
        return str(doc)

    def _logprob_pairs(self, entry: Any) -> Dict[str, float]:
        """Map lowercased candidate tokens to their log probabilities at one position."""
        pairs: Dict[str, float] = {}
        token = self._get(entry, "token")
        if isinstance(token, str):
            pairs[token.strip().lower()] = self._get(entry, "logprob")
        for candidate in self._get(entry, "top_logprobs") or []:
            cand_token = self._get(candidate, "token")
            if isinstance(cand_token, str):
                pairs[cand_token.strip().lower()] = self._get(candidate, "logprob")
        return pairs

    def _score_from_logprobs(self, logprobs: List[Any]) -> float:
        """Return P(yes)/(P(yes)+P(no)) from the last position that offers a yes/no choice."""
        decision: Dict[str, float] = {}
        for entry in logprobs or []:
            pairs = self._logprob_pairs(entry)
            if self._YES in pairs or self._NO in pairs:
                decision = pairs

        if not decision:
            return 0.5

        yes = decision.get(self._YES)
        no = decision.get(self._NO)
        if yes is not None and no is not None:
            return 1.0 / (1.0 + math.exp(no - yes))
        return 1.0 if yes is not None else 0.0

    def _score(self, query: str, document: str) -> float:
        safe_query = query[: self._MAX_INPUT_LEN]
        safe_doc = document[: self._MAX_INPUT_LEN]
        prompt = f"<Query>: {safe_query}\n<Document>: {safe_doc}"
        try:
            response = self.client.generate(
                model=self.config.model,
                prompt=prompt,
                system=self._system_prompt,
                options={"temperature": self.config.temperature, "num_predict": self.config.max_tokens},
                logprobs=True,
                top_logprobs=self.config.top_logprobs,
                think=False,
                keep_alive="5m",
            )
            logprobs = self._get(response, "logprobs") or []
            return self._score_from_logprobs(logprobs)
        except Exception as e:
            logger.warning("Ollama reranking failed for a document, assigning neutral score: %s", e)
            return 0.5

    def rerank(self, query: str, documents: List[Dict[str, Any]], top_k: int = None) -> List[Dict[str, Any]]:
        if not documents:
            return documents

        scored = []
        for doc in documents:
            scored_doc = doc.copy()
            scored_doc["rerank_score"] = self._score(query, self._doc_text(doc))
            scored.append(scored_doc)

        scored.sort(key=lambda d: d["rerank_score"], reverse=True)

        if top_k:
            scored = scored[:top_k]
        elif self.config.top_k:
            scored = scored[: self.config.top_k]

        return scored
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `hatch run dev_py_3_11 pytest tests/rerankers/test_ollama_reranker.py -v`
Expected: PASS (all tests).

- [ ] **Step 7: Lint**

Run: `hatch run dev_py_3_11 ruff check mem0/configs/rerankers/ollama.py mem0/reranker/ollama_reranker.py tests/rerankers/test_ollama_reranker.py`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add mem0/configs/rerankers/ollama.py mem0/reranker/ollama_reranker.py tests/rerankers/test_ollama_reranker.py tests/rerankers/conftest.py
git commit -m "feat(reranker): add Ollama yes/no logprob reranker provider"
```

---

## Task 2: Register the provider in the factory and package exports

**Files:**
- Modify: `mem0/utils/factory.py:18-25, 233-242`
- Modify: `mem0/reranker/__init__.py`
- Create: `tests/rerankers/test_ollama_reranker_registration.py`
- Modify: `tests/rerankers/test_reranker_public_exports.py`

**Interfaces:**
- Consumes: `OllamaReranker`, `OllamaRerankerConfig` from Task 1.
- Produces: `RerankerFactory.create("ollama", {...})` returns an `OllamaReranker`; `from mem0.reranker import OllamaReranker` succeeds.

- [ ] **Step 1: Write the failing registration test**

Create `tests/rerankers/test_ollama_reranker_registration.py`:

```python
from mem0.reranker.ollama_reranker import OllamaReranker
from mem0.utils.factory import RerankerFactory


def test_factory_creates_ollama_reranker(mock_ollama):
    reranker = RerankerFactory.create("ollama", {"model": "m"})
    assert isinstance(reranker, OllamaReranker)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `hatch run dev_py_3_11 pytest tests/rerankers/test_ollama_reranker_registration.py -v`
Expected: FAIL — `ValueError: Unsupported reranker provider: ollama`.

- [ ] **Step 3: Register in the factory**

In `mem0/utils/factory.py`, add the import next to the other reranker config imports (around line 22):

```python
from mem0.configs.rerankers.ollama import OllamaRerankerConfig
```

Add the provider mapping inside `RerankerFactory.provider_to_class` (after the `"huggingface"` entry, around line 241):

```python
        "ollama": ("mem0.reranker.ollama_reranker.OllamaReranker", OllamaRerankerConfig),
```

- [ ] **Step 4: Export from the package**

In `mem0/reranker/__init__.py`, add the import and `__all__` entry:

```python
from .ollama_reranker import OllamaReranker
```

and append `"OllamaReranker",` to `__all__`.

- [ ] **Step 5: Update the public-exports regression test**

In `tests/rerankers/test_reranker_public_exports.py`:
- Add `OllamaReranker` to the import list in `test_all_rerankers_are_importable_from_package_root`.
- Add `OllamaReranker` to the `assert { ... }` set in that test.
- Add `"OllamaReranker"` to the `expected` set in `test_all_exported_names_are_present_in_dunder_all`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `hatch run dev_py_3_11 pytest tests/rerankers/ -v`
Expected: PASS (all reranker tests, including registration and exports).

- [ ] **Step 7: Commit**

```bash
git add mem0/utils/factory.py mem0/reranker/__init__.py tests/rerankers/test_ollama_reranker_registration.py tests/rerankers/test_reranker_public_exports.py
git commit -m "feat(reranker): register ollama provider in RerankerFactory and exports"
```

---

## Task 3: Server default config, bundled providers, and rerank flag

**Files:**
- Modify: `server/main.py:62-63, 108-139, 198-207, 469-478`

**Interfaces:**
- Consumes: `ollama` provider (Task 1/2) available in the SDK.
- Produces: `DEFAULT_CONFIG` uses `ollama` for `llm`, `embedder`, `reranker` and `embedding_model_dims: 768`; `SearchRequest.rerank: Optional[bool]`; `POST /search` passes `rerank`.

- [ ] **Step 1: Add `ollama` to the bundled provider tuples**

`server/main.py` lines 62-63 become:

```python
BUNDLED_LLM_PROVIDERS = ("openai", "anthropic", "gemini", "ollama")
BUNDLED_EMBEDDER_PROVIDERS = ("openai", "gemini", "ollama")
```

- [ ] **Step 2: Add the Ollama env vars and defaults**

After the existing `DEFAULT_LLM_MODEL`/`DEFAULT_EMBEDDER_MODEL` lines (server/main.py:117-118), replace those two lines and add the Ollama settings:

```python
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
DEFAULT_LLM_MODEL = os.environ.get("MEM0_DEFAULT_LLM_MODEL", "gemma4:e4b32k")
DEFAULT_EMBEDDER_MODEL = os.environ.get("MEM0_DEFAULT_EMBEDDER_MODEL", "nomic-embed-text-v2-moe")
DEFAULT_RERANKER_MODEL = os.environ.get("MEM0_DEFAULT_RERANKER_MODEL", "dengcao/Qwen3-Reranker-8B:Q5_K_M")
DEFAULT_EMBEDDING_DIMS = int(os.environ.get("MEM0_DEFAULT_EMBEDDING_DIMS", "768"))
```

- [ ] **Step 3: Rewrite `DEFAULT_CONFIG`**

Replace `DEFAULT_CONFIG` (server/main.py:120-139) with:

```python
DEFAULT_CONFIG = {
    "version": "v1.1",
    "vector_store": {
        "provider": "pgvector",
        "config": {
            "host": POSTGRES_HOST,
            "port": int(POSTGRES_PORT),
            "dbname": POSTGRES_DB,
            "user": POSTGRES_USER,
            "password": POSTGRES_PASSWORD,
            "collection_name": POSTGRES_COLLECTION_NAME,
            "embedding_model_dims": DEFAULT_EMBEDDING_DIMS,
        },
    },
    "llm": {
        "provider": "ollama",
        "config": {"model": DEFAULT_LLM_MODEL, "ollama_base_url": OLLAMA_BASE_URL, "temperature": 0.2},
    },
    "embedder": {
        "provider": "ollama",
        "config": {"model": DEFAULT_EMBEDDER_MODEL, "ollama_base_url": OLLAMA_BASE_URL},
    },
    "reranker": {
        "provider": "ollama",
        "config": {
            "model": DEFAULT_RERANKER_MODEL,
            "ollama_base_url": OLLAMA_BASE_URL,
            "top_logprobs": 20,
        },
    },
    "history_db_path": HISTORY_DB_PATH,
}
```

- [ ] **Step 4: Add the `rerank` field to `SearchRequest`**

In the `SearchRequest` model (server/main.py:198-207), add after `show_expired`:

```python
    rerank: Optional[bool] = Field(None, description="Rerank results using the configured reranker.")
```

- [ ] **Step 5: Pass `rerank` through in `search_memories`**

In `search_memories` (server/main.py:469-478), add before the `return`:

```python
        if search_req.rerank is not None:
            params["rerank"] = search_req.rerank
```

- [ ] **Step 6: Verify the file compiles and the config is correct**

Run:
```bash
cd server && python -m py_compile main.py && grep -n "ollama\|embedding_model_dims\|rerank" main.py | head -30
```
Expected: compiles with no output errors; grep shows the `ollama` providers, `embedding_model_dims`, and `rerank` lines.

- [ ] **Step 7: Commit**

```bash
git add server/main.py
git commit -m "feat(server): default to Ollama for llm, embedder, and reranker with opt-in rerank"
```

---

## Task 4: Server dependencies and Compose wiring

**Files:**
- Modify: `server/requirements.txt`
- Modify: `server/docker-compose.yaml`

**Interfaces:**
- Consumes: nothing from earlier tasks at build time.
- Produces: the `mem0` container can reach host Ollama and runs the local editable SDK.

- [ ] **Step 1: Add the Ollama dependency**

In `server/requirements.txt`, under the bundled providers comment block, add:

```text
ollama>=0.6.3
```

- [ ] **Step 2: Add `extra_hosts`, Ollama env defaults, and the live SDK mount/command**

In `server/docker-compose.yaml`, update the `mem0` service. Add `extra_hosts` after `ports`, add the SDK volume, extend `environment`, and change `command`:

```yaml
  mem0:
    build:
      context: ..
      dockerfile: server/dev.Dockerfile
    ports:
      - "8888:8000"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    env_file:
      - .env
    networks:
      - mem0_network
    volumes:
      - ./history:/app/history
      - .:/app
      - ..:/workspace
    depends_on:
      postgres:
        condition: service_healthy
    command: >
      sh -c "pip install -q --force-reinstall --no-deps -e /workspace && alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
    environment:
      - PYTHONDONTWRITEBYTECODE=1
      - PYTHONUNBUFFERED=1
      - PYTHONPATH=
      - DASHBOARD_URL=http://localhost:3000
      - APP_DB_NAME=mem0_app
      - JWT_SECRET=${JWT_SECRET}
      - AUTH_DISABLED=${AUTH_DISABLED:-false}
      - MEM0_TELEMETRY=${MEM0_TELEMETRY:-true}
      - OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
      - MEM0_DEFAULT_LLM_MODEL=${MEM0_DEFAULT_LLM_MODEL:-gemma4:e4b32k}
      - MEM0_DEFAULT_EMBEDDER_MODEL=${MEM0_DEFAULT_EMBEDDER_MODEL:-nomic-embed-text-v2-moe}
      - MEM0_DEFAULT_RERANKER_MODEL=${MEM0_DEFAULT_RERANKER_MODEL:-dengcao/Qwen3-Reranker-8B:Q5_K_M}
```

- [ ] **Step 3: Verify the resolved Compose config**

Run:
```bash
cd server && printf 'POSTGRES_PASSWORD=x\nJWT_SECRET=y\n' > .env && docker compose config | grep -A3 "extra_hosts\|/workspace" ; rm -f .env
```
Expected: output shows `host.docker.internal` in `extra_hosts` and a `..`-sourced bind at `/workspace`.

- [ ] **Step 4: Commit**

```bash
git add server/requirements.txt server/docker-compose.yaml
git commit -m "build(server): reach host Ollama and run local SDK editable in dev compose"
```

---

## Task 5: Local env file and example

**Files:**
- Create: `server/.env` (gitignored — not committed)
- Modify: `server/.env.example`

**Interfaces:**
- Consumes: env var names from Task 3/4.
- Produces: a runnable local config.

- [ ] **Step 1: Document the Ollama vars in `.env.example`**

In `server/.env.example`, replace the `OPENAI_API_KEY` section note and append the Ollama block. Add after the existing model defaults:

```text
# Ollama (local models). The server reaches the host daemon through host.docker.internal.
# Required: the ollama Python client >= 0.6.3 for logprob scoring.
OLLAMA_BASE_URL=http://host.docker.internal:11434
MEM0_DEFAULT_LLM_MODEL=gemma4:e4b32k
MEM0_DEFAULT_EMBEDDER_MODEL=nomic-embed-text-v2-moe
MEM0_DEFAULT_RERANKER_MODEL=dengcao/Qwen3-Reranker-8B:Q5_K_M
MEM0_DEFAULT_EMBEDDING_DIMS=768
```

- [ ] **Step 2: Create `server/.env` with generated secrets**

Run:

```bash
cd /home/aris/projects/mem0/server
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
git check-ignore .env && echo "(.env is gitignored)"
```

Expected: prints `(.env is gitignored)`.

- [ ] **Step 3: Commit only the example file**

```bash
git add server/.env.example
git commit -m "docs(server): document Ollama env vars in .env.example"
```

---

## Task 6: Documentation page and index entries

**Files:**
- Create: `docs/components/rerankers/models/ollama.mdx`
- Modify: `docs/docs.json:274-278`
- Modify: `docs/llms.txt` (Rerankers section)
- Modify: `docs/components/rerankers/config.mdx:51-69`

**Interfaces:**
- Consumes: the config schema from Task 1.
- Produces: a discoverable docs page with a matching `llms.txt` entry.

- [ ] **Step 1: Create the docs page**

Create `docs/components/rerankers/models/ollama.mdx`:

````mdx
---
title: Ollama Reranker
description: 'Rerank self-hosted search results with a local Ollama scoring model'
icon: 'sparkles'
---

## Overview

The Ollama reranker scores each candidate memory against the query with a local model served by
[Ollama](https://ollama.com). It targets yes/no scoring models such as `Qwen3-Reranker`, which
answer a relevance judgement with `yes` or `no`. Mem0 reads the model's output log probabilities
for those two tokens and turns them into a relevance score.

<Note>
  Requires the `ollama` Python package **>= 0.6.3** for `logprobs` and `think` support:
  `pip install "ollama>=0.6.3"`.
</Note>

## Configuration

```python
from mem0 import Memory

config = {
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

results = m.search("What foods should I avoid?", filters={"user_id": "alice"}, rerank=True)
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | str | Required | Ollama model name (a yes/no scoring model) |
| `ollama_base_url` | str | None | Ollama server URL; None uses the client default (`http://localhost:11434`) |
| `temperature` | float | 0.0 | Sampling temperature for scoring |
| `max_tokens` | int | 8 | Maximum tokens generated per document |
| `top_logprobs` | int | 20 | Candidate tokens returned per position; keep high enough to include `yes` and `no` |
| `system_prompt` | str | None | Override the default yes/no judgement prompt |
| `top_k` | int | None | Maximum documents returned after reranking |

## Scoring

For each document the reranker sends the query and document to the model, then computes

```
score = P(yes) / (P(yes) + P(no))
```

using the log probabilities at the last position that offers a `yes`/`no` choice. A missing
choice, a model error, or an unreachable Ollama daemon yields a neutral `0.5`, and search falls
back to vector results if reranking fails entirely.

## Next Steps

<CardGroup cols={2}>
  <Card title="Reranker Configuration" icon="gear" href="/components/rerankers/config">
    Shared and provider-specific reranker config options
  </Card>
  <Card title="Reranker Search" icon="magnifying-glass" href="/open-source/features/reranker-search">
    Enable reranking during search
  </Card>
</CardGroup>
````

- [ ] **Step 2: Add the navigation entry**

In `docs/docs.json`, add `"components/rerankers/models/ollama"` to the reranker models list (after `"components/rerankers/models/llm-reranker"`, around line 277).

- [ ] **Step 3: Add the provider table row**

In `docs/components/rerankers/config.mdx`, add after the `### LLM Reranker` table (before `## Environment Variables`):

```mdx
### Ollama

| Parameter | Type | Default | Description |
| --------- | ---- | ------- | ----------- |
| `model` | `str` | Required | Ollama yes/no scoring model |
| `ollama_base_url` | `str` | `None` | Ollama server URL |
| `temperature` | `float` | `0.0` | Scoring temperature |
| `max_tokens` | `int` | `8` | Max tokens per document |
| `top_logprobs` | `int` | `20` | Candidate tokens per position |
| `system_prompt` | `str` | `None` | Override the default judgement prompt |
```

- [ ] **Step 4: Add the `llms.txt` entry**

In `docs/llms.txt`, under the `### Rerankers [OSS]` section, add:

```text
- [Ollama Reranker](https://docs.mem0.ai/components/rerankers/models/ollama) [OSS]: Use when reranking self-hosted search with a local Ollama yes/no scoring model.
```

- [ ] **Step 5: Verify `llms.txt` coverage**

Run: `python scripts/check-llms-txt-coverage.py`
Expected: exits 0 with no missing entries. If it reports the new page, run `python scripts/check-llms-txt-coverage.py --write`, replace the `[TODO: ...]` placeholder with the line from Step 4, and re-run until clean.

- [ ] **Step 6: Commit**

```bash
git add docs/components/rerankers/models/ollama.mdx docs/docs.json docs/llms.txt docs/components/rerankers/config.mdx
git commit -m "docs(reranker): document the Ollama reranker provider"
```

---

## Task 7: End-to-end verification and start the server

**Files:** none (verification only).

**Interfaces:**
- Consumes: all prior tasks.
- Produces: a running self-hosted server using Ollama for LLM, embedding, and reranking.

- [ ] **Step 1: Confirm the host Ollama daemon is reachable**

Run: `curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | head`
Expected: lists `gemma4:e4b32k`, `nomic-embed-text-v2-moe:latest`, and `dengcao/Qwen3-Reranker-8B:Q5_K_M`.

- [ ] **Step 2: Build and start the stack**

Run: `cd /home/aris/projects/mem0/server && make up`
Expected: builds the image, waits for API + dashboard, prints `Stack is ready.` with the dashboard at `http://localhost:3000` and API at `http://localhost:8888`.

- [ ] **Step 3: Smoke-test the SDK + Ollama + pgvector + reranker inside the container**

Run:
```bash
cd /home/aris/projects/mem0/server
docker compose exec -T mem0 python - <<'PY'
import os
from mem0 import Memory

config = {
    "vector_store": {
        "provider": "pgvector",
        "config": {
            "host": os.environ["POSTGRES_HOST"],
            "port": int(os.environ["POSTGRES_PORT"]),
            "dbname": os.environ["POSTGRES_DB"],
            "user": os.environ["POSTGRES_USER"],
            "password": os.environ["POSTGRES_PASSWORD"],
            "collection_name": "smoke_test",
            "embedding_model_dims": 768,
        },
    },
    "llm": {"provider": "ollama", "config": {"model": os.environ["MEM0_DEFAULT_LLM_MODEL"], "ollama_base_url": os.environ["OLLAMA_BASE_URL"]}},
    "embedder": {"provider": "ollama", "config": {"model": os.environ["MEM0_DEFAULT_EMBEDDER_MODEL"], "ollama_base_url": os.environ["OLLAMA_BASE_URL"]}},
    "reranker": {"provider": "ollama", "config": {"model": os.environ["MEM0_DEFAULT_RERANKER_MODEL"], "ollama_base_url": os.environ["OLLAMA_BASE_URL"]}},
}
m = Memory.from_config(config)
m.add("I am allergic to peanuts", user_id="smoke")
m.add("I love Italian food", user_id="smoke")
res = m.search("what foods should I avoid?", filters={"user_id": "smoke"}, rerank=True)
for r in res["results"]:
    print(r.get("rerank_score"), r["memory"])
m.delete_all(user_id="smoke")
PY
```
Expected: memories are found and `rerank_score` values are present and ordered descending. A `0.5` for every row indicates the yes/no tokens were not found — revisit `top_logprobs` / prompt in Task 1.

- [ ] **Step 4: Verify the API and dashboard health**

Run: `cd /home/aris/projects/mem0/server && make health`
Expected: `API: 200`, `Dashboard: 200`, `Postgres: ok`.

- [ ] **Step 5: Verify the API rerank flag**

In the dashboard (`http://localhost:3000`) complete the setup wizard, then create an API key. Run:

```bash
curl -s -X POST http://localhost:8888/memories \
  -H "X-API-Key: <KEY>" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"I am allergic to peanuts"}],"user_id":"api-user"}'

curl -s -X POST http://localhost:8888/search \
  -H "X-API-Key: <KEY>" -H "Content-Type: application/json" \
  -d '{"query":"what should I avoid eating?","filters":{"user_id":"api-user"},"rerank":true}'
```
Expected: the search response lists the peanut memory with a `rerank_score`.

- [ ] **Step 6: Final commit (if any verification-only follow-up fixes were needed)**

```bash
git add -A
git commit -m "fix(server): address Ollama end-to-end verification findings"
```
(Only if Step 3-5 required code changes; otherwise skip.)
