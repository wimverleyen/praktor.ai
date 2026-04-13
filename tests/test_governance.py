"""
Tests for praktor governance: detectors, audit log, policy, RBAC, and
end-to-end Agent.run() governance hooks.

All tests are mocked — no live LLM, no disk I/O by default.
"""
import sys
import json
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / 'praktor'))

import pytest
from pydantic import BaseModel

from governance.detectors import RegexDetector, DetectionResult, load_detector
from governance.policy import (
    GovernancePolicy, PolicyAction, DetectorConfig, AuditSinkType,
    GovernancePolicyViolation,
)
from governance.audit import AuditEntry, LocalFileAuditSink, StdoutAuditSink
from governance.rbac import (
    issue_token, verify_token, CallerIdentity, RBACError,
    ConfigurationError, _seen_jtis, _seen_jtis_set,
)


# ---------------------------------------------------------------------------
# RegexDetector
# ---------------------------------------------------------------------------

class TestRegexDetector:

    @pytest.mark.asyncio
    async def test_detects_ssn(self):
        detector = RegexDetector()
        results = await detector.detect("Patient SSN: 123-45-6789", ["US_SSN"])
        assert len(results) == 1
        assert results[0].entity_type == "US_SSN"
        assert results[0].text == "123-45-6789"
        assert results[0].score == 1.0

    @pytest.mark.asyncio
    async def test_detects_email(self):
        detector = RegexDetector()
        results = await detector.detect("Contact: alice@example.com", ["EMAIL_ADDRESS"])
        assert len(results) == 1
        assert results[0].entity_type == "EMAIL_ADDRESS"
        assert results[0].text == "alice@example.com"

    @pytest.mark.asyncio
    async def test_detects_phone(self):
        detector = RegexDetector()
        results = await detector.detect("Call 555-867-5309", ["PHONE_NUMBER"])
        assert len(results) == 1
        assert results[0].entity_type == "PHONE_NUMBER"

    @pytest.mark.asyncio
    async def test_detects_credit_card(self):
        detector = RegexDetector()
        results = await detector.detect("Card: 4111 1111 1111 1111", ["CREDIT_CARD"])
        assert len(results) == 1
        assert results[0].entity_type == "CREDIT_CARD"

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(self):
        detector = RegexDetector()
        results = await detector.detect("Hello world!", ["US_SSN", "EMAIL_ADDRESS"])
        assert results == []

    @pytest.mark.asyncio
    async def test_ignores_unrequested_entities(self):
        detector = RegexDetector()
        # Text has email but we only ask for SSN
        results = await detector.detect("alice@example.com", ["US_SSN"])
        assert results == []

    @pytest.mark.asyncio
    async def test_multiple_matches(self):
        detector = RegexDetector()
        text = "SSN 123-45-6789 and 987-65-4321"
        results = await detector.detect(text, ["US_SSN"])
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_large_text_chunking(self):
        """Text > MAX_DETECTOR_CHARS should be processed in chunks without dropping matches."""
        from governance.detectors import MAX_DETECTOR_CHARS
        detector = RegexDetector()
        # Build text just over the limit with an SSN near the start and end
        filler = "x " * (MAX_DETECTOR_CHARS // 2 + 100)
        text = "SSN 123-45-6789 " + filler + " SSN 987-65-4321"
        results = await detector.detect(text, ["US_SSN"])
        assert len(results) == 2

    def test_load_detector_by_import_path(self):
        detector = load_detector("governance.detectors.RegexDetector")
        assert isinstance(detector, RegexDetector)

    def test_load_detector_invalid_path_raises(self):
        with pytest.raises(ValueError, match="Invalid detector import path"):
            load_detector("InvalidPath")


# ---------------------------------------------------------------------------
# AuditEntry
# ---------------------------------------------------------------------------

class TestAuditEntry:

    def test_hash_text(self):
        h = AuditEntry.hash_text("hello")
        assert len(h) == 64  # SHA-256 hex

    def test_hash_text_deterministic(self):
        assert AuditEntry.hash_text("abc") == AuditEntry.hash_text("abc")

    def test_serialize_is_json(self):
        entry = AuditEntry(agent_type="test", session_id="s1", model="qwen2.5")
        data = json.loads(entry.serialize())
        assert data["agent_type"] == "test"
        assert data["session_id"] == "s1"

    def test_entry_hash_deterministic(self):
        entry = AuditEntry(agent_type="test", session_id="s1", model="qwen2.5")
        assert entry.entry_hash() == entry.entry_hash()

    def test_entry_hash_changes_with_content(self):
        e1 = AuditEntry(agent_type="a", session_id="s", model="m")
        e2 = AuditEntry(agent_type="b", session_id="s", model="m")
        assert e1.entry_hash() != e2.entry_hash()


# ---------------------------------------------------------------------------
# LocalFileAuditSink
# ---------------------------------------------------------------------------

class TestLocalFileAuditSink:

    @pytest.mark.asyncio
    async def test_write_creates_file(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        sink = LocalFileAuditSink(log_path=log_path)
        entry = AuditEntry(agent_type="test", session_id="s1", model="qwen2.5")
        await sink.write(entry)
        assert Path(log_path).exists()

    @pytest.mark.asyncio
    async def test_write_appends_valid_json(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        sink = LocalFileAuditSink(log_path=log_path)
        e1 = AuditEntry(agent_type="a", session_id="s1", model="m")
        e2 = AuditEntry(agent_type="b", session_id="s2", model="m")
        await sink.write(e1)
        await sink.write(e2)
        lines = Path(log_path).read_text().strip().split("\n")
        assert len(lines) == 2
        data1 = json.loads(lines[0])
        data2 = json.loads(lines[1])
        assert data1["agent_type"] == "a"
        assert data2["agent_type"] == "b"

    @pytest.mark.asyncio
    async def test_hash_chaining(self, tmp_path):
        """Second entry's previous_entry_hash should equal hash of first entry."""
        log_path = str(tmp_path / "audit.jsonl")
        sink = LocalFileAuditSink(log_path=log_path)
        e1 = AuditEntry(agent_type="a", session_id="s1", model="m")
        e2 = AuditEntry(agent_type="b", session_id="s2", model="m")
        await sink.write(e1)
        await sink.write(e2)

        lines = Path(log_path).read_text().strip().split("\n")
        d1 = json.loads(lines[0])
        d2 = json.loads(lines[1])

        # Reconstruct e1 as written (with its previous_entry_hash = genesis)
        e1_written = AuditEntry(**{k: v for k, v in d1.items() if k in AuditEntry.__dataclass_fields__})
        assert d2["previous_entry_hash"] == e1_written.entry_hash()

    @pytest.mark.asyncio
    async def test_chain_resumes_after_restart(self, tmp_path):
        """A new sink instance reads the chain tip from disk and continues correctly."""
        log_path = str(tmp_path / "audit.jsonl")

        sink1 = LocalFileAuditSink(log_path=log_path)
        e1 = AuditEntry(agent_type="a", session_id="s1", model="m")
        await sink1.write(e1)

        # Fresh sink instance — simulates process restart
        sink2 = LocalFileAuditSink(log_path=log_path)
        e2 = AuditEntry(agent_type="b", session_id="s2", model="m")
        await sink2.write(e2)

        lines = Path(log_path).read_text().strip().split("\n")
        d1 = json.loads(lines[0])
        d2 = json.loads(lines[1])
        e1_written = AuditEntry(**{k: v for k, v in d1.items() if k in AuditEntry.__dataclass_fields__})
        assert d2["previous_entry_hash"] == e1_written.entry_hash()

    @pytest.mark.asyncio
    async def test_first_entry_has_genesis_hash(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        sink = LocalFileAuditSink(log_path=log_path)
        entry = AuditEntry(agent_type="a", session_id="s", model="m")
        await sink.write(entry)
        lines = Path(log_path).read_text().strip().split("\n")
        d = json.loads(lines[0])
        assert d["previous_entry_hash"] == "genesis"


# ---------------------------------------------------------------------------
# GovernancePolicy
# ---------------------------------------------------------------------------

class TestGovernancePolicy:

    def test_default_policy_has_local_file_sink(self):
        policy = GovernancePolicy()
        assert AuditSinkType.LOCAL_FILE in policy.audit_sinks

    def test_invalid_sink_type_raises(self):
        with pytest.raises(ValueError, match="Invalid audit_sinks"):
            GovernancePolicy(audit_sinks=["invalid"])

    def test_empty_pre_and_post_is_valid(self):
        policy = GovernancePolicy(pre_execution=[], post_execution=[])
        assert policy.pre_execution == []


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------

class TestRBAC:

    def setup_method(self):
        # Clear replay cache between tests
        _seen_jtis.clear()
        _seen_jtis_set.clear()

    def test_issue_and_verify(self):
        secret = "test-secret-1234"
        token = issue_token(caller_id="alice", roles=["admin"], secret=secret)
        identity = verify_token(token, secret=secret, required_roles=["admin"])
        assert identity.caller_id == "alice"
        assert "admin" in identity.roles

    def test_wrong_secret_raises(self):
        token = issue_token(caller_id="alice", roles=["admin"], secret="correct")
        with pytest.raises(RBACError, match="signature invalid"):
            verify_token(token, secret="wrong", required_roles=["admin"])

    def test_missing_role_raises(self):
        token = issue_token(caller_id="alice", roles=["reader"], secret="s")
        with pytest.raises(RBACError, match="missing required role"):
            verify_token(token, secret="s", required_roles=["admin"])

    def test_malformed_token_raises(self):
        with pytest.raises(RBACError, match="Malformed token"):
            verify_token("not.a.valid.token.extra", secret="s", required_roles=[])

    def test_replay_rejected(self):
        token = issue_token(caller_id="alice", roles=["admin"], secret="s")
        verify_token(token, secret="s", required_roles=["admin"])
        with pytest.raises(RBACError, match="replay detected"):
            verify_token(token, secret="s", required_roles=["admin"])

    def test_expired_token_raises(self):
        import time
        from governance import rbac as rbac_module
        old_ttl = rbac_module.TOKEN_TTL_SECONDS
        rbac_module.TOKEN_TTL_SECONDS = 0  # Instantly expire
        try:
            token = issue_token(caller_id="alice", roles=["admin"], secret="s")
            with pytest.raises(RBACError, match="expired"):
                verify_token(token, secret="s", required_roles=["admin"])
        finally:
            rbac_module.TOKEN_TTL_SECONDS = old_ttl

    def test_no_required_roles_passes_with_any_token(self):
        token = issue_token(caller_id="bob", roles=[], secret="s")
        identity = verify_token(token, secret="s", required_roles=[])
        assert identity.caller_id == "bob"


# ---------------------------------------------------------------------------
# Router RBAC integration
# ---------------------------------------------------------------------------

class _ProtectedInput(BaseModel):
    agent_type: str = "protected"
    query: str
    session_id: str = ""
    caller_token: str = ""


class TestRouterRBAC:

    def setup_method(self):
        _seen_jtis.clear()
        _seen_jtis_set.clear()

    def test_register_rbac_agent_without_secret_raises(self, monkeypatch):
        from core.router import Router
        from governance.rbac import ConfigurationError

        monkeypatch.setattr("core.router.PRAKTOR_RBAC_SECRET", None)
        router = Router()
        defn = _make_protected_definition()
        with pytest.raises(ConfigurationError, match="PRAKTOR_RBAC_SECRET is not set"):
            router.register(defn)

    @pytest.mark.asyncio
    async def test_dispatch_without_token_raises(self, monkeypatch):
        from core.router import Router
        from governance.rbac import RBACError

        monkeypatch.setattr("core.router.PRAKTOR_RBAC_SECRET", "secret")
        router = Router()
        router.register(_make_protected_definition())

        raw = json.dumps({"agent_type": "protected", "query": "hi"}).encode()
        with pytest.raises(RBACError, match="caller_token.*missing"):
            async for _ in router.dispatch(raw):
                pass

    @pytest.mark.asyncio
    async def test_dispatch_with_valid_token_routes(self, monkeypatch):
        from core.router import Router

        secret = "test-secret"
        monkeypatch.setattr("core.router.PRAKTOR_RBAC_SECRET", secret)
        router = Router()
        router.register(_make_protected_definition())

        token = issue_token(caller_id="ml-team", roles=["hipaa-reader"], secret=secret)

        async def _fake_run(payload, session_id, caller_identity="anonymous"):
            yield "ok"

        with patch.object(router._agents["protected"], "run", side_effect=_fake_run):
            raw = json.dumps({
                "agent_type": "protected",
                "query": "test",
                "caller_token": token,
            }).encode()
            chunks = []
            async for chunk in router.dispatch(raw):
                chunks.append(chunk)

        assert chunks == ["ok"]


def _make_protected_definition():
    from core.agent_definition import AgentDefinition
    from governance.policy import GovernancePolicy

    return AgentDefinition(
        name="protected",
        prompt_template="Answer: {query}",
        input_schema=_ProtectedInput,
        governance_policy=GovernancePolicy(
            rbac_required_roles=["hipaa-reader"],
        ),
    )


# ---------------------------------------------------------------------------
# Agent governance hooks (end-to-end, mocked LLM)
# ---------------------------------------------------------------------------

class _GovInput(BaseModel):
    agent_type: str = "gov_test"
    text: str
    session_id: str = ""


class TestAgentGovernanceHooks:

    @pytest.mark.asyncio
    async def test_pre_execution_block_raises(self, tmp_path):
        """Agent with BLOCK policy raises GovernancePolicyViolation on SSN in payload."""
        from core.agent import Agent
        from core.agent_definition import AgentDefinition
        from governance.policy import GovernancePolicy, DetectorConfig, PolicyAction

        policy = GovernancePolicy(
            pre_execution=[
                DetectorConfig(
                    detector_class="governance.detectors.RegexDetector",
                    entities=["US_SSN"],
                    action=PolicyAction.BLOCK,
                )
            ],
            audit_sinks=[AuditSinkType.STDOUT],
        )
        defn = AgentDefinition(
            name="gov_test",
            prompt_template="Process: {text}",
            input_schema=_GovInput,
            governance_policy=policy,
        )
        agent = Agent(defn)

        # Patch astream so it never actually calls an LLM
        async def _never_called(payload):
            raise AssertionError("LLM should not be called after BLOCK")
            yield ""  # make it a generator

        with patch.object(agent._adapter, "astream", side_effect=_never_called):
            with pytest.raises(GovernancePolicyViolation, match="BLOCK"):
                async for _ in agent.run(
                    {"agent_type": "gov_test", "text": "SSN 123-45-6789", "session_id": ""},
                    session_id="test-session",
                ):
                    pass

    @pytest.mark.asyncio
    async def test_pre_execution_flag_passes_through(self, tmp_path):
        """FLAG action lets the call proceed and sets flagged=True in audit entry."""
        from core.agent import Agent
        from core.agent_definition import AgentDefinition
        from governance.policy import GovernancePolicy, DetectorConfig, PolicyAction

        written_entries: list[AuditEntry] = []

        class _CaptureSink:
            async def write(self, entry: AuditEntry) -> None:
                written_entries.append(entry)

        policy = GovernancePolicy(
            pre_execution=[
                DetectorConfig(
                    detector_class="governance.detectors.RegexDetector",
                    entities=["EMAIL_ADDRESS"],
                    action=PolicyAction.FLAG,
                )
            ],
            audit_sinks=[AuditSinkType.STDOUT],
        )
        defn = AgentDefinition(
            name="gov_test",
            prompt_template="Process: {text}",
            input_schema=_GovInput,
            governance_policy=policy,
        )
        agent = Agent(defn)

        async def _fake_stream(payload):
            yield "response text"

        with patch.object(agent._adapter, "astream", side_effect=_fake_stream):
            with patch("governance.audit.StdoutAuditSink", return_value=_CaptureSink()):
                chunks = []
                async for chunk in agent.run(
                    {"agent_type": "gov_test", "text": "email alice@example.com", "session_id": ""},
                    session_id="test-session",
                ):
                    chunks.append(chunk)

        assert chunks == ["response text"]
        assert len(written_entries) == 1
        entry = written_entries[0]
        assert entry.flagged is True
        assert any(a["entity_type"] == "EMAIL_ADDRESS" for a in entry.governance_actions)

    @pytest.mark.asyncio
    async def test_no_governance_policy_passes_through(self):
        """Agent without governance_policy works exactly as before."""
        from core.agent import Agent
        from core.agent_definition import AgentDefinition

        defn = AgentDefinition(
            name="plain",
            prompt_template="Answer: {text}",
            input_schema=_GovInput,
        )
        agent = Agent(defn)

        async def _fake_stream(payload):
            yield "plain response"

        with patch.object(agent._adapter, "astream", side_effect=_fake_stream):
            chunks = []
            async for chunk in agent.run(
                {"agent_type": "plain", "text": "Hello world", "session_id": ""},
                session_id="s1",
            ):
                chunks.append(chunk)

        assert chunks == ["plain response"]

    @pytest.mark.asyncio
    async def test_audit_entry_written_to_local_file(self, tmp_path):
        """Successful run with LOCAL_FILE sink produces a valid JSONL audit entry."""
        from core.agent import Agent
        from core.agent_definition import AgentDefinition
        from governance.policy import GovernancePolicy, AuditSinkType
        from governance.audit import LocalFileAuditSink

        log_path = str(tmp_path / "audit.jsonl")

        policy = GovernancePolicy(audit_sinks=[AuditSinkType.LOCAL_FILE])
        defn = AgentDefinition(
            name="gov_test",
            prompt_template="Answer: {text}",
            input_schema=_GovInput,
            governance_policy=policy,
        )
        agent = Agent(defn)

        async def _fake_stream(payload):
            yield "result"

        # Patch LocalFileAuditSink to use tmp_path
        with patch.object(agent._adapter, "astream", side_effect=_fake_stream):
            with patch(
                "governance.audit.LocalFileAuditSink",
                return_value=LocalFileAuditSink(log_path=log_path),
            ):
                async for _ in agent.run(
                    {"agent_type": "gov_test", "text": "safe input", "session_id": ""},
                    session_id="s1",
                ):
                    pass

        assert Path(log_path).exists()
        lines = Path(log_path).read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["agent_type"] == "gov_test"
        assert data["session_id"] == "s1"
        assert data["prompt_hash"]  # non-empty SHA-256
        assert data["response_hash"]
