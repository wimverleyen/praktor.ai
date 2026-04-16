"""
Agent registry — importing this module registers all built-in agents.

Usage:
    import agents  # triggers registration
    from core.router import get_global_router
    router = get_global_router()  # all agents now registered

To add a new agent:
    1. Create praktor/agents/my_agent.py with a MyAgentDefinition instance
    2. Add the import and register() call below
"""

from core.router import get_global_router

import clinical.agents  # registers clinical agents (HEDIS gap closure)

from agents.thank_you import ThankYouDefinition
from agents.message import MessageDefinition
from agents.search import SearchDefinition
from agents.job_application import JobApplicationDefinition
from agents.cover_letter import CoverLetterDefinition
from agents.keywords_extraction import KeywordsExtractionDefinition
from agents.job_interview import JobInterviewDefinition

_router = get_global_router()
_router.register(ThankYouDefinition)
_router.register(MessageDefinition)
_router.register(SearchDefinition)
_router.register(JobApplicationDefinition)
_router.register(CoverLetterDefinition)
_router.register(KeywordsExtractionDefinition)
_router.register(JobInterviewDefinition)

__all__ = [
    "ThankYouDefinition",
    "MessageDefinition",
    "SearchDefinition",
    "JobApplicationDefinition",
    "CoverLetterDefinition",
    "KeywordsExtractionDefinition",
    "JobInterviewDefinition",
]
