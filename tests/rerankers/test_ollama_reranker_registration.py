from mem0.reranker.ollama_reranker import OllamaReranker
from mem0.utils.factory import RerankerFactory


def test_factory_creates_ollama_reranker(mock_ollama):
    reranker = RerankerFactory.create("ollama", {"model": "m"})
    assert isinstance(reranker, OllamaReranker)
