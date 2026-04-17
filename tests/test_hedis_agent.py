"""
HEDIS gap agent tests — ReAct loop, output parsing, escalation guardrails.

Covers:
  - parse_next_best_action: structured output extraction
  - Safety override: low confidence → escalate
  - Escalation on critical tool failure (simulated)
  - Dry-run agent execution (no Ollama required)
  - Degraded tool paths (tool returns empty / error text)

Run:
    PYTHONPATH=praktor pytest tests/test_hedis_agent.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))


# ---------------------------------------------------------------------------
# parse_next_best_action tests
# ---------------------------------------------------------------------------

class TestParseNextBestAction:

    def _parse(self, text: str, member: str = "abc123def456abc1") -> dict:
        from clinical.agents.hedis_gap_agent import parse_next_best_action
        return parse_next_best_action(text, member)

    def test_parses_all_fields(self):
        text = """
ACTION_TYPE: pharmacy_refill_reminder
PRIORITY_SCORE: 8.5
MEASURE: MAC
CLOSURE_PROBABILITY: 0.72
RATIONALE: Member has open MAC gap with PDC 0.62 below 0.80 threshold.
DRAFT_MESSAGE: Please refill your statin prescription.
LANGUAGE: en
"""
        result = self._parse(text)
        assert result["action_type"] == "pharmacy_refill_reminder"
        assert result["priority_score"] == 8.5
        assert result["measure_id"] == "MAC"
        assert abs(result["closure_probability"] - 0.72) < 0.001
        assert result["language"] == "en"
        assert "statin" in result["draft_content"]

    def test_missing_fields_use_defaults(self):
        result = self._parse("No structured output here.")
        assert result["action_type"] == "escalate"
        assert result["measure_id"] == "unknown"
        assert result["priority_score"] == 0.0
        assert result["closure_probability"] == 0.0

    def test_low_closure_probability_forces_escalate(self):
        text = """
ACTION_TYPE: pharmacy_refill_reminder
PRIORITY_SCORE: 5.0
MEASURE: MAC
CLOSURE_PROBABILITY: 0.35
RATIONALE: Marginal case.
DRAFT_MESSAGE: Please refill.
LANGUAGE: en
"""
        result = self._parse(text)
        assert result["action_type"] == "escalate", (
            "closure_probability 0.35 < 0.4 must force escalate"
        )

    def test_exactly_04_does_not_escalate(self):
        text = """
ACTION_TYPE: care_plan_outreach
PRIORITY_SCORE: 4.0
MEASURE: BCS
CLOSURE_PROBABILITY: 0.40
RATIONALE: Borderline case.
DRAFT_MESSAGE: Please schedule your mammogram.
LANGUAGE: en
"""
        result = self._parse(text)
        assert result["action_type"] == "care_plan_outreach", (
            "closure_probability == 0.4 should NOT force escalate"
        )

    def test_explicit_escalate_preserved(self):
        text = """
ACTION_TYPE: escalate
PRIORITY_SCORE: 9.0
MEASURE: MAP
CLOSURE_PROBABILITY: 0.20
RATIONALE: Critical data unavailable — tool failure.
DRAFT_MESSAGE: Escalate to care manager.
LANGUAGE: en
"""
        result = self._parse(text)
        assert result["action_type"] == "escalate"

    def test_member_hash_preserved(self):
        result = self._parse("Minimal output.", member="deadbeef12345678")
        assert result["member_id_hash"] == "deadbeef12345678"

    def test_timestamp_is_float(self):
        result = self._parse("Minimal output.")
        assert isinstance(result["timestamp"], float)
        assert result["timestamp"] > 0

    def test_case_insensitive_field_matching(self):
        text = """
action_type: pcp_coordination
priority_score: 6.0
measure: MAD
closure_probability: 0.60
rationale: Diabetes gap open.
draft_message: Please see your doctor.
language: vi
"""
        result = self._parse(text)
        assert result["action_type"] == "pcp_coordination"
        assert result["language"] == "vi"

    def test_multiline_draft_message(self):
        text = """
