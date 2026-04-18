from pydantic import BaseModel
from praktor.core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink

_PROMPT = """You are a teacher and expert in machine learning, artificial intelligence, Generative AI, and data science.

Topic: {search}
Emphasis: {content}

Provide a thorough, well-structured response covering:
1. Core concepts and definitions
2. Practical applications
3. Key considerations and trade-offs

Response:"""


class SearchInput(BaseModel):
    agent_type: str = "search"
    search: str
    content: str
    session_id: str = ""


SearchDefinition = AgentDefinition(
    name="search",
    prompt_template=_PROMPT,
    input_schema=SearchInput,
    memory_policy=MemoryPolicy.SHORT_TERM,
    output_sink=OutputSink.BOTH,
    output_file="communication_search",
)
