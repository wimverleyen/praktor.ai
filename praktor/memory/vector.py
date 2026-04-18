from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Any

from settings import MODEL, VECTOR_DB, create_log

log = create_log()


class FAISSMemory:
    """
    Long-term semantic memory backed by a FAISS vector store.

    Uses similarity search to retrieve the most relevant context chunks
    for a given query. Replaces RAGTY / RAGSP from retrieve_generate.py.

    Seed the store first:
        python scripts/init_vector_db.py

    Gracefully degrades if the store doesn't exist — returns empty history.
    """

    def __init__(self, db_path: str | None = None, embeddings_model: str = MODEL, k: int = 5):
        self._k = k
        self._available = False
        self._store: Any = None

        path = db_path or VECTOR_DB
        if not path or not Path(path).exists():
            log.warning(
                f"FAISSMemory: store not found at '{path}'. "
                "Long-term memory unavailable. Run scripts/init_vector_db.py to seed."
            )
            return

        try:
            from langchain_community.embeddings import OllamaEmbeddings
            from langchain_community.vectorstores import FAISS

            embeddings = OllamaEmbeddings(model=embeddings_model)
            self._store = FAISS.load_local(
                path, embeddings, allow_dangerous_deserialization=True
            )
            self._available = True
            log.info(f"FAISSMemory loaded from {path}")
        except Exception as e:
            log.error(f"FAISSMemory: failed to load store from {path}: {e}")

    async def load(self, session_id: str, query: str = "", k: int | None = None) -> list[dict]:
        """
        Retrieve relevant documents for query via similarity search.
        session_id is accepted for protocol compatibility but unused
        (the store is global, not per-session).
        """
        if not self._available or not query:
            return []

        n = k or self._k
        try:
            docs = await asyncio.to_thread(self._store.similarity_search, query, k=n)
            return [{"role": "context", "content": d.page_content} for d in docs]
        except Exception as e:
            log.error(f"FAISSMemory.load failed: {e}")
            return []

    async def save(self, session_id: str, turn: dict) -> None:
        # Phase 2: optionally index new content into FAISS at runtime
        pass

    async def clear(self, session_id: str) -> None:
        pass

    @property
    def available(self) -> bool:
        return self._available