ACTION_TYPE: pharmacy_refill_reminder
PRIORITY_SCORE: 7.0
MEASURE: MAC
CLOSURE_PROBABILITY: 0.65
RATIONALE: Multi-line test.
DRAFT_MESSAGE: Line one of the message.
Line two continues here.
Line three as well.
LANGUAGE: en
"""
        result = self._parse(text)
        assert "Line one" in result["draft_content"]


# ---------------------------------------------------------------------------
# HEDISGapDefinition smoke test
# ---------------------------------------------------------------------------

class TestHEDISGapDefinition:

    def test_definition_has_required_fields(self):
        from clinical.agents.hedis_gap_agent import HEDISGapDefinition
        defn = HEDISGapDefinition
        assert defn.name == "hedis_gap"
        assert defn.max_steps == 7
        assert defn.temperature == 0.0

    def test_definition_has_all_tools(self):
        from clinical.agents.hedis_gap_agent import HEDISGapDefinition
        tools = HEDISGapDefinition.tools
        expected = {
            "gap_registry", "drug_adherence", "claims_lookup",
            "ehr_lookup", "sdoh_lookup", "outreach_history", "measure_criteria",
        }
        assert expected.issubset(set(tools)), f"Missing tools: {expected - set(tools)}"

    def test_prompt_template_has_required_variables(self):
        from clinical.agents.hedis_gap_agent import HEDISGapDefinition
        prompt = HEDISGapDefinition.prompt_template
        for var in ("{member_id_hash_short}", "{measurement_year}"):
            assert var in prompt, f"Prompt missing variable: {var}"

    def test_prompt_references_stars_weights(self):
        from clinical.agents.hedis_gap_agent import HEDISGapDefinition
        prompt = HEDISGapDefinition.prompt_template
        assert "STARS" in prompt or "stars_weight" in prompt.lower()

    def test_prompt_references_escalation(self):
        from clinical.agents.hedis_gap_agent import HEDISGapDefinition
        prompt = HEDISGapDefinition.prompt_template
        assert "escalate" in prompt.lower() or "ESCALATE" in prompt


# ---------------------------------------------------------------------------
# Degraded tool path tests (tools return error/empty text)
# ---------------------------------------------------------------------------

class TestDegradedToolPaths:
    """
    Verify parse_next_best_action handles tool failure responses gracefully.
    When a tool returns an error, the LLM should output ESCALATE.
    We test the parser's safety override handles any output correctly.
    """

    def _parse(self, text: str) -> dict:
        from clinical.agents.hedis_gap_agent import parse_next_best_action
        return parse_next_best_action(text, "testmember0000001234")

    def test_critical_data_unavailable_escalates(self):
        """If LLM outputs the critical failure sentinel, parser escalates."""
        text = """
ACTION_TYPE: CRITICAL_DATA_UNAVAILABLE
PRIORITY_SCORE: 0.0
MEASURE: unknown
CLOSURE_PROBABILITY: 0.0
RATIONALE: Tool failure — gap registry unavailable.
DRAFT_MESSAGE: Escalating to care manager.
LANGUAGE: en
"""
        result = self._parse(text)
        # closure_prob 0.0 < 0.4 → safety override
        assert result["action_type"] == "escalate"

    def test_empty_observation_response_escalates(self):
        """Entirely empty response → defaults to escalate (0.0 closure prob)."""
        result = self._parse("")
        assert result["action_type"] == "escalate"
        assert result["closure_probability"] == 0.0

    def test_garbage_output_escalates(self):
        """Malformed output → safe defaults → escalate."""
        result = self._parse("I don't know what to do here. The data is incomplete.")
        assert result["action_type"] == "escalate"


# ---------------------------------------------------------------------------
# Integration: dry-run agent execution
# ---------------------------------------------------------------------------

class TestDryRunExecution:
    """
    Run the HEDIS agent with mocked adapters (no Ollama required).
    Verifies the full ReAct loop + parse pipeline.
    """

    @pytest.mark.asyncio
    async def test_dry_run_produces_action(self, tmp_path):
        """Agent dry-run returns a parseable action dict."""
        import dataclasses
        from unittest.mock import AsyncMock, MagicMock, patch

        from clinical.agents.hedis_gap_agent import HEDISGapDefinition, parse_next_best_action
        from clinical.schemas import hash_member_id
        from core.agent import Agent

        dry_response = """Thought: I have all the information I need.
