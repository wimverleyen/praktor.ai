"""
Tests for praktor.aigov PR1 interface contract.
Covers ObligationEvent, all enums, EvidenceRef, SourceRef, ReviewerRef,
make_evidence canonical hashing, and PrivacyTestDataset validation.
"""
import hashlib
import json
import re
import socket

import pytest

from praktor.aigov import (
    AgentPattern,
    DeploymentEnv,
    EnforcementPoint,
    EvidenceRef,
    ObligationEvent,
    PredicateResult,
    ReviewerRef,
    Severity,
    SourceRef,
    make_evidence,
)
from praktor.aigov.manifests import DataFlowManifest, PrivacyTestDataset
from datetime import datetime, timezone


RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
ULID_RE = re.compile(r"^[0-9A-Z]{26}$")


def minimal_event() -> ObligationEvent:
    return ObligationEvent(
        obligation_id="O1",
        enforcement_point=EnforcementPoint.G_BUILD,
        predicate_result=PredicateResult.PASS,
    )


class TestPredicateResult:
    def test_values(self):
        assert PredicateResult.PASS == "PASS"
        assert PredicateResult.FAIL == "FAIL"
        assert PredicateResult.WAIVED == "WAIVED"
        assert PredicateResult.NA == "NA"

    def test_is_str(self):
        assert isinstance(PredicateResult.PASS, str)


class TestAgentPattern:
    def test_all_patterns(self):
        patterns = [AgentPattern.B1, AgentPattern.B2, AgentPattern.B3, AgentPattern.B4,
                    AgentPattern.B5, AgentPattern.B6, AgentPattern.B7]
        assert len(patterns) == 7

    def test_is_str(self):
        assert isinstance(AgentPattern.B3, str)
        assert AgentPattern.B3 == "B3"


class TestEnforcementPoint:
    def test_values(self):
        assert EnforcementPoint.G_BUILD == "G-BUILD"
        assert EnforcementPoint.G_TEST == "G-TEST"
        assert EnforcementPoint.G_RUN == "G-RUN"


class TestDeploymentEnv:
    def test_values(self):
        assert DeploymentEnv.DEV == "dev"
        assert DeploymentEnv.PROD == "prod"


class TestSeverity:
    def test_ordering(self):
        levels = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        assert len(levels) == 5


class TestObligationEventDefaults:
    def test_required_fields_only(self):
        ev = minimal_event()
        assert ev.obligation_id == "O1"
        assert ev.enforcement_point == EnforcementPoint.G_BUILD
        assert ev.predicate_result == PredicateResult.PASS

    def test_event_id_is_ulid(self):
        ev = minimal_event()
        assert ULID_RE.match(ev.event_id), f"Not a ULID: {ev.event_id!r}"

    def test_event_id_unique_per_instance(self):
        a = minimal_event()
        b = minimal_event()
        assert a.event_id != b.event_id

    def test_event_ts_is_rfc3339_utc(self):
        ev = minimal_event()
        assert RFC3339_RE.match(ev.event_ts), f"Bad event_ts: {ev.event_ts!r}"

    def test_ingest_ts_is_rfc3339_utc(self):
        ev = minimal_event()
        assert RFC3339_RE.match(ev.ingest_ts), f"Bad ingest_ts: {ev.ingest_ts!r}"

    def test_schema_version(self):
        ev = minimal_event()
        assert ev.schema_version == "1.0"

    def test_default_agent_pattern(self):
        ev = minimal_event()
        assert ev.agent_pattern == AgentPattern.B1

    def test_default_deployment_env(self):
        ev = minimal_event()
        assert ev.deployment_env == DeploymentEnv.DEV

    def test_default_severity(self):
        ev = minimal_event()
        assert ev.severity == Severity.INFO

    def test_default_tenant(self):
        ev = minimal_event()
        assert ev.tenant_id == "default"

    def test_regulatory_tags_default_empty(self):
        ev = minimal_event()
        assert ev.regulatory_tags == []

    def test_source_ref_defaults(self):
        ev = minimal_event()
        assert ev.source.kind == "praktor_aigov"
        assert ev.source.version == "0.5.0"
        assert ev.source.host == socket.gethostname()

    def test_na_with_deferred_reason(self):
        ev = ObligationEvent(
            obligation_id="O5",
            enforcement_point=EnforcementPoint.G_RUN,
            predicate_result=PredicateResult.NA,
            deferred_reason="no_hitl_platform",
        )
        assert ev.predicate_result == PredicateResult.NA
        assert ev.deferred_reason == "no_hitl_platform"

    def test_missing_required_raises(self):
        with pytest.raises(TypeError):
            ObligationEvent()  # type: ignore[call-arg]

    def test_explicit_event_id_preserved(self):
        ev = ObligationEvent(
            obligation_id="O1",
            enforcement_point=EnforcementPoint.G_BUILD,
            predicate_result=PredicateResult.PASS,
            event_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        )
        assert ev.event_id == "01ARZ3NDEKTSV4RRFFQ69G5FAV"

    def test_full_population(self):
        ev = ObligationEvent(
            obligation_id="O2",
            enforcement_point=EnforcementPoint.G_TEST,
            predicate_result=PredicateResult.FAIL,
            agent_id="agent-123",
            agent_version="1.2.3",
            agent_pattern=AgentPattern.B3,
            deployment_env=DeploymentEnv.STAGING,
            tenant_id="acme",
            bundle_id="healthcare-v1",
            severity=Severity.HIGH,
            regulatory_tags=["HIPAA", "EU-AI-ACT"],
            trace_id="abc123",
            span_id="def456",
            evidence=EvidenceRef(uri="s3://bucket/ev.json", sha256="deadbeef"),
            reviewer=ReviewerRef(reviewer_id="rev-1", name="Alice"),
        )
        assert ev.agent_id == "agent-123"
        assert ev.regulatory_tags == ["HIPAA", "EU-AI-ACT"]
        assert ev.evidence.uri == "s3://bucket/ev.json"
        assert ev.reviewer.reviewer_id == "rev-1"


