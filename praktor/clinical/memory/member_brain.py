"""
Per-member FAISS second brain — Karpathy architecture for clinical reasoning.

Each member gets a dedicated FAISS shard at:
    VECTOR_DB/members/{member_id_hash}/

LRU cache keeps the N most recently accessed shards hot in memory.
Shards are created only by the ingestion pipeline — never lazily at query time.

Three-layer retrieval (in order):
    1. Member-specific shard — this patient's longitudinal history
    2. Cohort shard (shared) — population-level patterns for similar members
    3. Literature shard (shared) — clinical evidence base

Usage:
    brain = MemberBrain()
    chunks = await brain.retrieve(member_id_hash, query="statin adherence barriers")
    brain.add_chunk(chunk)  # ingestion only — raises in agent context
"""

from __future__ import annotations

import asyncio
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any

from settings import MODEL, VECTOR_DB, create_log
from clinical.privacy.deidentifier import validate_phi_scrubbed
from clinical.privacy.audit import audit
from clinical.schemas import ClinicalBrainChunk

log = create_log()

_LRU_MAX_SHARDS = int(os.getenv("PRAKTOR_BRAIN_CACHE_SIZE", "128"))
_SHARED_COHORT_SHARD = "cohort"
_SHARED_LITERATURE_SHARD = "literature"


def _shard_path(base_dir: str, shard_id: str) -> Path:
    return Path(base_dir) / "members" / shard_id


