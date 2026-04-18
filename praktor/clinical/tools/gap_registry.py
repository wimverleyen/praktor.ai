"""
HEDIS gap registry tool — retrieves open gaps ranked by priority score.

Input: member_id_hash (string or JSON)
Returns: ranked list of open gaps with priority scores and stars weights.
"""

from __future__ import annotations

import json

from praktor.core.tool import ToolResult, register_tool
from praktor.settings import create_log

log = create_log()


class GapRegistryTool:
    name = "gap_registry"
    description = (
        "Look up open HEDIS quality gaps for a member, ranked by STARS impact. "
        "Input: member_id_hash string. "
        "Returns: ranked gaps with measure name, STARS weight, days remaining, and PDC if applicable."
    )

    async def __call__(self, input: str) -> ToolResult:
        try:
            member_id_hash = self._parse(input)
            if not member_id_hash:
                return ToolResult(content="", error="member_id_hash is required")

            from praktor.clinical.data.clinical_store import get_clinical_store
            from praktor.clinical.schemas import HEDISGap

            store = get_clinical_store()
            raw_gaps = store.get_open_gaps(member_id_hash)

            if not raw_gaps:
                return ToolResult(
                    content="No open HEDIS gaps found for this member.",
                    metadata={"member_id_hash": member_id_hash, "count": 0},
                )

            gaps = []
            for g in raw_gaps:
                gap = HEDISGap(
                    member_id_hash=member_id_hash,
                    measure_id=g["measure_id"],
                    measure_name=g["measure_name"],
                    stars_weight=g["stars_weight"],
                    measurement_year=g["measurement_year"],
                    days_remaining=g["days_remaining"],
                    last_service_date=g.get("last_service_date"),
                    pdc_current=g.get("pdc_current"),
                    pdc_threshold=g.get("pdc_threshold", 0.80),
                )
                gaps.append(gap)

            # Sort by priority score descending
            gaps.sort(key=lambda x: x.priority_score, reverse=True)

            lines = [f"Open HEDIS gaps ({len(gaps)} total), ranked by priority:"]
            for i, gap in enumerate(gaps, 1):
                weight_label = f"{gap.stars_weight:.0f}x STARS"
                pdc_info = ""
                if gap.pdc_current is not None:
                    pdc_info = f" | PDC={gap.pdc_current:.2f} (need {gap.pdc_threshold:.2f})"
                    if gap.pdc_gap:
                        pdc_info += f" | gap={gap.pdc_gap:.2f}"
                lines.append(
                    f"{i}. [{weight_label}] {gap.measure_id}: {gap.measure_name}"
                    f" | {gap.days_remaining}d remaining | priority={gap.priority_score:.3f}"
                    f"{pdc_info}"
                )

            return ToolResult(
                content="\n".join(lines),
                metadata={"member_id_hash": member_id_hash, "count": len(gaps)},
            )
        except Exception as e:
            log.error(f"GapRegistryTool failed: {e}")
            return ToolResult(content="", error=f"gap_registry failed: {e}")

    def _parse(self, input: str) -> str:
        input = input.strip()
        if input.startswith("{"):
            return json.loads(input).get("member_id_hash", "")
        return input


register_tool(GapRegistryTool())