class TestEvidenceRef:
    def test_defaults(self):
        ref = EvidenceRef(uri="file:///tmp/ev.json", sha256="abc")
        assert ref.size_bytes == 0
        assert ref.redacted is True

    def test_custom_values(self):
        ref = EvidenceRef(uri="s3://x", sha256="deadbeef", size_bytes=1024, redacted=False)
        assert ref.size_bytes == 1024
        assert ref.redacted is False


class TestReviewerRef:
    def test_minimal(self):
        ref = ReviewerRef(reviewer_id="r1")
        assert ref.name == ""
        assert ref.role == ""


class TestMakeEvidence:
    def test_returns_bytes_and_hex(self):
        data = {"foo": "bar", "n": 42}
        raw, sha = make_evidence(data)
        assert isinstance(raw, bytes)
        assert len(sha) == 64
        assert all(c in "0123456789abcdef" for c in sha)

    def test_sha256_correct(self):
        data = {"x": 1}
        raw, sha = make_evidence(data)
        expected = hashlib.sha256(raw).hexdigest()
        assert sha == expected

    def test_canonical_sort_keys(self):
        a, sha_a = make_evidence({"b": 2, "a": 1})
        b, sha_b = make_evidence({"a": 1, "b": 2})
        assert sha_a == sha_b

    def test_compact_separators(self):
        raw, _ = make_evidence({"k": "v"})
        decoded = raw.decode("utf-8")
        assert " " not in decoded

    def test_non_serializable_uses_str(self):
        from datetime import date
        raw, sha = make_evidence({"d": date(2024, 1, 1)})
        assert b"2024-01-01" in raw

    def test_empty_dict(self):
        raw, sha = make_evidence({})
        assert raw == b"{}"
        assert len(sha) == 64


class TestDataFlowManifest:
    def test_instantiation(self):
        m = DataFlowManifest(
            source_systems=["ehr"],
            allowed_egress_destinations=["audit_log"],
            phi_fields=["member_id"],
            signed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            deployer="ci-bot",
        )
        assert m.source_systems == ["ehr"]
        assert m.deployer == "ci-bot"
        assert m.version == "1.0"
        assert m.cim_version == ""


class TestPrivacyTestDataset:
    def test_valid(self):
        ds = PrivacyTestDataset(
            records=[{"text": "SSN: 123-45-6789"}, {"text": "hello"}],
            labels=["US_SSN", "none"],
        )
        assert len(ds.records) == 2

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="equal length"):
            PrivacyTestDataset(records=[{"a": 1}, {"b": 2}], labels=["x"])

    def test_defaults(self):
        ds = PrivacyTestDataset(records=[], labels=[])
        assert ds.loaded_from == ""
        assert ds.description == ""
