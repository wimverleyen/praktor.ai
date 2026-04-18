"""
Evidence blob utilities for AIGov ObligationEvents.

All obligations use make_evidence() to produce a (bytes, sha256_hex) pair.
The bytes are written to MinIO or local filesystem; the sha256_hex goes into
ObligationEvent.evidence.sha256.

Canonical form: JSON with sorted keys and no extra whitespace, UTF-8 encoded.
This ensures the same logical content always produces the same hash regardless
of which obligation emitted it.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def make_evidence(content: dict[str, Any]) -> tuple[bytes, str]:
    """
    Serialize content to canonical JSON and return (bytes, sha256_hex).

    Always use this function — never call json.dumps() directly for evidence blobs.
    Consistent serialization is required for cross-system hash verification.

    Args:
        content: Evidence payload dict. May include redacted fields, check traces,
                 detector results, scores, etc. Must be JSON-serializable.

    Returns:
        (canonical_bytes, sha256_hex) — write bytes to storage, store sha256_hex
        in ObligationEvent.evidence.sha256.
    """
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)
    evidence_bytes = canonical.encode("utf-8")
    sha256_hex = hashlib.sha256(evidence_bytes).hexdigest()
    return evidence_bytes, sha256_hex
