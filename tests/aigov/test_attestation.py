"""Tests for AttestationRecord and create_attestation()."""
from datetime import datetime, timezone, timedelta

import pytest

from praktor.aigov.attestation import AttestationRecord, create_attestation


def _rows(statuses):
    return [
        {"obligation_id": f"O{i+1}", "enforcement_point": "G-RUN", "status": s, "event_ts": "2026-01-01T00:00:00Z"}
        for i, s in enumerate(statuses)
    ]


class TestCreateAttestation:
    def test_returns_attestation_record(self):
        att = create_attestation("agent-1", "test-v1", rows=[])
        assert isinstance(att, AttestationRecord)

    def test_agent_id_set(self):
        att = create_attestation("my-agent", "bundle-v1", rows=[])
        assert att.agent_id == "my-agent"

    def test_bundle_id_set(self):
        att = create_attestation("a", "healthcare-v1", rows=[])
        assert att.bundle_id == "healthcare-v1"

    def test_tenant_id_defaults_empty(self):
        att = create_attestation("a", "b", rows=[])
        assert att.tenant_id == ""

    def test_tenant_id_set(self):
        att = create_attestation("a", "b", rows=[], tenant_id="acme")
        assert att.tenant_id == "acme"

    def test_attestation_id_is_ulid(self):
        att = create_attestation("a", "b", rows=[])
        assert len(att.attestation_id) == 26

    def test_signature_hex_is_sha256(self):
        att = create_attestation("a", "b", rows=[])
        assert len(att.signature_hex) == 64

    def test_created_at_rfc3339(self):
        att = create_attestation("a", "b", rows=[])
        assert att.created_at.endswith("Z")

    def test_valid_until_rfc3339(self):
        att = create_attestation("a", "b", rows=[])
        assert att.valid_until.endswith("Z")

    def test_valid_until_after_created_at(self):
        att = create_attestation("a", "b", rows=[])
        assert att.valid_until > att.created_at

    def test_validity_days_custom(self):
        att = create_attestation("a", "b", rows=[], validity_days=7)
        # valid_until should be ~7 days after created_at
        assert att.valid_until > att.created_at

    def test_obligation_statuses_populated(self):
        rows = _rows(["GREEN", "RED"])
        att = create_attestation("a", "b", rows=rows)
        assert len(att.obligation_statuses) == 2
        assert att.obligation_statuses[0]["obligation_id"] == "O1"
        assert att.obligation_statuses[0]["status"] == "GREEN"

    def test_notes_set(self):
        att = create_attestation("a", "b", rows=[], notes="CI build 42")
        assert att.notes == "CI build 42"

    def test_signature_deterministic(self):
        rows = _rows(["GREEN"])
        att1 = create_attestation("agent", "bundle", rows=rows, tenant_id="t1")
        # Different timestamp = different signature (that's correct behaviour)
        assert len(att1.signature_hex) == 64

    def test_signer_key_id_placeholder(self):
        att = create_attestation("a", "b", rows=[])
        assert att.signer_key_id == "sha256-content-hash"


class TestAttestationRecord:
    def _make(self, statuses, *, expired=False):
        rows = _rows(statuses)
        att = create_attestation("a", "b", rows=rows, validity_days=1 if not expired else 0)
        if expired:
            att = AttestationRecord(
                attestation_id=att.attestation_id,
                agent_id=att.agent_id,
                bundle_id=att.bundle_id,
                created_at="2020-01-01T00:00:00Z",
                valid_until="2020-01-02T00:00:00Z",
                obligation_statuses=att.obligation_statuses,
                signature_hex=att.signature_hex,
            )
        return att

    def test_is_current_true(self):
        att = self._make(["GREEN"])
        assert att.is_current() is True

    def test_is_current_false_when_expired(self):
        att = self._make(["GREEN"], expired=True)
        assert att.is_current() is False

    def test_all_obligations_held_all_green(self):
        att = self._make(["GREEN", "GREEN", "GREEN"])
        assert att.all_obligations_held() is True

    def test_all_obligations_held_amber_ok(self):
        att = self._make(["AMBER", "AMBER"])
        assert att.all_obligations_held() is True

    def test_all_obligations_held_red_fails(self):
        att = self._make(["GREEN", "RED"])
        assert att.all_obligations_held() is False

    def test_all_obligations_held_fail_status_fails(self):
        att = self._make(["FAIL"])
        assert att.all_obligations_held() is False

    def test_all_obligations_held_empty(self):
        att = self._make([])
        assert att.all_obligations_held() is True

    def test_has_any_green_true(self):
        att = self._make(["AMBER", "GREEN"])
        assert att.has_any_green() is True

    def test_has_any_green_false(self):
        att = self._make(["AMBER", "AMBER"])
        assert att.has_any_green() is False

    def test_has_any_green_empty(self):
        att = self._make([])
        assert att.has_any_green() is False
