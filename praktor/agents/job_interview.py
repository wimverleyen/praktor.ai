from pydantic import BaseModel
from core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink

_PROMPT = """You are an expert in machine learning, AI strategy, and data science leadership.

Use the context below to answer the question thoroughly and practically.

Context:
{history}

Question: {search}
Focus on: {content}

Provide a structured, insightful response drawing on the context where relevant.

Answer:"""


class JobInterviewInput(BaseModel):
    agent_type: str = "job_interview"
    search: str
    content: str
    session_id: str = ""


JobInterviewDefinition = AgentDefinition(
    name="job_interview",
    prompt_template=_PROMPT,
    input_schema=JobInterviewInput,
    memory_policy=MemoryPolicy.LONG_TERM,  # Uses FAISS vector store
    output_sink=OutputSink.BOTH,
    output_file="interview_prep",
)
