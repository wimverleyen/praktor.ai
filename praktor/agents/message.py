from pydantic import BaseModel
from praktor.core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink

_PROMPT = """You are a top business executive specialized in artificial intelligence and data science.

Write a concise, professional message about {topic}.

Tone: {emotion}

The message should be genuine, direct, and reflect strong interpersonal awareness.

Message:"""


class MessageInput(BaseModel):
    agent_type: str = "message"
    topic: str
    emotion: str
    session_id: str = ""


MessageDefinition = AgentDefinition(
    name="message",
    prompt_template=_PROMPT,
    input_schema=MessageInput,
    memory_policy=MemoryPolicy.NONE,
    output_sink=OutputSink.BOTH,
    output_file="communication_message",
)
