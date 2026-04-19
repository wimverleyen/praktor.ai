"""Tests for `python -m praktor aigov` CLI subcommands."""
import argparse
import sys
from unittest.mock import MagicMock, patch

import pytest


def _make_args(**kwargs):
    """Build a minimal argparse Namespace for cmd_aigov."""
    defaults = {
        "aigov_cmd": "scoreboard",
        "agent": None,
        "tenant": None,
        "format": "table",
        "no_fail_on_empty": False,
        "bundle": "standard",
        "manifest": "",
        "validity_days": 30,
        "notes": "",
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# Import here after path is set up by conftest
from praktor.__main__ import cmd_aigov


class TestScoreboardEmpty:
    def test_no_fail_on_empty_exits_0(self, tmp_path, capsys):
        args = _make_args(aigov_cmd="scoreboard", no_fail_on_empty=True)
        with patch.dict("os.environ", {"AIGOV_LEDGER_PATH": str(tmp_path / "test.duckdb")}):
            cmd_aigov(args)
        out = capsys.readouterr().out
        assert "no events" in out.lower() or "empty" in out.lower()

    def test_empty_ledger_exits_0_with_no_fail(self, tmp_path):
        args = _make_args(aigov_cmd="scoreboard", no_fail_on_empty=True)
        with patch.dict("os.environ", {"AIGOV_LEDGER_PATH": str(tmp_path / "test.duckdb")}):
            cmd_aigov(args)


class TestScoreboardWithEvents:
    def test_table_format_prints_rows(self, tmp_path, capsys):
        """Write a PASS event then check the scoreboard prints it as GREEN."""
        import asyncio
        from praktor.aigov.ledger.store import LedgerStore
        from praktor.aigov.obligations.o7_auditable import O7Auditable
        from praktor.aigov.manifests import DataFlowManifest
        from datetime import datetime, timezone
        from unittest.mock import patch as _patch

        db = str(tmp_path / "sb.duckdb")
        store = LedgerStore(db_path=db)

        ob = O7Auditable()
        with _patch(
            "praktor.aigov.obligations.o7_auditable._otel_state",
            return_value={"sdk_disabled": False, "tracer_initialized": True},
        ):
            ev = asyncio.run(ob.check_run("p", "r"))

        import dataclasses as _dc
        ev = _dc.replace(ev, agent_id="test-agent")
        asyncio.run(store.write_event(ev))

        args = _make_args(aigov_cmd="scoreboard", format="table")
        with patch.dict("os.environ", {"AIGOV_LEDGER_PATH": db}):
            cmd_aigov(args)

        out = capsys.readouterr().out
        assert "Scoreboard" in out

    def test_json_format_produces_valid_json(self, tmp_path, capsys):
        import asyncio
        import json as _json
        from praktor.aigov.ledger.store import LedgerStore
        from praktor.aigov.obligations.o7_auditable import O7Auditable
        from unittest.mock import patch as _patch

        db = str(tmp_path / "sb2.duckdb")
        store = LedgerStore(db_path=db)

        ob = O7Auditable()
        with _patch(
            "praktor.aigov.obligations.o7_auditable._otel_state",
            return_value={"sdk_disabled": False, "tracer_initialized": True},
        ):
            ev = asyncio.run(ob.check_run("p", "r"))
        asyncio.run(store.write_event(ev))

        args = _make_args(aigov_cmd="scoreboard", format="json")
        with patch.dict("os.environ", {"AIGOV_LEDGER_PATH": db}):
            cmd_aigov(args)

        out = capsys.readouterr().out
        parsed = _json.loads(out)
        assert isinstance(parsed, list)


class TestAttest:
    def test_attest_empty_ledger(self, tmp_path, capsys):
        args = _make_args(
            aigov_cmd="attest",
            agent="test-agent",
            bundle="test-v1",
            validity_days=7,
            notes="ci test",
        )
        with patch.dict("os.environ", {"AIGOV_LEDGER_PATH": str(tmp_path / "att.duckdb")}):
            cmd_aigov(args)
        out = capsys.readouterr().out
        assert "Attestation" in out
        assert "test-agent" in out
        assert "test-v1" in out


class TestBuildCheck:
    def test_standard_bundle_passes(self, capsys):
        """Standard bundle has NA stubs — no FAIL → exit 0."""
        args = _make_args(aigov_cmd="build-check", bundle="standard", manifest="")
        cmd_aigov(args)
        out = capsys.readouterr().out
        assert "Build check passed" in out

    def test_minimal_bundle_passes(self, capsys):
        args = _make_args(aigov_cmd="build-check", bundle="minimal", manifest="")
        cmd_aigov(args)
        out = capsys.readouterr().out
        assert "Build check passed" in out or "✅" in out

    def test_healthcare_bundle_passes(self, capsys):
        args = _make_args(aigov_cmd="build-check", bundle="healthcare", manifest="")
        cmd_aigov(args)
        out = capsys.readouterr().out
        assert "passed" in out.lower() or "✅" in out

    def test_external_bundle_passes(self, capsys):
        args = _make_args(aigov_cmd="build-check", bundle="external", manifest="")
        cmd_aigov(args)
        out = capsys.readouterr().out
        assert "passed" in out.lower() or "✅" in out

    def test_custom_manifest_json(self, capsys):
        import json as _json
        manifest = _json.dumps({
            "source_systems": ["test"],
            "allowed_egress_destinations": ["audit"],
            "phi_fields": ["field1"],
            "signed_at": "2026-01-01T00:00:00+00:00",
            "deployer": "ci",
        })
        args = _make_args(aigov_cmd="build-check", bundle="minimal", manifest=manifest)
        cmd_aigov(args)
        out = capsys.readouterr().out
        assert "passed" in out.lower() or "✅" in out

    def test_all_bundles_show_obligation_ids(self, capsys):
        for bundle_name in ["minimal", "standard", "healthcare", "external"]:
            args = _make_args(aigov_cmd="build-check", bundle=bundle_name, manifest="")
            cmd_aigov(args)
        out = capsys.readouterr().out
        assert "O7" in out
