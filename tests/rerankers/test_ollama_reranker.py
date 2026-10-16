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
        _client_returning(client, [_logprobs(yes=-0.01, no=-5.0) + _logprobs(yes=-5.0, no=-0.01)])
        assert OllamaReranker({"model": "m"}).rerank("q", [{"memory": "d"}])[0]["rerank_score"] == pytest.approx(
            0.0, abs=0.01
        )

    def test_missing_tokens_is_neutral(self, mock_ollama):
        _, client = mock_ollama
        payload = [{"token": "foo", "logprob": -0.1, "top_logprobs": [{"token": "bar", "logprob": -1.0}]}]
        _client_returning(client, [payload])
        assert OllamaReranker({"model": "m"}).rerank("q", [{"memory": "d"}])[0]["rerank_score"] == 0.5

    def test_generate_error_is_neutral(self, mock_ollama):
        _, client = mock_ollama
        client.generate.side_effect = RuntimeError("connection refused")
        assert OllamaReranker({"model": "m"}).rerank("q", [{"memory": "d"}])[0]["rerank_score"] == 0.5


class TestRerank:
    def test_sorted_descending(self, mock_ollama):
        _, client = mock_ollama
        payloads = [_logprobs(yes=-3.0, no=0.0), _logprobs(yes=0.0, no=-3.0), _logprobs(yes=-1.0, no=-1.0)]
        _client_returning(client, payloads)
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
