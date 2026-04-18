"""
Claims lookup tool — retrieves claims history and pharmacy fills for a member.

Input format (JSON string):
    {"member_id_hash": "...", "drug_class": "statin"}  # rx claims by drug class
    {"member_id_hash": "...", "icd_code": "E11"}       # medical claims by diagnosis
    {"member_id_hash": "..."}                           # all recent claims

Returns structured summary of claims — never raw PHI.
All data retrieved is pre-de-identified in the ingestion pipeline.
"""

from __future__ import annotations

import json

from praktor.core.tool import ToolResult, register_tool
from praktor.settings import create_log

log = create_log()


class ClaimsLookupTool:
    name = "claims_lookup"
    description = (
        "Look up claims history and pharmacy fills for a member. "
        "Input: JSON with 'member_id_hash' and optional 'drug_class' (statin/oral_hypoglycemic/rasa/ace_inhibitor/arb) "
        "or 'icd_code'. Returns claims summary with dates, drug names, days supply."
    )

    async def __call__(self, input: str) -> ToolResult:
        try:
            params = self._parse(input)
            member_id_hash = params.get("member_id_hash", "").strip()
            if not member_id_hash:
                return ToolResult(content="", error="member_id_hash is required")

            from praktor.clinical.data.clinical_store import get_clinical_store
            store = get_clinical_store()

            drug_class = params.get("drug_class")
            claims = store.get_claims(member_id_hash, drug_class=drug_class, limit=30)

            if not claims:
                return ToolResult(
                    content=f"No claims found for member (drug_class={drug_class or 'any'}).",
                    metadata={"member_id_hash": member_id_hash, "count": 0},
                )

            lines = [f"Claims history ({len(claims)} records):"]
            for c in claims:
                icd = json.loads(c["icd_codes"]) if c.get("icd_codes") else []
                line = f"- {c['service_date']} | {c['claim_type']} | {c.get('drug_name') or ','.join(icd) or 'N/A'}"
                if c.get("days_supply"):
                    line += f" | {c['days_supply']}d supply"
                if c.get("drug_class"):
                    line += f" | class={c['drug_class']}"
                lines.append(line)

            return ToolResult(
                content="\n".join(lines),
                metadata={"member_id_hash": member_id_hash, "count": len(claims)},
            )
        except Exception as e:
            log.error(f"ClaimsLookupTool failed: {e}")
            return ToolResult(content="", error=f"claims_lookup failed: {e}")

    def _parse(self, input: str) -> dict:
        input = input.strip()
        if input.startswith("{"):
            return json.loads(input)
        # Plain member_id_hash string
        return {"member_id_hash": input}


register_tool(ClaimsLookupTool())
