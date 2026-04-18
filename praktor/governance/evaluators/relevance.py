"""
EmbeddingRelevanceEvaluator — cosine similarity between prompt and response embeddings.

Requires a running Ollama instance with an embedding-capable model.
Uses langchain_ollama for embeddings. Falls back to raising
EvaluatorUnavailableError if Ollama is unreachable.

Score: 1.0 = perfect semantic match. 0.0 = completely unrelated.
"""
from __future__ import annotations

import asyncio
import math

from praktor.settings import create_log

log = create_log()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingRelevanceEvaluator:
    """
    Cosine similarity evaluator using Ollama embeddings.

    Lazy-loads OllamaEmbeddings on first call. Cached at instance level.
    If Ollama is unreachable, raises EvaluatorUnavailableError (fail-closed).

    Latency note: two embedding calls per evaluation. On CPU-only Ollama,
    expect 200ms-2s depending on model and text length.
    """

    metric_name: str = "relevance"
    _embeddings = None

    def _get_embeddings(self):
        if self._embeddings is None:
            try:
                from langchain_ollama import OllamaEmbeddings
                self._embeddings = OllamaEmbeddings(model="qwen2.5")
                log.info("EmbeddingRelevanceEvaluator: embeddings model loaded")
            except Exception as e:
                from praktor.governance.evaluators import EvaluatorUnavailableError
                raise EvaluatorUnavailableError(
                    f"Ollama embeddings unavailable: {e}. "
                    "Ensure Ollama is running with an embedding-capable model."
                ) from e
        return self._embeddings

    async def score(self, prompt: str, response: str) -> float:
        embeddings = self._get_embeddings()
        try:
            prompt_emb, response_emb = await asyncio.gather(
                asyncio.to_thread(embeddings.embed_query, prompt),
                asyncio.to_thread(embeddings.embed_query, response),
            )
        except Exception as e:
            from praktor.governance.evaluators import EvaluatorUnavailableError
            raise EvaluatorUnavailableError(
                f"Embedding call failed: {e}. Is Ollama running?"
            ) from e

        similarity = _cosine_similarity(prompt_emb, response_emb)
        # Clamp to [0.0, 1.0] (cosine similarity can be negative)
        result = max(0.0, min(1.0, similarity))

        log.debug(f"EmbeddingRelevanceEvaluator: similarity={result:.3f}")
        return result
