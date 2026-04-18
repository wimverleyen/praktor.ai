"""
Audit logging with append-only hash-chained entries.

AuditEntry: one entry per agent execution. Includes governance actions taken,
evaluation scores, OTel trace correlation, and a SHA-256 chain link to the
previous entry. Chain integrity makes silent tampering detectable.

LocalFileAuditSink: writes to a local JSONL file with filelock-based
concurrent-write safety. Documented throughput limit: CONCURRENCY <= 8.
Above that, use KafkaSink (Phase 2).

StdoutAuditSink: for development and testing.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Protocol

from settings import CONCURRENCY, create_log

log = create_log()

_DEFAULT_AUDIT_LOG = os.getenv("PRAKTOR_AUDIT_LOG", "praktor_audit.jsonl")
_MAX_FILE_BYTES = int(os.getenv("PRAKTOR_AUDIT_MAX_BYTES", str(100 * 1024 * 1024)))  # 100 MB


@dataclass
class AuditEntry:
    """
    One immutable record per agent execution.

    prompt_hash and response_hash store SHA-256 digests only — never the raw
    text. This satisfies HIPAA minimum-necessary principles (PHI not stored in
    audit logs) while preserving integrity verification capability.

    governance_actions: list of {detector_class, entity_type, action, count}
        ALLOW actions produce NO entry here (governance_actions stays empty).
    evaluation_scores: list of {evaluator_class, metric_name, score, pass}
        Empty in Phase 1 (EvaluationPass execution wired in Phase 2).

    Hash-chaining: previous_entry_hash = SHA-256 of the prior serialized entry.
    First entry ever: previous_entry_hash = "genesis".
    After log rotation: new file starts fresh with "genesis".
    """
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    agent_type: str = ""
    session_id: str = ""
    caller_identity: str = "anonymous"
    model: str = ""
    prompt_hash: str = ""
    response_hash: str = ""
    governance_actions: list[dict] = field(default_factory=list)
    evaluation_scores: list[dict] = field(default_factory=list)
    duration_ms: float = 0.0
    token_count: int = 0
    flagged: bool = False
    otel_trace_id: str = ""
    previous_entry_hash: str = "genesis"

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def serialize(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    def entry_hash(self) -> str:
        return hashlib.sha256(self.serialize().encode()).hexdigest()


class AuditSink(Protocol):
    async def write(self, entry: AuditEntry) -> None:
        ...


class StdoutAuditSink:
    """Writes audit entries to stdout. For development and testing."""
    async def write(self, entry: AuditEntry) -> None:
        sys.stdout.write(f"AUDIT {entry.serialize()}\n")
        sys.stdout.flush()


class LocalFileAuditSink:
    """
    Append-only JSONL audit log with hash-chaining.

    Concurrent write safety: uses filelock to serialize writes.
    Throughput note: file locking serializes all writes. Suitable for
    CONCURRENCY <= 8. For higher throughput, use KafkaSink (Phase 2).

    Log rotation: when the file exceeds _MAX_FILE_BYTES, it is renamed
    with a timestamp suffix. The new file starts a fresh chain (genesis).
    A rotation event is appended as the final entry of the old file.

    Restart continuity: on first write, reads the last line of the existing
    log file to obtain the current chain tip.
    """

    def __init__(self, log_path: str = _DEFAULT_AUDIT_LOG) -> None:
        self._path = Path(log_path)
        self._chain_tip: str | None = None  # Lazily loaded

        if CONCURRENCY > 8:
            log.warning(
                f"LocalFileAuditSink: PRAKTOR_CONCURRENCY={CONCURRENCY} > 8. "
                "File locking may become a write bottleneck. "
                "Consider switching to KafkaSink for high-throughput deployments."
            )

    def _get_lock(self):
        from filelock import FileLock
        return FileLock(str(self._path) + ".lock")

    def _read_chain_tip(self) -> str:
        """Read the last entry's hash from disk to resume the chain."""
        if not self._path.exists():
            return "genesis"
        try:
            last_line = None
            with open(self._path, "rb") as f:
                # Efficiently seek to last line
                try:
                    f.seek(-2, 2)
                    while f.read(1) != b"\n":
                        f.seek(-2, 1)
                except OSError:
                    f.seek(0)
                last_line = f.readline().decode().strip()
            if last_line:
                data = json.loads(last_line)
                # Reconstruct hash of the last entry
                entry = AuditEntry(**{k: v for k, v in data.items() if k in AuditEntry.__dataclass_fields__})
                return entry.entry_hash()
        except Exception as e:
            log.warning(f"LocalFileAuditSink: could not read chain tip: {e}. Starting fresh.")
        return "genesis"

    def _maybe_rotate(self) -> None:
        """Rotate the log file if it exceeds the size limit."""
        if not self._path.exists():
            return
        if self._path.stat().st_size < _MAX_FILE_BYTES:
            return

        import shutil
        timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        rotated = self._path.with_name(f"{self._path.stem}.{timestamp}{self._path.suffix}")
        # Write rotation event as final entry
        rotation_record = json.dumps({
            "entry_type": "rotation",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "next_file": str(self._path),
            "previous_entry_hash": self._chain_tip or "genesis",
        })
        try:
            with open(self._path, "a") as f:
                f.write(rotation_record + "\n")
            shutil.move(str(self._path), str(rotated))
            self._chain_tip = "genesis"
            log.info(f"LocalFileAuditSink: rotated to {rotated}")
        except Exception as e:
            log.error(f"LocalFileAuditSink: rotation failed: {e}")

    async def write(self, entry: AuditEntry) -> None:
        """
        Write one audit entry. Thread-safe via filelock.

        On disk-full: logs error to stderr, never silently drops the entry
        or crashes the agent. The agent continues; the audit gap is visible
        in the log.
        """
        lock = self._get_lock()
        try:
            with lock:
                # Lazy-load chain tip on first write
                if self._chain_tip is None:
                    self._chain_tip = self._read_chain_tip()

                self._maybe_rotate()
                entry.previous_entry_hash = self._chain_tip

                line = entry.serialize() + "\n"
                with open(self._path, "a") as f:
                    f.write(line)

                self._chain_tip = entry.entry_hash()
                log.debug(f"AuditEntry written: {entry.entry_id} agent={entry.agent_type}")

        except OSError as e:
            # Disk full or permission error — never crash the agent
            log.error(
                f"LocalFileAuditSink: WRITE FAILED for entry {entry.entry_id}: {e}. "
                "Audit entry dropped. Check disk space and file permissions.",
                exc_info=True,
            )
            sys.stderr.write(
                f"PRAKTOR AUDIT ERROR: entry {entry.entry_id} dropped: {e}\n"
            )
        except Exception as e:
            log.error(f"LocalFileAuditSink: unexpected error: {e}", exc_info=True)
