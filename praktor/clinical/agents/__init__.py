"""
Clinical agent registry — importing this module registers all clinical agents.

Usage:
    import clinical.agents  # triggers registration
    from core.router import get_global_router
    router = get_global_router()  # clinical agents now registered
"""

from core.router import get_global_router

from clinical.agents.hedis_gap_agent import HEDISGapDefinition
from clinical.agents.diabetes_hedis_agent import DiabetesHEDISDefinition

_router = get_global_router()
_router.register(HEDISGapDefinition)
_router.register(DiabetesHEDISDefinition)

__all__ = ["HEDISGapDefinition", "DiabetesHEDISDefinition"]