class MemberBrain:
    """
    Per-member FAISS shard manager with LRU eviction.

    Thread-safe for concurrent reads. Ingestion writes must happen outside
    the agent event loop (in scripts/init_member_brain.py).
    """

    def __init__(
        self,
        base_dir: str | None = None,
        embeddings_model: str = MODEL,
        k: int = 5,
    ) -> None:
        self._base_dir = base_dir or VECTOR_DB or str(Path.home() / ".praktor" / "vector_db")
        self._embeddings_model = embeddings_model
        self._k = k
        # LRU cache: member_id_hash → FAISS store object
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._embeddings: Any = None
        self._cohort_store: Any = None
        self._literature_store: Any = None
        self._init_embeddings()
        self._init_shared_shards()

    def _init_embeddings(self) -> None:
        try:
            from langchain_community.embeddings import OllamaEmbeddings
            self._embeddings = OllamaEmbeddings(model=self._embeddings_model)
        except Exception as e:
            log.warning(f"MemberBrain: embeddings init failed ({e}) — retrieval unavailable")

    def _init_shared_shards(self) -> None:
        for shard_id, attr in [
            (_SHARED_COHORT_SHARD, "_cohort_store"),
            (_SHARED_LITERATURE_SHARD, "_literature_store"),
        ]:
            path = Path(self._base_dir) / shard_id
            if path.exists():
                try:
                    from langchain_community.vectorstores import FAISS
                    store = FAISS.load_local(
                        str(path), self._embeddings,
                        allow_dangerous_deserialization=True,
                    )
                    setattr(self, attr, store)
                    log.info(f"MemberBrain: loaded shared shard '{shard_id}'")
                except Exception as e:
                    log.warning(f"MemberBrain: shared shard '{shard_id}' failed to load: {e}")

    # ------------------------------------------------------------------
    # Retrieval (async, agent-safe)
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        member_id_hash: str,
        query: str,
        k: int | None = None,
        include_cohort: bool = True,
        include_literature: bool = False,
    ) -> list[dict]:
        """
        Three-layer retrieval. Returns list of {role, content, source} dicts.
        Never raises — degrades gracefully if shards are missing.
        """
        if not query or not self._embeddings:
            return []

        n = k or self._k
        results: list[dict] = []

        # Layer 1: member-specific shard
        member_store = await asyncio.to_thread(self._load_member_shard, member_id_hash)
        if member_store:
            docs = await asyncio.to_thread(
                member_store.similarity_search, query, k=n
            )
            for doc in docs:
                results.append({
                    "role": "context",
                    "content": doc.page_content,
                    "source": "member_history",
                })
            audit(
                "faiss_read", f"retrieve query='{query[:40]}'",
                member_id_hash=member_id_hash,
                details={"layer": "member", "hits": len(docs)},
            )

        # Layer 2: cohort shard (population patterns)
        if include_cohort and self._cohort_store and len(results) < n:
            try:
                docs = await asyncio.to_thread(
                    self._cohort_store.similarity_search, query, k=max(1, n - len(results))
                )
                for doc in docs:
                    results.append({
                        "role": "context",
                        "content": doc.page_content,
                        "source": "cohort_patterns",
                    })
            except Exception as e:
                log.warning(f"MemberBrain: cohort retrieval failed: {e}")

        # Layer 3: clinical literature
        if include_literature and self._literature_store and len(results) < n:
            try:
                docs = await asyncio.to_thread(
                    self._literature_store.similarity_search, query, k=2
                )
                for doc in docs:
                    results.append({
                        "role": "context",
                        "content": doc.page_content,
                        "source": "clinical_literature",
                    })
            except Exception as e:
                log.warning(f"MemberBrain: literature retrieval failed: {e}")

        return results

    # ------------------------------------------------------------------
    # Ingestion (sync — called from scripts only, not agent loop)
    # ------------------------------------------------------------------

    def add_chunk(self, chunk: ClinicalBrainChunk) -> None:
        """
        Add a document chunk to the member's FAISS shard.
        PHI gate: raises ValueError if phi_scrubbed=False.
        Must be called from ingestion scripts, not from within agent.run().
        """
        validate_phi_scrubbed(chunk.phi_scrubbed, context=f"add_chunk member={chunk.member_id_hash[:8]}")

        if not self._embeddings:
            log.warning("MemberBrain: cannot add chunk — embeddings unavailable")
            return

        try:
            from langchain.schema import Document
            from langchain_community.vectorstores import FAISS

            doc = Document(
                page_content=chunk.content,
                metadata={
                    "member_id_hash": chunk.member_id_hash,
                    "source_type": chunk.source_type,
                    "date": chunk.date,
                    "icd_codes": ",".join(chunk.icd_codes),
                    "cpt_codes": ",".join(chunk.cpt_codes),
                    "phi_scrubbed": str(chunk.phi_scrubbed),
                    "provenance": chunk.provenance,
                },
            )

            shard_dir = _shard_path(self._base_dir, chunk.member_id_hash)
            shard_dir.mkdir(parents=True, exist_ok=True)

            if shard_dir.exists() and (shard_dir / "index.faiss").exists():
                # Load existing, add, save
                existing = FAISS.load_local(
                    str(shard_dir), self._embeddings,
                    allow_dangerous_deserialization=True,
                )
                existing.add_documents([doc])
                existing.save_local(str(shard_dir))
                # Evict from LRU cache so next read gets fresh version
                self._cache.pop(chunk.member_id_hash, None)
            else:
                store = FAISS.from_documents([doc], self._embeddings)
                store.save_local(str(shard_dir))

            audit(
                "faiss_write", f"add_chunk source_type={chunk.source_type}",
                member_id_hash=chunk.member_id_hash,
                details={"source_type": chunk.source_type, "date": chunk.date},
            )
        except Exception as e:
            log.error(f"MemberBrain.add_chunk failed: {e}")
            raise

    # ------------------------------------------------------------------
    # LRU shard loader
    # ------------------------------------------------------------------

    def _load_member_shard(self, member_id_hash: str) -> Any | None:
        """
        Load member FAISS shard with LRU eviction.
        Returns None if shard doesn't exist — agent degrades gracefully.
        """
        if member_id_hash in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(member_id_hash)
            return self._cache[member_id_hash]

        shard_dir = _shard_path(self._base_dir, member_id_hash)
        if not shard_dir.exists() or not (shard_dir / "index.faiss").exists():
            log.debug(f"MemberBrain: shard missing for {member_id_hash[:8]} — run ingestion pipeline")
            return None

        try:
            from langchain_community.vectorstores import FAISS
            store = FAISS.load_local(
                str(shard_dir), self._embeddings,
                allow_dangerous_deserialization=True,
            )
            # LRU: evict oldest if at capacity
            if len(self._cache) >= _LRU_MAX_SHARDS:
                evicted, _ = self._cache.popitem(last=False)
                log.debug(f"MemberBrain: evicted shard {evicted[:8]} from LRU cache")

            self._cache[member_id_hash] = store
            self._cache.move_to_end(member_id_hash)
            return store
        except Exception as e:
            log.error(f"MemberBrain: failed to load shard {member_id_hash[:8]}: {e}")
            return None

    def shard_exists(self, member_id_hash: str) -> bool:
        shard_dir = _shard_path(self._base_dir, member_id_hash)
        return (shard_dir / "index.faiss").exists()

    @property
    def cache_size(self) -> int:
        return len(self._cache)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_brain: MemberBrain | None = None


def get_member_brain() -> MemberBrain:
    global _brain
    if _brain is None:
        _brain = MemberBrain()
    return _brain
