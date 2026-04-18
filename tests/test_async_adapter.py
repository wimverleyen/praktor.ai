import sys
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent / 'praktor'))

import pytest


class TestAsyncLLMAdapter:
    """Tests for AsyncLLMAdapter — mocks LLMFactory to avoid needing Ollama."""

    def _make_adapter(self, template="Answer: {question}", model="qwen2.5"):
        with patch("LLM.llm_interface.LLMFactory") as mock_factory_cls:
            mock_llm = MagicMock()
            mock_factory_cls.return_value.create_llm.return_value = mock_llm
            from LLM.llm_interface import AsyncLLMAdapter
            adapter = AsyncLLMAdapter(prompt_template=template, model=model)
            adapter._llm = mock_llm
            return adapter, mock_llm

    @pytest.mark.asyncio
    async def test_ainvoke_returns_string(self):
        adapter, mock_llm = self._make_adapter()

        with patch("LLM.llm_interface._invoke_with_retry", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = "Paris is the capital of France."
            result = await adapter.ainvoke({"question": "Capital of France?"})

        assert result == "Paris is the capital of France."

    @pytest.mark.asyncio
    async def test_ainvoke_uses_cache_on_second_call(self):
        adapter, mock_llm = self._make_adapter()

        fresh_cache: dict = {}

        def _cache_get(key, default=None):
            return fresh_cache.get(key, default)

        def _cache_set(key, value, **kwargs):
            fresh_cache[key] = value

        with patch("LLM.llm_interface._invoke_with_retry", new_callable=AsyncMock) as mock_retry, \
             patch("LLM.llm_interface._cache") as mock_cache:
            mock_cache.get.side_effect = _cache_get
            mock_cache.set.side_effect = _cache_set
            mock_retry.return_value = "Cached response"
            # First call — cache miss, hits retry
            r1 = await adapter.ainvoke({"question": "Same question?"})
            # Second call — should hit in-memory cache
            r2 = await adapter.ainvoke({"question": "Same question?"})

        assert r1 == r2 == "Cached response"
        assert mock_retry.call_count == 1  # Only called once; second was cached

    @pytest.mark.asyncio
    async def test_astream_yields_chunks(self):
        adapter, mock_llm = self._make_adapter()

        async def _fake_astream(input):
            for word in ["Hello", " ", "world"]:
                yield MagicMock(content=word)

        adapter._chain = MagicMock()
        adapter._chain.astream = _fake_astream

        chunks = []
        async for chunk in adapter.astream({"question": "Greeting?"}):
            chunks.append(chunk)

        assert "".join(chunks) == "Hello world"

    @pytest.mark.asyncio
    async def test_astream_fallback_on_not_implemented(self):
        adapter, mock_llm = self._make_adapter()

        async def _fail_astream(input):
            raise NotImplementedError("No streaming support")
            yield  # make it an async generator

        adapter._chain = MagicMock()
        adapter._chain.astream = _fail_astream

        with patch("LLM.llm_interface._invoke_with_retry", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = "Fallback response"
            chunks = []
            async for chunk in adapter.astream({"question": "Test?"}):
                chunks.append(chunk)

        assert "".join(chunks) == "Fallback response"

    @pytest.mark.asyncio
    async def test_cache_disabled_for_nonzero_temperature(self):
        with patch("LLM.llm_interface.LLMFactory") as mock_factory_cls:
            mock_factory_cls.return_value.create_llm.return_value = MagicMock()
            from LLM.llm_interface import AsyncLLMAdapter
            adapter = AsyncLLMAdapter(
                prompt_template="Answer: {question}",
                model="qwen2.5",
                temperature=0.7,
            )

        assert adapter._use_cache is False
