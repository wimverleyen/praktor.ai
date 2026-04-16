"""
SDOH (Social Determinants of Health) lookup tool.

Returns language preference, health literacy, known barriers, PCP info,
and pharmacy proximity for a member.

Input: member_id_hash string
"""

from __future__ import annotations

import json

from core.tool import ToolResult, register_tool
from settings import create_log

log = create_log()


class SDOHLookupTool:
    name = "sdoh_lookup"
    description = (
        "Look up social determinants of health for a member: language preference, "
        "health literacy level (low/medium/high), SDOH risk, known barriers "
        "(transportation, cost, health literacy), PCP name and language, pharmacy proximity. "
        "Input: member_id_hash string."
    )

    async def __call__(self, input: str) -> ToolResult:
        try:
            member_id_hash = self._parse(input)
            if not member_id_hash:
                return ToolResult(content="", error="member_id_hash is required")

            from clinical.data.clinical_store import get_clinical_store
            store = get_clinical_store()
            member = store.get_member(member_id_hash)

            if not member:
                return ToolResult(
                    content="Member profile not found in SDOH registry.",
                    metadata={"member_id_hash": member_id_hash},
                )

            barriers = []
            if member.get("sdoh_barriers"):
                try:
                    barriers = json.loads(member["sdoh_barriers"])
                except Exception:
                    barriers = [member["sdoh_barriers"]]

            lines = [
                f"Language: {member.get('language', 'en')}",
                f"Health literacy: {member.get('health_literacy', 'medium')}",
                f"SDOH risk: {member.get('sdoh_risk', 'unknown')}",
                f"SDOH barriers: {', '.join(barriers) if barriers else 'none identified'}",
                f"PCP: {member.get('pcp_name', 'unknown')} "
                f"(language: {member.get('pcp_language', 'en')})",
                f"Pharmacy: {member.get('pharmacy_name', 'unknown')} "
                f"({member.get('pharmacy_miles', '?')} mi)",
            ]

            return ToolResult(
                content="\n".join(lines),
                metadata={"member_id_hash": member_id_hash, "sdoh_risk": member.get("sdoh_risk")},
            )
        except Exception as e:
            log.error(f"SDOHLookupTool failed: {e}")
            return ToolResult(content="", error=f"sdoh_lookup failed: {e}")

    def _parse(self, input: str) -> str:
        input = input.strip()
        if input.startswith("{"):
            return json.loads(input).get("member_id_hash", "")
        return input


register_tool(SDOHLookupTool())
