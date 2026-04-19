"""Tests for pre-built ObligationBundle factories."""
import pytest

from praktor.aigov.bundle import (
    ObligationBundle,
    external_bundle,
    healthcare_bundle,
    minimal_bundle,
    standard_bundle,
)


class TestMinimalBundle:
    def test_returns_obligation_bundle(self):
        b = minimal_bundle()
        assert isinstance(b, ObligationBundle)

    def test_bundle_id(self):
        assert minimal_bundle().bundle_id == "minimal-v1"

    def test_contains_o7(self):
        assert "O7" in minimal_bundle().obligation_ids()

    def test_length(self):
        assert len(minimal_bundle()) == 1

    def test_fresh_instances(self):
        assert minimal_bundle() is not minimal_bundle()


class TestStandardBundle:
    def test_bundle_id(self):
        assert standard_bundle().bundle_id == "standard-v1"

    def test_contains_required_set(self):
        ids = standard_bundle().obligation_ids()
        for oid in ["O1", "O3", "O7", "O9", "O10"]:
            assert oid in ids, f"Missing {oid}"

    def test_length(self):
        assert len(standard_bundle()) == 5

    def test_no_o2(self):
        assert "O2" not in standard_bundle().obligation_ids()

    def test_no_o11(self):
        assert "O11" not in standard_bundle().obligation_ids()


class TestHealthcareBundle:
    def test_bundle_id(self):
        assert healthcare_bundle().bundle_id == "healthcare-v1"

    def test_contains_phi_and_hitl(self):
        ids = healthcare_bundle().obligation_ids()
        for oid in ["O1", "O2", "O3", "O7", "O8", "O9", "O10"]:
            assert oid in ids, f"Missing {oid}"

    def test_length(self):
        assert len(healthcare_bundle()) == 7

    def test_no_o11(self):
        assert "O11" not in healthcare_bundle().obligation_ids()


class TestExternalBundle:
    def test_bundle_id(self):
        assert external_bundle().bundle_id == "external-v1"

    def test_contains_o11(self):
        assert "O11" in external_bundle().obligation_ids()

    def test_contains_standard_set(self):
        ids = external_bundle().obligation_ids()
        for oid in ["O1", "O3", "O7", "O9", "O10", "O11"]:
            assert oid in ids, f"Missing {oid}"

    def test_length(self):
        assert len(external_bundle()) == 6

    def test_no_o2(self):
        assert "O2" not in external_bundle().obligation_ids()

    def test_no_o8(self):
        assert "O8" not in external_bundle().obligation_ids()


class TestBundleIteration:
    def test_iter_all_bundles(self):
        for factory in [minimal_bundle, standard_bundle, healthcare_bundle, external_bundle]:
            b = factory()
            obligations = list(b)
            assert len(obligations) == len(b)

    def test_get_existing(self):
        b = healthcare_bundle()
        o2 = b.get("O2")
        assert o2 is not None
        assert o2.id == "O2"

    def test_get_missing_returns_none(self):
        b = minimal_bundle()
        assert b.get("O99") is None

    def test_description_nonempty(self):
        for factory in [minimal_bundle, standard_bundle, healthcare_bundle, external_bundle]:
            assert factory().description
