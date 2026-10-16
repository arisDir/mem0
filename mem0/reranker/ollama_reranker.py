import logging
import math
from typing import Any, Dict, List, Union

from mem0.configs.rerankers.base import BaseRerankerConfig
from mem0.configs.rerankers.ollama import OllamaRerankerConfig
from mem0.reranker.base import BaseReranker

try:
    from ollama import Client

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

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

        if not OLLAMA_AVAILABLE:
            raise ImportError("The 'ollama' library is required. Please install it with 'pip install \"ollama>=0.6.3\"'.")

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
