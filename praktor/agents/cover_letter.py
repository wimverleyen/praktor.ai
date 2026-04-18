from pydantic import BaseModel
from praktor.core.agent_definition import AgentDefinition, MemoryPolicy, OutputSink, ImprovementPass

_INITIAL_PROMPT = """You are an experienced professional resume writer specializing in leadership roles in Data Science, AI, and Engineering.

Write a compelling cover letter for the {job_title} role at {company}.

Job Description:
{job_description}

Cover Letter:"""

_IMPROVE_PROMPT_1 = """You are an expert cover letter editor.

Rewrite this cover letter for the {job_title} role at {company} to be more compelling and specific.
- Lead with a strong opening that names a concrete achievement
- Make every paragraph earn its place
- Mirror language from the job description
- End with a confident call to action

Job Description:
{job_description}

Current Cover Letter:
{cover_letter}

Improved Cover Letter:"""

_IMPROVE_PROMPT_2 = """You are a senior hiring manager and executive coach.

Review this cover letter for the {job_title} role at {company} and produce a final, polished version.
- Fix any passive voice
- Sharpen metrics and impact statements
- Ensure the tone matches a senior leadership candidate
- Tighten to 3 focused paragraphs

Job Description:
{job_description}

Current Cover Letter:
{cover_letter}

Final Cover Letter:"""


class CoverLetterInput(BaseModel):
    agent_type: str = "cover_letter"
    job_title: str
    company: str
    job_description: str
    session_id: str = ""


CoverLetterDefinition = AgentDefinition(
    name="cover_letter",
    prompt_template=_INITIAL_PROMPT,
    input_schema=CoverLetterInput,
    memory_policy=MemoryPolicy.NONE,
    output_sink=OutputSink.BOTH,
    output_file="cover_letter_final",
    improvement_passes=[
        ImprovementPass(prompt_template=_IMPROVE_PROMPT_1, output_key="cover_letter"),
        ImprovementPass(prompt_template=_IMPROVE_PROMPT_2, output_key="cover_letter"),
    ],
)
