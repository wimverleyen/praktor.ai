"""
Clinical privacy tests — PHI gate enforcement (IRON RULE).

These tests must pass before any FAISS write path ships.
Every test here corresponds to a hard compliance requirement.

Run:
    PYTHONPATH=praktor pytest tests/test_clinical_privacy.py -v
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))


# ---------------------------------------------------------------------------
# Deidentifier tests
# ---------------------------------------------------------------------------

class TestDeidentifier:

    def setup_method(self):
        from clinical.privacy.deidentifier import Deidentifier
        self.deidentifier = Deidentifier()

    def test_empty_string_returns_empty(self):
        result = self.deidentifier.scrub("")
        assert result.text == ""
        assert result.phi_detected is False

    def test_no_phi_returns_text_unchanged(self):
        clean = "The patient has type 2 diabetes and requires statin therapy."
        result = self.deidentifier.scrub(clean)
        assert result.text == clean
        assert result.phi_detected is False

    def test_ssn_is_scrubbed(self):
        text = "Patient SSN: 123-45-6789. Diagnosis: hypertension."
        result = self.deidentifier.scrub(text)
        assert "123-45-6789" not in result.text
        assert result.phi_detected is True

    def test_phone_number_is_scrubbed(self):
        text = "Call patient at 555-867-5309 for follow-up."
        result = self.deidentifier.scrub(text)
        assert "555-867-5309" not in result.text
        assert result.phi_detected is True

    def test_email_is_scrubbed(self):
        text = "Send results to patient@example.com for review."
        result = self.deidentifier.scrub(text)
        assert "patient@example.com" not in result.text
        assert result.phi_detected is True

    def test_date_is_scrubbed(self):
        text = "DOB: 01/15/1980. Admission date 03/22/2024."
        result = self.deidentifier.scrub(text)
        assert "01/15/1980" not in result.text
        assert result.phi_detected is True

    def test_iso_date_is_scrubbed(self):
        text = "Lab drawn on 2024-03-15. Result pending."
        result = self.deidentifier.scrub(text)
        assert "2024-03-15" not in result.text
        assert result.phi_detected is True

    def test_scrub_result_text_is_string(self):
        result = self.deidentifier.scrub("Normal clinical text without PHI.")
        assert isinstance(result.text, str)

    def test_multiple_phi_types_all_scrubbed(self):
        text = "John Smith, DOB 02/14/1975, SSN 987-65-4321, email: john@test.com"
        result = self.deidentifier.scrub(text)
        assert "987-65-4321" not in result.text
        assert "john@test.com" not in result.text
        assert "02/14/1975" not in result.text


# ---------------------------------------------------------------------------
# PHI gate tests — IRON RULE: raises, never passes through
# ---------------------------------------------------------------------------

class TestPHIGate:

    def test_phi_scrubbed_true_passes(self):
        from clinical.privacy.deidentifier import validate_phi_scrubbed
        # Must not raise
        validate_phi_scrubbed(True, context="test")

    def test_phi_scrubbed_false_raises(self):
        from clinical.privacy.deidentifier import validate_phi_scrubbed
        with pytest.raises(ValueError, match="PHI gate violation"):
            validate_phi_scrubbed(False, context="test")

    def test_phi_gate_raises_not_logs(self):
        """Gate must raise — logging and continuing is not acceptable."""
        from clinical.privacy.deidentifier import validate_phi_scrubbed
        raised = False
        try:
            validate_phi_scrubbed(False)
        except ValueError:
            raised = True
        assert raised, "PHI gate must raise ValueError, not silently continue"

    def test_member_brain_rejects_unscrubbed_chunk(self, tmp_path):
        """MemberBrain.add_chunk raises if phi_scrubbed=False."""
        from clinical.memory.member_brain import MemberBrain
        from clinical.schemas import ClinicalBrainChunk

        brain = MemberBrain(base_dir=str(tmp_path))

        chunk = ClinicalBrainChunk(
            member_id_hash="abc123def456",
            source_type="claim",
            date="2024-01-15",
            content="Some clinical text",
            phi_scrubbed=False,   # ← MUST be rejected
        )

        with pytest.raises(ValueError, match="PHI gate violation"):
            brain.add_chunk(chunk)

    def test_member_brain_accepts_scrubbed_chunk_when_embeddings_unavailable(self, tmp_path):
        """Gate passes when phi_scrubbed=True (embeddings may be unavailable in tests)."""
        from clinical.memory.member_brain import MemberBrain
        from clinical.schemas import ClinicalBrainChunk

        brain = MemberBrain(base_dir=str(tmp_path))
        # Disable embeddings so we test gate logic without Ollama
        brain._embeddings = None

        chunk = ClinicalBrainChunk(
            member_id_hash="abc123def456",
            source_type="claim",
            date="2024-01-15",
            content="Statin fill 30d supply",
            phi_scrubbed=True,   # ← Should pass the gate (embeddings skip is graceful)
        )
        # Should not raise — embeddings missing → logs warning and returns
        brain.add_chunk(chunk)


# ---------------------------------------------------------------------------
# Member ID hashing tests
# ---------------------------------------------------------------------------

class TestMemberIDHashing:

    def test_hash_is_deterministic(self):
        from clinical.schemas import hash_member_id
        h1 = hash_member_id("MEMBER-12345")
        h2 = hash_member_id("MEMBER-12345")
        assert h1 == h2

    def test_hash_is_64_chars(self):
        from clinical.schemas import hash_member_id
        h = hash_member_id("MEMBER-12345")
        assert len(h) == 64

    def test_different_ids_produce_different_hashes(self):
        from clinical.schemas import hash_member_id
        h1 = hash_member_id("MEMBER-12345")
        h2 = hash_member_id("MEMBER-12346")
        assert h1 != h2

    def test_raw_id_not_present_in_hash(self):
        from clinical.schemas import hash_member_id
        raw = "MEMBER-99999"
        hashed = hash_member_id(raw)
        assert raw not in hashed

    def test_short_id_is_prefix_of_full_hash(self):
        from clinical.schemas import hash_member_id, short_id
        full = hash_member_id("MEMBER-12345")
        short = short_id(full)
        assert full.startswith(short)
        assert len(short) == 12


# ---------------------------------------------------------------------------
# HEDIS gap schema tests
# ---------------------------------------------------------------------------

class TestHEDISGap:

    def test_priority_score_triple_weighted_ranks_higher(self):
        from clinical.schemas import HEDISGap

        triple = HEDISGap(
            member_id_hash="abc", measure_id="MAC",
            measure_name="Statin", stars_weight=3.0,
            measurement_year=2024, days_remaining=60,
            pdc_current=0.65,
        )
        single = HEDISGap(
            member_id_hash="abc", measure_id="BCS",
            measure_name="Mammogram", stars_weight=1.0,
            measurement_year=2024, days_remaining=60,
        )
        assert triple.priority_score > single.priority_score

    def test_pdc_gap_calculated_correctly(self):
        from clinical.schemas import HEDISGap

        gap = HEDISGap(
            member_id_hash="abc", measure_id="MAC",
            measure_name="Statin", stars_weight=3.0,
            measurement_year=2024, days_remaining=90,
            pdc_current=0.72, pdc_threshold=0.80,
        )
        assert abs(gap.pdc_gap - 0.08) < 0.001

    def test_pdc_gap_none_when_pdc_current_none(self):
        from clinical.schemas import HEDISGap

        gap = HEDISGap(
            member_id_hash="abc", measure_id="BCS",
            measure_name="Mammogram", stars_weight=1.0,
            measurement_year=2024, days_remaining=90,
        )
        assert gap.pdc_gap is None

    def test_days_remaining_zero_handled(self):
        from clinical.schemas import HEDISGap

        gap = HEDISGap(
            member_id_hash="abc", measure_id="MAC",
            measure_name="Statin", stars_weight=3.0,
            measurement_year=2024, days_remaining=0,
        )
        # Should not raise, priority_score should still be a float
        assert isinstance(gap.priority_score, float)
