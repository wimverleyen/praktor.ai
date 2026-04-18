from __future__ import annotations
import asyncio
import hashlib
import diskcache
from contextlib import contextmanager
from typing import AsyncGenerator, Any

from langchain_core.prompts import PromptTemplate

from settings import MODEL, CACHE_DIR, CACHE_TTL, create_log
from LLM.llm_factory import LLMFactory

log = create_log()

# Shared prompt-response cache (temperature=0 calls only)
_cache = diskcache.Cache(CACHE_DIR)


async def _invoke_with_retry(chain, data: dict, max_attempts: int = 3) -> str:
    """Run a LangChain chain synchronously in a thread pool with exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            result = await asyncio.to_thread(chain.invoke, data)
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            last_error = e
            if attempt < max_attempts - 1:
                wait = 2 ** attempt  # 1s, 2s
                log.warning(f"LLM invoke attempt {attempt + 1}/{max_attempts} failed: {e}. Retrying in {wait}s.")
                await asyncio.sleep(wait)
    raise RuntimeError(
        f"LLM invoke failed after {max_attempts} attempts: {last_error}"
    )


# ---------------------------------------------------------------------------
# Legacy synchronous adapter — kept for backwards compatibility.
# New agent definitions should use AsyncLLMAdapter below.
# ---------------------------------------------------------------------------

class LLMAdapter:
    """
    Synchronous LLM adapter (legacy).

    Wraps a LangChain LCEL chain built from a PromptTemplate + OllamaLLM.
    Still used by the legacy agent_method.py handlers.
    """

    def __init__(self, prompt_method, temperature=0.0):
        from langchain_ollama.llms import OllamaLLM
        self.__prompt = prompt_method
        self.__llm = OllamaLLM(model=MODEL, temperature=temperature)
        self.__chain = self.__prompt | self.__llm

    def update(self, prompt_method):
        self.__prompt = prompt_method
        self.__chain = self.__prompt | self.__llm

    def generate(self, data={}):
        try:
            log.debug(f'generate: prompt variables: {self.__prompt.input_variables}')
            response = self.__chain.invoke(input=data)
        except Exception as e:
            response = {'error': str(e)}
        return response


# ---------------------------------------------------------------------------
# New async adapter — used by all AgentDefinition-based agents.
# ---------------------------------------------------------------------------

class AsyncLLMAdapter:
    """
    Async-first LLM adapter with streaming, retry, and prompt-response caching.

    Key improvements over LLMAdapter:
    - Uses LLMFactory to support any model (Ollama, OpenAI, Claude)
    - astream() yields token chunks as they arrive
    - ainvoke() retries up to 3x with exponential backoff
    - Caches responses for temperature=0 calls (keyed on model + prompt text)
    - Prompt template compiled once at construction, not per call
    """

    def __init__(
        self,
        prompt_template: str,
        model: str = MODEL,
        temperature: float = 0.0,
    ):
        self._model = model
        self._temperature = temperature
        self._use_cache = temperature == 0.0
        self._prompt = PromptTemplate.from_template(prompt_template)
        self._llm = LLMFactory().create_llm(model)
        self._chain = self._prompt | self._llm

    def _cache_key(self, data: dict) -> str:
        """SHA256 of model + rendered prompt text."""
        try:
            prompt_text = self._prompt.format(
                **{k: v for k, v in data.items() if k in self._prompt.input_variables}
            )
        except Exception:
            prompt_text = str(data)
        return hashlib.sha256(f"{self._model}:{prompt_text}".encode()).hexdigest()

    def render(self, data: dict) -> str:
        """
        Return the fully rendered prompt string.

        Useful for debugging, logging, and any caller that needs to inspect
        the exact text the LLM will see before calling astream().
        """
        try:
            return self._prompt.format(
                **{k: v for k, v in data.items() if k in self._prompt.input_variables}
            )
        except Exception:
            return str(data)

    async def ainvoke(self, data: dict, call_span: Any = None) -> str:
        """
        Single blocking call with retry. Returns full response string.

        call_span: optional LLMCallSpan context manager from core.observability.
                   If provided, latency and cache status are recorded on it.
        """
        if self._use_cache:
            key = self._cache_key(data)
            cached = _cache.get(key)
            if cached is not None:
                log.debug(f"Cache hit [{self._model}]")
                if call_span is not None:
                    call_span.cached = True
                    call_span.output_tokens = len(cached.split())
                return cached

        result = await _invoke_with_retry(self._chain, data)

        if self._use_cache:
            _cache.set(key, result, expire=CACHE_TTL)

        if call_span is not None:
            call_span.output_tokens = len(result.split())

        return result

    async def astream(self, data: dict, call_span: Any = None) -> AsyncGenerator[str, None]:
        """
        Yield token chunks as they arrive from the LLM.

        Cache hit: yields the full cached response as a single chunk.
        Cache miss: streams natively via LCEL astream(); falls back to
                    thread-pool invoke if the LLM doesn't support streaming.

        call_span: optional LLMCallSpan context manager from core.observability.
                   If provided, token count and cache status are recorded on it.
        """
        if self._use_cache:
            key = self._cache_key(data)
            cached = _cache.get(key)
            if cached is not None:
                log.debug(f"Cache hit (stream) [{self._model}]")
                if call_span is not None:
                    call_span.cached = True
                    call_span.output_tokens = len(cached.split())
                yield cached
                return

        full_response: list[str] = []

        try:
            async for chunk in self._chain.astream(input=data):
                text = chunk.content if hasattr(chunk, "content") else str(chunk)
                if text:
                    full_response.append(text)
                    yield text
        except (NotImplementedError, AttributeError, TypeError):
            # LLM doesn't natively support astream — fall back to thread pool
            log.debug(f"astream not supported for {self._model}, falling back to ainvoke")
            result = await _invoke_with_retry(self._chain, data)
            full_response.append(result)
            yield result

        if full_response:
            joined = "".join(full_response)
            if call_span is not None:
                call_span.output_tokens = len(joined.split())
            if self._use_cache:
                _cache.set(self._cache_key(data), joined, expire=CACHE_TTL)
