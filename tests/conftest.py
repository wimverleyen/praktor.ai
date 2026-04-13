"""
Test configuration and shared fixtures.

Stubs out heavy dependencies (langchain, langchain_community, etc.) so the
test suite runs without installing the full ML dependency stack. Tests that
mock agent.run() or adapter.astream() never reach these imports at runtime.
"""
import sys
from unittest.mock import MagicMock, AsyncMock

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
    "langchain_anthropic",
    "langchain.text_splitter",
    "faiss",
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
