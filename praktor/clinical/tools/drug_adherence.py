"""
Drug adherence (PDC) tool — reads pre-computed PDC scores from the ingestion pipeline.

PDC = Proportion of Days Covered.
Computed once per weekly ingestion cycle. Never computed at query time.

Input: JSON with member_id_hash and optional drug_class
Returns: PDC scores with threshold status, days until next gap, refill recommendation
"""

from __future__ import annotations

import json

from praktor.core.tool import ToolResult, register_tool
from praktor.settings import create_log

log = create_log()


class DrugAdherenceTool:
    name = "drug_adherence"
    description = (
        "Look up pre-computed medication adherence (PDC) scores for a member. "
        "PDC >= 0.80 required for HEDIS triple-weighted measures. "
        "Input: JSON with 'member_id_hash' and optional 'drug_class' "
        "(statin/oral_hypoglycemic/rasa/ace_inhibitor/arb). "
        "Returns: current PDC, threshold, gap size, days until gap, refill recommendation."
    )

    async def __call__(self, input: str) -> ToolResult:
        try:
            params = self._parse(input)
            member_id_hash = params.get("member_id_hash", "").strip()
            if not member_id_hash:
                return ToolResult(content="", error="member_id_hash is required")

            drug_class = params.get("drug_class")

            from praktor.clinical.data.clinical_store import get_clinical_store
            store = get_clinical_store()
            scores = store.get_pdc(member_id_hash, drug_class=drug_class)

            if not scores:
                return ToolResult(
                    content=f"No PDC scores found for member "
                            f"(drug_class={drug_class or 'any'}). "
                            "Ensure ingestion pipeline has been run.",
                    metadata={"member_id_hash": member_id_hash, "count": 0},
                )

            lines = [f"PDC scores ({len(scores)} drug class(es)):"]
            for s in scores:
                pdc = s["pdc"]
                threshold = s.get("pdc_threshold", 0.80) if "pdc_threshold" in s else 0.80
                status = "MEETS THRESHOLD" if pdc >= threshold else "BELOW THRESHOLD"
                gap_days = s.get("days_until_gap", 0)

                line = (
                    f"- {s['drug_class']} [{s['measure_id']}]: PDC={pdc:.3f} "
                    f"(threshold={threshold:.2f}) — {status}"
                )
                if s.get("last_fill_date"):
                    line += f" | last fill: {s['last_fill_date']}"
                if s.get("next_fill_due"):
                    line += f" | next fill due: {s['next_fill_due']}"
                if gap_days > 0:
                    line += f" | gap opens in {gap_days}d"
                elif gap_days == 0 and pdc < threshold:
                    line += " | GAP ACTIVE — refill needed now"

                # Refill recommendation
                if pdc < threshold:
                    fills_needed = self._fills_to_close(pdc, threshold, s.get("fills_count", 0))
                    line += f" | ~{fills_needed} fill(s) needed to reach threshold"

                lines.append(line)

            return ToolResult(
                content="\n".join(lines),
                metadata={"member_id_hash": member_id_hash, "count": len(scores)},
            )
        except Exception as e:
            log.error(f"DrugAdherenceTool failed: {e}")
            return ToolResult(content="", error=f"drug_adherence failed: {e}")

    def _fills_to_close(self, current_pdc: float, threshold: float, fills_so_far: int) -> int:
        """Rough estimate: how many 30-day fills needed to cross the threshold."""
        # PDC = total days covered / 365
        days_covered = current_pdc * 365
        days_needed = threshold * 365
        gap_days = days_needed - days_covered
        return max(1, int(gap_days / 30) + 1)

    def _parse(self, input: str) -> dict:
        input = input.strip()
        if input.startswith("{"):
            return json.loads(input)
        return {"member_id_hash": input}


register_tool(DrugAdherenceTool())
