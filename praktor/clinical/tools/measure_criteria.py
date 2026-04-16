"""
HEDIS measure criteria tool — returns measure specification and exclusion criteria.

Uses NCQA public HEDIS measure specs only (no MCG licensing required).
Phase 1: medication adherence measures (MAC, MAD, MAP) + key chronic disease measures.

Input: measure_id string (e.g., "MAC", "MAD", "MAP", "CDC-HbA1c")
"""

from __future__ import annotations

from core.tool import ToolResult, register_tool
from settings import create_log

log = create_log()

# NCQA HEDIS 2024 public measure specifications
# Source: https://www.ncqa.org/hedis/measures/
_MEASURE_SPECS: dict[str, dict] = {
    "MAC": {
        "full_name": "Medication Adherence for Cholesterol (Statins)",
        "numerator": "Members who achieved PDC >= 0.80 for statin medications.",
        "denominator": "Members 18+ as of Dec 31 with a statin dispensing event in the measurement year.",
        "pdc_threshold": 0.80,
        "measurement_period": "Full measurement year (Jan 1 – Dec 31)",
        "exclusions": [
            "Hospice care during measurement year",
            "Frailty AND advanced illness",
            "ESRD (end-stage renal disease)",
        ],
        "closure_criteria": "Member fills statin prescription with PDC >= 0.80 by Dec 31.",
        "drug_classes": ["statin"],
        "icd_exclusion_codes": ["Z51.5"],
        "notes": "PDC = proportion of days covered. Days supply sum / days in period.",
        "source": "NCQA HEDIS 2024 Technical Specifications",
    },
    "MAD": {
        "full_name": "Medication Adherence for Diabetes (Oral Hypoglycemics/Injectable)",
        "numerator": "Members who achieved PDC >= 0.80 for oral/injectable hypoglycemic agents.",
        "denominator": "Members 18–75 with diabetes and a hypoglycemic dispensing event.",
        "pdc_threshold": 0.80,
        "measurement_period": "Full measurement year (Jan 1 – Dec 31)",
        "exclusions": [
            "Hospice care during measurement year",
            "Frailty AND advanced illness",
            "ESRD",
            "Gestational diabetes only (ICD-10 O24.4)",
        ],
        "closure_criteria": "Member fills oral/injectable diabetes medication with PDC >= 0.80 by Dec 31.",
        "drug_classes": ["oral_hypoglycemic", "metformin", "sulfonylurea", "dpp4", "sglt2", "glp1"],
        "icd_exclusion_codes": ["O24.4", "Z51.5"],
        "notes": "Insulin-only patients excluded from denominator.",
        "source": "NCQA HEDIS 2024 Technical Specifications",
    },
    "MAP": {
        "full_name": "Medication Adherence for Hypertension (RASA)",
        "numerator": "Members who achieved PDC >= 0.80 for RASA medications.",
        "denominator": "Members 18–85 with hypertension and a RASA dispensing event.",
        "pdc_threshold": 0.80,
        "measurement_period": "Full measurement year (Jan 1 – Dec 31)",
        "exclusions": [
            "Hospice care during measurement year",
            "Frailty AND advanced illness",
            "ESRD",
            "Pregnancy (ICD-10 O10, O11, O13, O14, O16)",
        ],
        "closure_criteria": "Member fills ACE inhibitor, ARB, or other RASA with PDC >= 0.80 by Dec 31.",
        "drug_classes": ["ace_inhibitor", "arb", "direct_renin_inhibitor"],
        "icd_exclusion_codes": ["O10", "O11", "O13", "O14", "O16", "Z51.5"],
        "notes": "RASA = renin-angiotensin system antagonists. Includes ACEi, ARB, DRI.",
        "source": "NCQA HEDIS 2024 Technical Specifications",
    },
    "CBP": {
        "full_name": "Controlling High Blood Pressure",
        "numerator": "Members with most recent BP < 140/90 mmHg.",
        "denominator": "Members 18–85 with hypertension (ICD-10 I10).",
        "pdc_threshold": None,
        "measurement_period": "Most recent BP reading during measurement year",
        "exclusions": [
            "Hospice care",
            "Frailty AND advanced illness",
            "ESRD",
            "Pregnancy",
            "Advanced illness with BP measure exclusion codes",
        ],
        "closure_criteria": "Documented BP reading < 140 mmHg systolic AND < 90 mmHg diastolic.",
        "drug_classes": [],
        "icd_exclusion_codes": ["Z51.5"],
        "notes": "Index date = first hypertension diagnosis. Look-back: 1 year prior to start.",
        "source": "NCQA HEDIS 2024 Technical Specifications",
    },
    "CDC-HbA1c": {
        "full_name": "Comprehensive Diabetes Care: HbA1c Testing",
        "numerator": "Members who had one or more HbA1c tests during the measurement year.",
        "denominator": "Members 18–75 with diabetes (ICD-10 E10, E11, E13).",
        "pdc_threshold": None,
        "measurement_period": "Measurement year (Jan 1 – Dec 31)",
        "exclusions": [
            "Hospice care",
            "Frailty AND advanced illness",
            "Gestational diabetes only",
            "Steroid-induced diabetes only",
        ],
        "closure_criteria": "HbA1c test result (LOINC 4548-4 or 17856-6) documented in measurement year.",
        "drug_classes": [],
        "icd_exclusion_codes": ["O24.4", "Z51.5"],
        "notes": "CPT codes: 83036, 83037. LOINC: 4548-4, 17856-6.",
        "source": "NCQA HEDIS 2024 Technical Specifications",
    },
    "BCS": {
        "full_name": "Breast Cancer Screening",
        "numerator": "Women who had a mammogram in the past 27 months.",
        "denominator": "Women 52–74 as of Dec 31 of the measurement year.",
        "pdc_threshold": None,
        "measurement_period": "27 months ending Dec 31",
        "exclusions": [
            "Bilateral mastectomy (CPT 19180+19303 or ICD-10 Z90.13)",
            "Hospice care",
            "Frailty AND advanced illness",
        ],
        "closure_criteria": "Mammography (CPT 77057, 77065, 77066, 77067) documented in period.",
        "drug_classes": [],
        "icd_exclusion_codes": ["Z90.13", "Z51.5"],
        "notes": "Age range: 52–74. Lookback: 27 months (two-year biennial screening window).",
        "source": "NCQA HEDIS 2024 Technical Specifications",
    },
    "COL": {
        "full_name": "Colorectal Cancer Screening",
        "numerator": "Members with appropriate colorectal cancer screening.",
        "denominator": "Members 46–75 as of Dec 31.",
        "pdc_threshold": None,
        "measurement_period": "Varies by test: FOBT=1yr, sigmoidoscopy=5yr, colonoscopy=10yr",
        "exclusions": [
            "Colorectal cancer diagnosis (ICD-10 C18-C20)",
            "Total colectomy",
            "Hospice care",
            "Frailty AND advanced illness",
        ],
        "closure_criteria": (
            "FOBT/FIT (within 1 year), stool DNA (within 3 years), "
            "CT colonography or flexible sigmoidoscopy (within 5 years), "
            "or colonoscopy (within 10 years)."
        ),
        "drug_classes": [],
        "icd_exclusion_codes": ["C18", "C19", "C20", "Z51.5"],
        "notes": "Age range: 46–75. Multiple test types with different lookback periods.",
        "source": "NCQA HEDIS 2024 Technical Specifications",
    },
}


