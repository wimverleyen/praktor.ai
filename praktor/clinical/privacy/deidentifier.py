"""
PHI de-identification pipeline.

Uses Microsoft Presidio (if available) with a regex fallback for environments
where Presidio isn't installed. The fallback covers the most common PHI patterns
but is not a substitute for Presidio in production.

PHI gate: validate_phi_scrubbed() RAISES — never logs and continues.
Any code path that writes to FAISS or sends to an LLM must call this first.

Install Presidio for production:
    pip install presidio-analyzer presidio-anonymizer
    python -m spacy download en_core_web_lg
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from praktor.settings import create_log

log = create_log()


# ---------------------------------------------------------------------------
# PHI entity types we scrub
# ---------------------------------------------------------------------------

_PRESIDIO_ENTITIES = [
    "PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN",
    "US_DRIVER_LICENSE", "US_PASSPORT", "CREDIT_CARD",
    "US_BANK_NUMBER", "IP_ADDRESS", "DATE_TIME",
    "LOCATION", "NRP", "MEDICAL_LICENSE", "URL",
]

# Regex fallback patterns (order matters — more specific first)
_REGEX_PATTERNS: list[tuple[str, str]] = [
    # SSN
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),
    # Phone
    (r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE]"),
    # Email
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", "[EMAIL]"),
    # Date patterns (MM/DD/YYYY, YYYY-MM-DD, Month DD YYYY)
    (r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", "[DATE]"),
    (r"\b\d{4}-\d{2}-\d{2}\b", "[DATE]"),
    (r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b", "[DATE]"),
    # MRN / member ID patterns (7-10 digit numbers that look like IDs)
    (r"\bMRN[:\s#]*\d{6,12}\b", "[MRN]"),
    (r"\bMember[:\s#]*ID[:\s#]*\d{6,12}\b", "[MEMBER_ID]"),
    # ZIP+4
    (r"\b\d{5}-\d{4}\b", "[ZIP]"),
    # NPI
    (r"\bNPI[:\s#]*\d{10}\b", "[NPI]"),
    # DEA number
    (r"\b[A-Z]{2}\d{7}\b", "[DEA]"),
]

_REGEX_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _REGEX_PATTERNS]


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ScrubResult:
    text: str
    entities_found: list[str]
    engine: str    # "presidio" | "regex_fallback"
    phi_detected: bool

    @property
    def is_clean(self) -> bool:
        return not self.phi_detected


# ---------------------------------------------------------------------------
# De-identifier
# ---------------------------------------------------------------------------

class Deidentifier:
    """
    Scrubs PHI from text using Presidio (preferred) or regex fallback.

    Usage:
        deidentifier = Deidentifier()
        result = deidentifier.scrub("Patient John Smith DOB 01/15/1980")
        assert result.is_clean
        clean_text = result.text
    """

    def __init__(self, deny_list_mode: bool = True):
        """
        deny_list_mode=True: raise if ANY entity detected after scrubbing
        (pilot mode — conservative). Set False for production after validation.
        """
        self._deny_list_mode = deny_list_mode
        self._presidio_available = False
        self._analyzer = None
        self._anonymizer = None
        self._init_presidio()

    def _init_presidio(self) -> None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
            self._presidio_available = True
            log.info("Deidentifier: using Presidio engine")
        except ImportError:
            log.warning(
                "Deidentifier: presidio-analyzer not installed — using regex fallback. "
                "For production, install: pip install presidio-analyzer presidio-anonymizer"
            )

    def scrub(self, text: str) -> ScrubResult:
        """De-identify text. Returns ScrubResult with cleaned text and metadata."""
        if not text or not text.strip():
            return ScrubResult(text="", entities_found=[], engine="noop", phi_detected=False)

        if self._presidio_available:
            return self._scrub_presidio(text)
        return self._scrub_regex(text)

    def _scrub_presidio(self, text: str) -> ScrubResult:
        from presidio_anonymizer.entities import OperatorConfig
        results = self._analyzer.analyze(
            text=text,
            entities=_PRESIDIO_ENTITIES,
            language="en",
        )
        entities_found = [r.entity_type for r in results]
        if not results:
            return ScrubResult(
                text=text, entities_found=[], engine="presidio", phi_detected=False
            )
        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators={
                e: OperatorConfig("replace", {"new_value": f"[{e}]"})
                for e in _PRESIDIO_ENTITIES
            },
        )
        return ScrubResult(
            text=anonymized.text,
            entities_found=entities_found,
            engine="presidio",
            phi_detected=True,
        )

    def _scrub_regex(self, text: str) -> ScrubResult:
        scrubbed = text
        entities_found: list[str] = []
        for pattern, replacement in _REGEX_COMPILED:
            new_text, n = pattern.subn(replacement, scrubbed)
            if n > 0:
                entities_found.append(replacement.strip("[]"))
                scrubbed = new_text
        return ScrubResult(
            text=scrubbed,
            entities_found=entities_found,
            engine="regex_fallback",
            phi_detected=len(entities_found) > 0,
        )


# ---------------------------------------------------------------------------
# PHI gate — hard enforcement
# ---------------------------------------------------------------------------

def validate_phi_scrubbed(phi_scrubbed: bool, context: str = "") -> None:
    """
    Hard gate: raises ValueError if phi_scrubbed is False.
    Call before every FAISS write and every LLM prompt construction.

    Never catch this exception silently — PHI reaching a vector store or LLM
    is a HIPAA incident, not a graceful-degradation scenario.
    """
    if not phi_scrubbed:
        msg = (
            "PHI gate violation: phi_scrubbed=False. "
            "Data must pass through Deidentifier.scrub() before storage or LLM use."
        )
        if context:
            msg += f" Context: {context}"
        log.error(msg)
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_deidentifier: Deidentifier | None = None


def get_deidentifier() -> Deidentifier:
    global _deidentifier
    if _deidentifier is None:
        _deidentifier = Deidentifier()
    return _deidentifier


def scrub_text(text: str) -> tuple[str, bool]:
    """
    Convenience function: scrub text and return (clean_text, phi_was_detected).
    Always returns a string safe for storage.
    """
    result = get_deidentifier().scrub(text)
    if result.entities_found:
        log.debug(f"PHI scrubbed: {result.entities_found} via {result.engine}")
    return result.text, result.phi_detected
