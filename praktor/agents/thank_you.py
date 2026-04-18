from pydantic import BaseModel
from praktor.core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink

_PROMPT = """You are a business executive and chief data scientist.

Write a {adjective} thank you email responding to {content} for the {position} role.

Focus on:
- Specific points from the conversation that resonated
- How your background aligns with their needs
- Genuine appreciation without being sycophantic
- A clear, professional closing

Email:"""


class ThankYouInput(BaseModel):
    agent_type: str = "thank_you"
    adjective: str
    position: str
    content: str
    session_id: str = ""


ThankYouDefinition = AgentDefinition(
    name="thank_you",
    prompt_template=_PROMPT,
    input_schema=ThankYouInput,
    memory_policy=MemoryPolicy.NONE,
    output_sink=OutputSink.BOTH,
    output_file="communication_thank_you",
)
