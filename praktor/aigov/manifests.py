"""
Input types for Obligation check_build() and check_test() methods.

DataFlowManifest: static declaration of data flows for G-BUILD lint (O2, O1).
PrivacyTestDataset: labelled records for G-TEST evaluation (O2, O4).

Both are provided by the agent owner at deploy/CI time, not at runtime.
Missing G-TEST data → AMBER advisory (NA event), not CI failure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DataFlowManifest:
    """
    Declares which systems data flows through and where PHI is allowed to travel.

    Used by O2 (check_build) to verify PHI fields never reach disallowed egress.
    Used by O1 (check_build) to verify the agent's action space is bounded.

    Must be signed at deploy time (signed_at timestamp + deployer identity).
    """

    source_systems: list[str]
    """Upstream data sources this agent reads from (e.g. ['ehr', 'claims_db'])."""

    allowed_egress_destinations: list[str]
    """Systems the agent is permitted to write to (e.g. ['audit_log', 'minio'])."""

    phi_fields: list[str]
    """Field names that may contain PHI (e.g. ['member_id', 'diagnosis_codes'])."""

    signed_at: datetime
    """When this manifest was signed by the deployer. Used for O9 currency check."""

    deployer: str = ""
    """Identity of whoever signed this manifest (e.g. 'ci-bot', 'john.doe@acme')."""

    version: str = "1.0"
    """Semantic version of this manifest declaration."""

    cim_version: str = ""
    """Change Impact Matrix version active when this manifest was signed (O9)."""


@dataclass
class PrivacyTestDataset:
    """
    Labelled records for G-TEST privacy evaluation (O2, O4).

    Loaded from AIGOV_TEST_DATA_PATH env var at CI time.
    If the path is missing or the file is unreadable, obligations emit a NA event
    with deferred_reason='test_data_unavailable' — not a CI failure.

    records: list of dicts, each representing one test input.
    labels: expected entity types present in each record (parallel to records).
    """

    records: list[dict]
    """Test inputs. PHI fields should be synthetic (not real patient data)."""

    labels: list[str]
    """
    Expected entity type for each record (parallel list).
    E.g. ['US_SSN', 'EMAIL_ADDRESS', 'none'] for three records.
    'none' means the record should produce no detections.
    """

    loaded_from: str = ""
    """Filesystem path this dataset was loaded from (for provenance)."""

    description: str = ""

    def __post_init__(self) -> None:
        if len(self.records) != len(self.labels):
            raise ValueError(
                f"PrivacyTestDataset: records ({len(self.records)}) and "
                f"labels ({len(self.labels)}) must have equal length."
            )