Final Answer:
ACTION_TYPE: pharmacy_refill_reminder
PRIORITY_SCORE: 9.0
MEASURE: MAC
CLOSURE_PROBABILITY: 0.72
RATIONALE: Member has open MAC gap. PDC=0.62 below 0.80. Statin refill overdue.
DRAFT_MESSAGE: Please refill your statin prescription at your pharmacy.
LANGUAGE: en"""

        async def mock_ainvoke(payload, call_span=None):
            return dry_response

        async def mock_astream(payload, call_span=None):
            for chunk in dry_response.split(" "):
                yield chunk + " "

        defn = dataclasses.replace(HEDISGapDefinition, llm_model="dry-run-mock")
        # Patch AsyncLLMAdapter at the module level so the lazily-created
        # _react_adapter picks up the mock (it's built inside _react_loop).
        with patch("core.agent.AsyncLLMAdapter") as MockAdapter:
            instance = MagicMock()
            instance.ainvoke = mock_ainvoke
            instance.astream = mock_astream
            MockAdapter.return_value = instance
            agent = Agent(defn)

            member_hash = hash_member_id("TEST-DRY-001")
            payload = {
                "agent_type": "hedis_gap",
                "member_id_hash": member_hash,
                "member_id_hash_short": member_hash[:12],
                "measurement_year": 2024,
                "history": "",
            }

            chunks = []
            async for chunk in agent.run(payload, session_id="test-dry-run"):
                chunks.append(chunk)

        full = "".join(chunks)
        action = parse_next_best_action(full, member_hash)

        assert action["action_type"] == "pharmacy_refill_reminder"
        assert action["measure_id"] == "MAC"
        assert action["closure_probability"] >= 0.4
        assert action["member_id_hash"] == member_hash

    @pytest.mark.asyncio
    async def test_dry_run_escalates_on_low_confidence(self, tmp_path):
        """Agent dry-run with low confidence output escalates correctly."""
        import dataclasses

        from clinical.agents.hedis_gap_agent import HEDISGapDefinition, parse_next_best_action
        from clinical.schemas import hash_member_id
        from core.agent import Agent

        low_confidence_response = """Final Answer:
ACTION_TYPE: pharmacy_refill_reminder
PRIORITY_SCORE: 2.0
MEASURE: BCS
CLOSURE_PROBABILITY: 0.25
RATIONALE: Very uncertain.
DRAFT_MESSAGE: Maybe try outreach?
LANGUAGE: en"""

        async def mock_ainvoke_low(payload, call_span=None):
            return low_confidence_response

        async def mock_astream_low(payload, call_span=None):
            for chunk in low_confidence_response.split(" "):
                yield chunk + " "

        defn = dataclasses.replace(HEDISGapDefinition, llm_model="dry-run-mock")
        from unittest.mock import MagicMock, patch
        with patch("core.agent.AsyncLLMAdapter") as MockAdapter:
            instance = MagicMock()
            instance.ainvoke = mock_ainvoke_low
            instance.astream = mock_astream_low
            MockAdapter.return_value = instance
            agent = Agent(defn)

            member_hash = hash_member_id("TEST-DRY-002")
            payload = {
                "agent_type": "hedis_gap",
                "member_id_hash": member_hash,
                "member_id_hash_short": member_hash[:12],
                "measurement_year": 2024,
                "history": "",
            }

            chunks = []
            async for chunk in agent.run(payload, session_id="test-low-conf"):
                chunks.append(chunk)

        action = parse_next_best_action("".join(chunks), member_hash)
        assert action["action_type"] == "escalate", (
            "closure_probability 0.25 < 0.4 must force escalate"
        )
