from pydantic import BaseModel
from praktor.core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink

_PROMPT = """You are an experienced resume writer specializing in leadership roles in Data Science, AI, and Engineering.

Write a tailored resume for the {job_title} role at {company} with bullet-point achievements that show measurable impact and metrics.

Job Description:
{job_description}

Resume:"""


class JobApplicationInput(BaseModel):
    agent_type: str = "job_application"
    job_title: str
    company: str
    job_description: str
    session_id: str = ""


JobApplicationDefinition = AgentDefinition(
    name="job_application",
    prompt_template=_PROMPT,
    input_schema=JobApplicationInput,
    memory_policy=MemoryPolicy.NONE,
    output_sink=OutputSink.BOTH,
    output_file="resume_jd",
)
