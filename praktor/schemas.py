from pydantic import BaseModel, field_validator
from typing import Literal


AGENT_TYPES = Literal[
    "job_application",
    "cover_letter",
    "keywords_extraction",
    "job_interview",
    "thank_you",
    "search",
    "message",
]


class BaseAgentMessage(BaseModel):
    agent_type: AGENT_TYPES


class JobApplicationMessage(BaseAgentMessage):
    agent_type: Literal["job_application"] = "job_application"
    job_title: str
    company: str
    job_description: str


class CoverLetterMessage(BaseAgentMessage):
    agent_type: Literal["cover_letter"] = "cover_letter"
    job_title: str
    company: str
    job_description: str


class KeywordsExtractionMessage(BaseAgentMessage):
    agent_type: Literal["keywords_extraction"] = "keywords_extraction"
    job_title: str
    company: str
    job_description: str


class JobInterviewMessage(BaseAgentMessage):
    agent_type: Literal["job_interview"] = "job_interview"
    search: str
    content: str


class ThankYouMessage(BaseAgentMessage):
    agent_type: Literal["thank_you"] = "thank_you"
    adjective: str
    position: str
    content: str


class SearchMessage(BaseAgentMessage):
    agent_type: Literal["search"] = "search"
    search: str
    content: str


class MessageMessage(BaseAgentMessage):
    agent_type: Literal["message"] = "message"
    topic: str
    emotion: str


_SCHEMA_MAP = {
    "job_application": JobApplicationMessage,
    "cover_letter": CoverLetterMessage,
    "keywords_extraction": KeywordsExtractionMessage,
    "job_interview": JobInterviewMessage,
    "thank_you": ThankYouMessage,
    "search": SearchMessage,
    "message": MessageMessage,
}


def parse_message(data: dict) -> BaseAgentMessage:
    """Parse and validate a raw dict into the appropriate typed message schema."""
    agent_type = data.get("agent_type")
    if agent_type not in _SCHEMA_MAP:
        raise ValueError(
            f"Unknown or missing agent_type '{agent_type}'. "
            f"Valid types: {list(_SCHEMA_MAP.keys())}"
        )
    return _SCHEMA_MAP[agent_type](**data)
