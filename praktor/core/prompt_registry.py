"""
Prompt version registry — file-based storage for prompt templates.

Each agent has its own JSONL file at PROMPT_STORE_DIR/{agent_name}.jsonl.
One line = one version. The active version is marked with is_active=true.

Usage:
    registry = PromptRegistry()
    v = registry.save("cover_letter", template="...", notes="initial")
    registry.set_active("cover_letter", v.version_id)
    active = registry.get_active("cover_letter")
    print(registry.diff("cover_letter", v1_id, v2_id))
"""

from __future__ import annotations

import hashlib
import json
import os
import difflib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from praktor.settings import create_log

log = create_log()

_DEFAULT_STORE = os.getenv("PROMPT_STORE_DIR", str(Path.home() / ".praktor" / "prompts"))


@dataclass
class PromptVersion:
    """A single immutable snapshot of a prompt template."""
    version_id: str          # sha256[:12] of the template text
    agent_name: str
    template: str
    created_at: str          # ISO 8601 UTC
    notes: str = ""
    is_active: bool = False
    avg_score: float | None = None   # running mean from judge evaluations
    eval_count: int = 0
    avg_latency_ms: float | None = None

    def short_id(self) -> str:
        return self.version_id[:8]

    def summary(self) -> str:
        score_str = f"{self.avg_score:.1f}/10" if self.avg_score is not None else "—"
        active_str = " [active]" if self.is_active else ""
        return (
            f"{self.short_id()}  {self.created_at[:10]}  "
            f"score={score_str}  evals={self.eval_count}"
            f"{active_str}  {self.notes[:40]}"
        )


class PromptRegistry:
    """
    File-based prompt version store.

    One JSONL file per agent at {store_dir}/{agent_name}.jsonl.
    Append-only writes; set_active rewrites the file to update the flag.
    """

    def __init__(self, store_dir: str | None = None):
        self._store = Path(store_dir or _DEFAULT_STORE)
        self._store.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(
        self,
        agent_name: str,
        template: str,
        notes: str = "",
        set_active: bool = False,
    ) -> PromptVersion:
        """
        Save a prompt template as a new version.

        If a version with the same content already exists, returns it
        without creating a duplicate.
        """
        version_id = hashlib.sha256(template.encode()).hexdigest()[:12]
        existing = self._load_all(agent_name)

        for v in existing:
            if v.version_id == version_id:
                log.debug(f"PromptRegistry: version {version_id} already exists for '{agent_name}'")
                return v

        version = PromptVersion(
            version_id=version_id,
            agent_name=agent_name,
            template=template,
            created_at=datetime.now(timezone.utc).isoformat(),
            notes=notes,
            is_active=False,
        )
        self._append(agent_name, version)
        log.info(f"PromptRegistry: saved {version_id} for '{agent_name}'")

        if set_active:
            self.set_active(agent_name, version_id)
            version.is_active = True

        return version

    def set_active(self, agent_name: str, version_id: str) -> None:
        """Mark one version as active, clearing the flag on all others."""
        versions = self._load_all(agent_name)
        found = False
        for v in versions:
            v.is_active = v.version_id == version_id
            if v.is_active:
                found = True

        if not found:
            raise KeyError(f"Version '{version_id}' not found for agent '{agent_name}'")

        self._rewrite(agent_name, versions)
        log.info(f"PromptRegistry: activated {version_id} for '{agent_name}'")

    def record_eval(
        self,
        agent_name: str,
        version_id: str,
        score: float,
        latency_ms: float,
    ) -> None:
        """Update running average score and latency for a version."""
        versions = self._load_all(agent_name)
        for v in versions:
            if v.version_id == version_id:
                n = v.eval_count
                v.avg_score = ((v.avg_score or 0.0) * n + score) / (n + 1)
                v.avg_latency_ms = (
                    ((v.avg_latency_ms or 0.0) * n + latency_ms) / (n + 1)
                )
                v.eval_count += 1
                break
        self._rewrite(agent_name, versions)

    def delete(self, agent_name: str, version_id: str) -> None:
        """Remove a version. Active versions cannot be deleted."""
        versions = self._load_all(agent_name)
        target = next((v for v in versions if v.version_id == version_id), None)
        if target is None:
            raise KeyError(f"Version '{version_id}' not found")
        if target.is_active:
            raise ValueError("Cannot delete the active version. Activate another first.")
        self._rewrite(agent_name, [v for v in versions if v.version_id != version_id])

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list(self, agent_name: str) -> list[PromptVersion]:
        """Return all versions for an agent, newest first."""
        return sorted(
            self._load_all(agent_name),
            key=lambda v: v.created_at,
            reverse=True,
        )

    def get(self, agent_name: str, version_id: str) -> PromptVersion:
        """Retrieve a specific version by ID (prefix match supported)."""
        versions = self._load_all(agent_name)
        matches = [v for v in versions if v.version_id.startswith(version_id)]
        if not matches:
            raise KeyError(f"Version '{version_id}' not found for agent '{agent_name}'")
        if len(matches) > 1:
            raise ValueError(f"Ambiguous prefix '{version_id}' — matches: {[v.version_id for v in matches]}")
        return matches[0]

    def get_active(self, agent_name: str) -> PromptVersion | None:
        """Return the currently active version, or None if none is set."""
        for v in self._load_all(agent_name):
            if v.is_active:
                return v
        return None

    def agents(self) -> list[str]:
        """List all agent names that have at least one stored version."""
        return [p.stem for p in self._store.glob("*.jsonl")]

    # ------------------------------------------------------------------
    # Diff
    # ------------------------------------------------------------------

    def diff(self, agent_name: str, v1_id: str, v2_id: str) -> str:
        """
        Return a unified diff between two prompt versions.

        Example:
            print(registry.diff("cover_letter", "abc123", "def456"))
        """
        v1 = self.get(agent_name, v1_id)
        v2 = self.get(agent_name, v2_id)
        lines = difflib.unified_diff(
            v1.template.splitlines(keepends=True),
            v2.template.splitlines(keepends=True),
            fromfile=f"{agent_name}/{v1.short_id()} ({v1.created_at[:10]})",
            tofile=f"{agent_name}/{v2.short_id()} ({v2.created_at[:10]})",
        )
        return "".join(lines) or "(no differences)"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path(self, agent_name: str) -> Path:
        return self._store / f"{agent_name}.jsonl"

    def _load_all(self, agent_name: str) -> list[PromptVersion]:
        path = self._path(agent_name)
        if not path.exists():
            return []
        versions = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    versions.append(PromptVersion(**json.loads(line)))
                except Exception as e:
                    log.warning(f"PromptRegistry: skipping malformed line: {e}")
        return versions

    def _append(self, agent_name: str, version: PromptVersion) -> None:
        with self._path(agent_name).open("a") as f:
            f.write(json.dumps(asdict(version)) + "\n")

    def _rewrite(self, agent_name: str, versions: list[PromptVersion]) -> None:
        with self._path(agent_name).open("w") as f:
            for v in versions:
                f.write(json.dumps(asdict(v)) + "\n")
