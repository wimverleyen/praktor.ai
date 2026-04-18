"""
EHR lookup tool — retrieves structured clinical data (labs, vitals, diagnoses).

Input format (JSON string):
    {"member_id_hash": "...", "data_type": "labs", "test_name": "HbA1c"}
    {"member_id_hash": "...", "data_type": "vitals"}
    {"member_id_hash": "...", "data_type": "all"}

In production: swap _query_* methods for FHIR R4 API calls or warehouse queries.
All data is pre-de-identified in the ingestion pipeline.
"""

from __future__ import annotations

import json

from praktor.core.tool import ToolResult, register_tool
from praktor.settings import create_log

log = create_log()


class EHRLookupTool:
    name = "ehr_lookup"
    description = (
        "Look up structured clinical data from EHR: labs (HbA1c, LDL, creatinine, eGFR), "
        "vitals (blood pressure, BMI), and active diagnoses. "
        "Input: JSON with 'member_id_hash', 'data_type' (labs/vitals/all), "
        "and optional 'test_name'."
    )

    async def __call__(self, input: str) -> ToolResult:
        try:
            params = self._parse(input)
            member_id_hash = params.get("member_id_hash", "").strip()
            if not member_id_hash:
                return ToolResult(content="", error="member_id_hash is required")

            data_type = params.get("data_type", "all").lower()
            test_name = params.get("test_name")

            from praktor.clinical.data.clinical_store import get_clinical_store
            store = get_clinical_store()

            parts: list[str] = []

            if data_type in ("labs", "all"):
                labs = store.get_labs(member_id_hash, test_name=test_name, limit=10)
                if labs:
                    parts.append("Labs:")
                    for lab in labs:
                        val = f"{lab['result_value']} {lab.get('result_unit', '')}".strip() \
                            if lab.get("result_value") else lab.get("result_text", "N/A")
                        ref = f" (ref: {lab['reference_range']})" if lab.get("reference_range") else ""
                        parts.append(f"  {lab['test_date']} | {lab['test_name']}: {val}{ref}")
                else:
                    parts.append(f"Labs: No {test_name or ''} results found.")

            if data_type in ("vitals", "all"):
                vitals = store.get_vitals(member_id_hash, limit=3)
                if vitals:
                    parts.append("Vitals:")
                    for v in vitals:
                        bp = f"BP {v['systolic_bp']}/{v['diastolic_bp']}" \
                            if v.get("systolic_bp") else ""
                        bmi = f"BMI {v['bmi']:.1f}" if v.get("bmi") else ""
                        parts.append(f"  {v['recorded_date']} | {' | '.join(x for x in [bp, bmi] if x)}")
                else:
                    parts.append("Vitals: No records found.")

            content = "\n".join(parts) if parts else "No EHR data found for this member."
            return ToolResult(
                content=content,
                metadata={"member_id_hash": member_id_hash, "data_type": data_type},
            )
        except Exception as e:
            log.error(f"EHRLookupTool failed: {e}")
            return ToolResult(content="", error=f"ehr_lookup failed: {e}")

    def _parse(self, input: str) -> dict:
        input = input.strip()
        if input.startswith("{"):
            return json.loads(input)
        return {"member_id_hash": input, "data_type": "all"}


register_tool(EHRLookupTool())
