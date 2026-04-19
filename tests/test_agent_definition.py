import sys
from pathlib import Path
from unittest.mock import patch

from pydantic import BaseModel
from praktor.core.agent_definition import (
    AgentDefinition,
    ImprovementPass,
    MemoryPolicy,
    OutputSink,
)


class _SimpleInput(BaseModel):
    agent_type: str = "simple"
    topic: str


class TestAgentDefinition:

    def test_defaults(self):
        with patch("praktor.core.agent_definition._DEFAULT_MODEL", "qwen2.5"):
            defn = AgentDefinition(
                name="simple",
                prompt_template="Write about {topic}",
                input_schema=_SimpleInput,
            )
        assert defn.llm_model == "qwen2.5"
        assert defn.temperature == 0.0
        assert defn.memory_policy == MemoryPolicy.NONE
        assert defn.output_sink == OutputSink.STREAM
        assert defn.tools == []
        assert defn.improvement_passes == []
        assert defn.max_steps == 1

    def test_custom_values(self):
        defn = AgentDefinition(
            name="custom",
            prompt_template="Search {query}",
            input_schema=_SimpleInput,
            llm_model="claude-sonnet-4-6",
            temperature=0.7,
            memory_policy=MemoryPolicy.SHORT_TERM,
            output_sink=OutputSink.BOTH,
            output_file="output",
            tools=["web_search"],
            max_steps=3,
        )
        assert defn.llm_model == "claude-sonnet-4-6"
        assert defn.temperature == 0.7
        assert defn.memory_policy == MemoryPolicy.SHORT_TERM
        assert "web_search" in defn.tools

    def test_improvement_passes(self):
        defn = AgentDefinition(
            name="multi",
            prompt_template="Draft {topic}",
            input_schema=_SimpleInput,
            improvement_passes=[
                ImprovementPass(prompt_template="Improve {previous_response}", output_key="previous_response"),
                ImprovementPass(prompt_template="Polish {previous_response}", output_key="previous_response"),
            ],
        )
        assert len(defn.improvement_passes) == 2
        assert defn.improvement_passes[0].output_key == "previous_response"

    def test_prompt_template_hash_is_sha256(self):
        import hashlib
        template = "Write about {topic}"
        defn = AgentDefinition(
            name="h",
            prompt_template=template,
            input_schema=_SimpleInput,
        )
        expected = hashlib.sha256(template.encode("utf-8")).hexdigest()
        assert defn.prompt_template_hash == expected

    def test_prompt_version_defaults_to_hash_prefix(self):
        defn = AgentDefinition(
            name="h",
            prompt_template="Write about {topic}",
            input_schema=_SimpleInput,
        )
        assert defn.prompt_version == defn.prompt_template_hash[:12]

    def test_explicit_prompt_version_preserved(self):
        defn = AgentDefinition(
            name="h",
            prompt_template="Write about {topic}",
            input_schema=_SimpleInput,
            prompt_version="v2.0.0",
        )
        assert defn.prompt_version == "v2.0.0"

    def test_different_templates_yield_different_hashes(self):
        a = AgentDefinition(name="a", prompt_template="Template A {x}", input_schema=_SimpleInput)
        b = AgentDefinition(name="b", prompt_template="Template B {x}", input_schema=_SimpleInput)
        assert a.prompt_template_hash != b.prompt_template_hash

    def test_input_schema_validation(self):
        defn = AgentDefinition(
            name="simple",
            prompt_template="Write about {topic}",
            input_schema=_SimpleInput,
        )
        # Valid
        msg = defn.input_schema(topic="AI")
        assert msg.topic == "AI"

        # Invalid
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            defn.input_schema()  # missing required field


# ---------------------------------------------------------------------------
# PR11a — registry_key field + validator
# ---------------------------------------------------------------------------

class TestRegistryKey:

    def test_registry_key_field_present_no_error_when_none(self):
        """registry_key defaults to None — no validation fires."""
        defn = AgentDefinition(
            name="no_key",
            prompt_template="Write about {topic}",
            input_schema=_SimpleInput,
        )
        assert defn.registry_key is None

    def test_registry_key_raises_value_error_when_not_in_registry(self):
        """registry_key set to unknown key raises ValueError at instantiation."""
        from unittest.mock import patch, MagicMock
        import pytest

        mock_registry = MagicMock()
        mock_registry.get_active.return_value = None  # key not found

        with patch(
            "praktor.core.prompt_registry.PromptRegistry",
            return_value=mock_registry,
        ):
            with pytest.raises(ValueError, match="registry_key"):
                AgentDefinition(
                    name="bad_key",
                    prompt_template="Write about {topic}",
                    input_schema=_SimpleInput,
                    registry_key="nonexistent_key",
                )

    def test_registry_key_no_error_when_key_found_in_registry(self):
        """registry_key set to valid key (get_active returns a version) does not raise."""
        from unittest.mock import patch, MagicMock

        mock_registry = MagicMock()
        mock_version = MagicMock()
        mock_registry.get_active.return_value = mock_version  # key found

        with patch(
            "praktor.core.prompt_registry.PromptRegistry",
            return_value=mock_registry,
        ):
            defn = AgentDefinition(
                name="good_key",
                prompt_template="Write about {topic}",
                input_schema=_SimpleInput,
                registry_key="judge_hedis",
            )
            assert defn.registry_key == "judge_hedis"
