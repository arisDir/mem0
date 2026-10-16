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
