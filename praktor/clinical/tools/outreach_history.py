"""
Outreach history tool — prior contact attempts and outcomes for a member.

Input: JSON with member_id_hash and optional measure_id
Returns: history of outreach attempts with channel, outcome, date
"""

from __future__ import annotations

import json

from core.tool import ToolResult, register_tool
from settings import create_log

log = create_log()


class OutreachHistoryTool:
    name = "outreach_history"
    description = (
        "Look up prior outreach attempts for a member. "
        "Input: JSON with 'member_id_hash' and optional 'measure_id'. "
        "Returns: contact history with channel (phone/letter/sms/portal), outcome, and date."
    )

    async def __call__(self, input: str) -> ToolResult:
        try:
            params = self._parse(input)
            member_id_hash = params.get("member_id_hash", "").strip()
            if not member_id_hash:
                return ToolResult(content="", error="member_id_hash is required")

            measure_id = params.get("measure_id")

            from clinical.data.clinical_store import get_clinical_store
            store = get_clinical_store()
            history = store.get_outreach(member_id_hash, measure_id=measure_id, limit=10)

            if not history:
                scope = f" for measure {measure_id}" if measure_id else ""
                return ToolResult(
                    content=f"No prior outreach attempts{scope}.",
                    metadata={"member_id_hash": member_id_hash, "count": 0},
                )

            reached = sum(1 for h in history if h.get("outcome") == "reached")
            lines = [f"Outreach history ({len(history)} attempts, {reached} reached):"]
            for h in history:
                measure = f" [{h['measure_id']}]" if h.get("measure_id") else ""
                notes = f" — {h['notes']}" if h.get("notes") else ""
                lines.append(
                    f"- {h['contact_date']} | {h.get('channel', 'unknown')}"
                    f"{measure} | outcome={h.get('outcome', 'unknown')}{notes}"
                )

            return ToolResult(
                content="\n".join(lines),
                metadata={"member_id_hash": member_id_hash, "count": len(history)},
            )
        except Exception as e:
            log.error(f"OutreachHistoryTool failed: {e}")
            return ToolResult(content="", error=f"outreach_history failed: {e}")

    def _parse(self, input: str) -> dict:
        input = input.strip()
        if input.startswith("{"):
            return json.loads(input)
        return {"member_id_hash": input}


register_tool(OutreachHistoryTool())
