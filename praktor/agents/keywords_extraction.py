from pydantic import BaseModel
from praktor.core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink

_PROMPT = """You are an expert resume analyst and career coach.

Analyze the resume and job description below to produce a comprehensive keyword gap analysis.

Job Title: {job_title}
Company: {company}

Resume:
{resume}

Job Description:
{job_description}

Produce three sections:

## Resume Keywords
List the 30 most important skills, tools, and concepts from the resume.

## Job Description Keywords
List the 30 most important skills, tools, and concepts from the job description.

## Keyword Gaps
Identify the top 15 keywords present in the job description but missing or weak in the resume.
For each gap, briefly explain why it matters for this role.

Analysis:"""


class KeywordsExtractionInput(BaseModel):
    agent_type: str = "keywords_extraction"
    job_title: str
    company: str
    job_description: str
    resume: str
    session_id: str = ""


KeywordsExtractionDefinition = AgentDefinition(
    name="keywords_extraction",
    prompt_template=_PROMPT,
    input_schema=KeywordsExtractionInput,
    memory_policy=MemoryPolicy.NONE,
    output_sink=OutputSink.BOTH,
    output_file="keywords_analysis",
)
