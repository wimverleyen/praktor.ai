import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'praktor'))

from pydantic import BaseModel
from core.agent_definition import (
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
