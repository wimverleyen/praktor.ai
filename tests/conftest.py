"""
Test configuration and shared fixtures.

Sets OTEL_SDK_DISABLED=true before any test module imports opentelemetry.
Without this, the ConsoleSpanExporter (initialized at module load in
observability.py) holds a reference to stdout that gets closed after the
first test, causing "I/O operation on closed file" errors in subsequent
tests when BatchSpanProcessor tries to flush.

Also stubs out heavy dependencies (langchain, langchain_community, etc.) so
the test suite runs without installing the full ML dependency stack.
"""
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, AsyncMock

os.environ.setdefault("OTEL_SDK_DISABLED", "true")

# ---------------------------------------------------------------------------
# Fix faiss.__spec__ before anything else tries to import it.
# faiss (the native extension) sometimes loads with __spec__ = None, which
# causes importlib.util.find_spec("faiss") to raise ValueError.  Replace
# (or pre-register) it with a plain module stub that has a valid __spec__.
# ---------------------------------------------------------------------------
_faiss_stub = types.ModuleType("faiss")
_faiss_stub.__spec__ = importlib.util.spec_from_loader("faiss", loader=None)
sys.modules["faiss"] = _faiss_stub

# ---------------------------------------------------------------------------
# Stub langchain at collection time so modules that import it at module level
# don't fail when langchain isn't installed in the dev environment.
# ---------------------------------------------------------------------------

def _make_langchain_stub():
    stub = MagicMock()
    # PromptTemplate.from_template returns something with .pipe()
    template = MagicMock()
    template.pipe.return_value = MagicMock()
    stub.prompts.PromptTemplate.from_template.return_value = template
    return stub


_STUB_MODULES = [
    "langchain",
    "langchain.prompts",
    "langchain_community",
    "langchain_community.embeddings",
    "langchain_community.vectorstores",
    "langchain_community.document_loaders",
    "langchain_ollama",
    "langchain_ollama.llms",
    "langchain_openai",
    "langchain_openai.llms",
    "langchain_anthropic",
    "langchain.text_splitter",
    # langchain_core submodules that drag in transformers → faiss chain
    "langchain_core",
    "langchain_core.prompts",
    "langchain_core.prompts.base",
    "langchain_core.language_models",
    "langchain_core.language_models.base",
    "langchain_core.output_parsers",
    "langchain_core.output_parsers.base",
    "langchain_core.runnables",
    "langchain_core.messages",
    "transformers",
]

for _mod in _STUB_MODULES:
    if _mod not in sys.modules:
        _s = _make_langchain_stub()
        # Make submodule attributes accessible on parent
        if "." in _mod:
            parent, child = _mod.rsplit(".", 1)
            if parent in sys.modules:
                setattr(sys.modules[parent], child, _s)
        sys.modules[_mod] = _s
