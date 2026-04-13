"""
PII/PHI detector protocol and built-in implementations.

PIIDetector protocol: implement detect(text, entities) -> list[DetectionResult]
RegexDetector: zero-weight, pattern-based, covers common PHI patterns
PresidioDetector: full ML-based PHI detection (pip install praktor[presidio])
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from settings import create_log

log = create_log()

MAX_DETECTOR_CHARS = 100_000
_CHUNK_SIZE = 10_000
_CHUNK_OVERLAP = 200


@dataclass
class DetectionResult:
    entity_type: str
    start: int        # character offset in the input text
    end: int
    score: float      # 0.0–1.0; RegexDetector always returns 1.0
    text: str         # the matched span


@runtime_checkable
class PIIDetector(Protocol):
    async def detect(self, text: str, entities: list[str]) -> list[DetectionResult]:
        """Detect entities in text. Must handle up to MAX_DETECTOR_CHARS chars."""
        ...


# ---------------------------------------------------------------------------
# Regex patterns for common PHI/PII — zero ML deps, instant startup
# ---------------------------------------------------------------------------

_PATTERNS: dict[str, re.Pattern] = {
    "US_SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "PHONE_NUMBER": re.compile(
        r"\b(\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    ),
    "EMAIL_ADDRESS": re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    ),
    "DATE_OF_BIRTH": re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4}\b"
        r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
        r"|\b\d{4}-\d{2}-\d{2}\b"
    ),
    "US_PASSPORT": re.compile(r"\b[A-Z]{1,2}\d{6,9}\b"),
    "CREDIT_CARD": re.compile(
        r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
    ),
}


class RegexDetector:
    """
    Pattern-based PII detector. Zero ML dependencies, instant startup.

    Covers: US_SSN, PHONE_NUMBER, EMAIL_ADDRESS, DATE_OF_BIRTH, US_PASSPORT, CREDIT_CARD.
    Always returns score=1.0 (pattern match = certain).

    For inputs > MAX_DETECTOR_CHARS, processes in overlapping chunks to avoid
    missing matches at chunk boundaries. Character offsets in results are
    relative to the original (full) input string.

    Limitation: lower recall than Presidio for non-pattern PHI (names, addresses).
    For full HIPAA PHI recall, use pip install praktor[presidio].
    """

    async def detect(
        self, text: str, entities: list[str]
    ) -> list[DetectionResult]:
        if len(text) <= MAX_DETECTOR_CHARS:
            return self._scan(text, entities, offset=0)

        # Process in overlapping chunks to catch boundary-spanning matches
        results: list[DetectionResult] = []
        seen_spans: set[tuple[int, int]] = set()
        pos = 0
        while pos < len(text):
            chunk = text[pos: pos + _CHUNK_SIZE + _CHUNK_OVERLAP]
            for r in self._scan(chunk, entities, offset=pos):
                span = (r.start, r.end)
                if span not in seen_spans:
                    seen_spans.add(span)
                    results.append(r)
            pos += _CHUNK_SIZE
        return results

    @staticmethod
    def _scan(
        text: str, entities: list[str], offset: int
    ) -> list[DetectionResult]:
        results: list[DetectionResult] = []
        active = {e: p for e, p in _PATTERNS.items() if e in entities}
        for entity_type, pattern in active.items():
            for match in pattern.finditer(text):
                results.append(DetectionResult(
                    entity_type=entity_type,
                    start=match.start() + offset,
                    end=match.end() + offset,
                    score=1.0,
                    text=match.group(),
                ))
        return results


class PresidioDetector:
    """
    ML-based PII/PHI detector using Microsoft Presidio.

    Requires: pip install praktor[presidio]

    Lazy-loads the spaCy model on first use (~1-3 seconds cold start).
    Cached at module level — not per-request.

    On model load failure: raises DetectorUnavailableError (fails closed).
    """

    _analyzer = None  # Module-level cache

    async def detect(
        self, text: str, entities: list[str]
    ) -> list[DetectionResult]:
        analyzer = self._get_analyzer()
        import asyncio
        results = await asyncio.to_thread(analyzer.analyze, text=text, entities=entities, language="en")
        return [
            DetectionResult(
                entity_type=r.entity_type,
                start=r.start,
                end=r.end,
                score=r.score,
                text=text[r.start:r.end],
            )
            for r in results
        ]

    @classmethod
    def _get_analyzer(cls):
        if cls._analyzer is None:
            try:
                from presidio_analyzer import AnalyzerEngine
                cls._analyzer = AnalyzerEngine()
                log.info("PresidioDetector: analyzer loaded")
            except Exception as e:
                raise DetectorUnavailableError(
                    f"Presidio failed to load: {e}. "
                    "Install with: pip install praktor[presidio]"
                ) from e
        return cls._analyzer


class DetectorUnavailableError(Exception):
    """Raised when a detector cannot initialize (e.g. missing model). Fails closed."""


def load_detector(import_path: str) -> PIIDetector:
    """
    Import a detector class by dotted path and return an instance.

    Example: load_detector("praktor.governance.detectors.RegexDetector")
    """
    parts = import_path.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid detector import path: {import_path!r}")
    module_path, class_name = parts
    import importlib
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls()