class MeasureCriteriaTool:
    name = "measure_criteria"
    description = (
        "Look up HEDIS measure specification and exclusion criteria (NCQA public specs). "
        "Input: measure_id string (e.g., 'MAC', 'MAD', 'MAP', 'CBP', 'CDC-HbA1c', 'BCS', 'COL'). "
        "Returns: numerator, denominator, exclusion criteria, closure requirements."
    )

    async def __call__(self, input: str) -> ToolResult:
        try:
            measure_id = input.strip().upper().replace(" ", "-")

            # Fuzzy match common aliases
            aliases = {
                "STATIN": "MAC", "CHOLESTEROL": "MAC",
                "DIABETES-MED": "MAD", "ORAL-DIABETES": "MAD",
                "HYPERTENSION-MED": "MAP", "ACE": "MAP", "ARB": "MAP",
                "BP": "CBP", "BLOOD-PRESSURE": "CBP",
                "HBAIC": "CDC-HbA1c", "A1C": "CDC-HbA1c", "HEMOGLOBIN": "CDC-HbA1c",
                "MAMMOGRAM": "BCS", "BREAST": "BCS",
                "COLONOSCOPY": "COL", "COLORECTAL": "COL",
            }
            measure_id = aliases.get(measure_id, measure_id)

            spec = _MEASURE_SPECS.get(measure_id)
            if not spec:
                available = ", ".join(_MEASURE_SPECS.keys())
                return ToolResult(
                    content=f"Measure '{measure_id}' not found. Available: {available}",
                    metadata={"measure_id": measure_id, "found": False},
                )

            lines = [
                f"HEDIS Measure: {measure_id} — {spec['full_name']}",
                f"Source: {spec['source']}",
                "",
                f"Denominator: {spec['denominator']}",
                f"Numerator: {spec['numerator']}",
                f"Measurement period: {spec['measurement_period']}",
            ]

            if spec.get("pdc_threshold"):
                lines.append(f"PDC threshold: {spec['pdc_threshold']:.2f} (>= required)")

            lines.append(f"\nClosure criteria: {spec['closure_criteria']}")

            if spec["exclusions"]:
                lines.append("\nExclusion criteria:")
                for exc in spec["exclusions"]:
                    lines.append(f"  - {exc}")

            if spec.get("drug_classes"):
                lines.append(f"\nRelevant drug classes: {', '.join(spec['drug_classes'])}")

            if spec.get("notes"):
                lines.append(f"\nNotes: {spec['notes']}")

            return ToolResult(
                content="\n".join(lines),
                metadata={"measure_id": measure_id, "found": True,
                          "stars_weight": self._get_weight(measure_id)},
            )
        except Exception as e:
            log.error(f"MeasureCriteriaTool failed: {e}")
            return ToolResult(content="", error=f"measure_criteria failed: {e}")

    def _get_weight(self, measure_id: str) -> float:
        from clinical.schemas import HEDIS_MEASURES
        return HEDIS_MEASURES.get(measure_id, {}).get("stars_weight", 1.0)


register_tool(MeasureCriteriaTool())
