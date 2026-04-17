"""
HEDIS measure criteria tool — returns measure specification and exclusion criteria.

Uses NCQA public HEDIS measure specs only (no MCG licensing required).
Phase 1: medication adherence measures (MAC, MAD, MAP) + key chronic disease measures.
Phase 2: full diabetes measure set (GSD, KED, EED-E, SPD-E, BPD-E) — NCQA HEDIS MY 2026.

Input: measure_id string (e.g., "GSD", "KED", "EED-E", "SPD-E", "BPD-E", "MAC", "MAD")
"""

from __future__ import annotations

from core.tool import ToolResult, register_tool
from settings import create_log

log = create_log()

# NCQA HEDIS public measure specifications
# Phase 1: MAC, MAD, MAP, CBP, CDC-HbA1c, BCS, COL  — NCQA HEDIS 2024
# Phase 2: GSD, KED, EED-E, SPD-E, BPD-E             — NCQA HEDIS MY 2026
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

    # -----------------------------------------------------------------------
    # Diabetes measure set — NCQA HEDIS MY 2026 (from SKILL.md)
    # -----------------------------------------------------------------------
    "GSD": {
        "full_name": "Glycemic Status Assessment for Patients with Diabetes",
        "numerator": (
            "Three rates reported: (1) Most recent A1c or GMI < 8.0%, "
            "(2) Most recent A1c or GMI < 7.0%, "
            "(3) Most recent A1c or GMI > 9.0% (INVERSE — poor control, triple-weighted in MA Stars)."
        ),
        "denominator": (
            "Members 18–75 with diabetes: two DX codes (E10/E11/E13) on different dates in MY or PY, "
            "OR dispensed insulin/hypoglycemics/antihyperglycemics with at least one DX code. "
            "Metformin alone counts since MY 2024."
        ),
        "pdc_threshold": None,
        "measurement_period": "Most recent A1c or GMI result during the measurement year",
        "exclusions": [
            "Hospice care during measurement year",
            "Frailty AND advanced illness",
            "Gestational diabetes only (ICD-10 O24.4)",
            "Steroid-induced diabetes only",
            "Members with bilateral adrenalectomy (affects A1c validity)",
        ],
        "closure_criteria": (
            "A numeric A1c or GMI result documented in the measurement year. "
            "Missing, unknown, or range results = poor control. "
            "GMI from CGM is measure-compliant as of MY 2026."
        ),
        "drug_classes": [],
        "icd_exclusion_codes": ["O24.4", "Z51.5"],
        "notes": (
            "PRIORITIZATION: Untested members (no A1c/GMI in MY) are the cheapest gap to close "
            "and highest Stars leverage — one standing lab order closes the gap. "
            "Therapeutic inertia bands: (a) untested → order lab, (b) A1c 8.5–9.0% trending up "
            "→ intervention, (c) A1c >9.0% with recent encounter → titration, "
            "(d) A1c >9.0% + no PCP in >180 days → re-engagement. "
            "GSD is INVERSE and triple-weighted — every uncontrolled diabetic penalizes Stars 3x."
        ),
        "source": "NCQA HEDIS MY 2026 Technical Specifications",
    },
    "KED": {
        "full_name": "Kidney Health Evaluation for Patients with Diabetes",
        "numerator": (
            "BOTH eGFR AND uACR (urine albumin-to-creatinine ratio) present in the measurement year. "
            "eGFR alone = FAIL. uACR alone = FAIL. Both required."
        ),
        "denominator": "Members 18–85 with diabetes (same denominator logic as GSD).",
        "pdc_threshold": None,
        "measurement_period": "Measurement year (Jan 1 – Dec 31)",
        "exclusions": [
            "Hospice care",
            "Frailty AND advanced illness",
            "ESRD (bilateral nephrectomy or maintenance dialysis)",
            "Kidney transplant recipients",
        ],
        "closure_criteria": (
            "eGFR (LOINC 33914-3 or 50044-7) AND uACR (LOINC 14959-1 or 32294-1) "
            "both documented in the measurement year."
        ),
        "drug_classes": [],
        "icd_exclusion_codes": ["N18.6", "Z94.0", "Z51.5"],
        "notes": (
            "Clinical action beyond compliance: uACR-positive members (>30 mg/g) should be evaluated "
            "for SGLT2i initiation — Class I evidence for renal protection: CREDENCE (canagliflozin), "
            "DAPA-CKD (dapagliflozin), EMPA-KIDNEY (empagliflozin). "
            "Most open KED gaps are eGFR-only — the fix is a standing uACR add-on to the next lab draw. "
            "Mail-in urine kits (Healthy.io, Siemens) for members without upcoming encounters."
        ),
        "source": "NCQA HEDIS MY 2026 Technical Specifications",
    },
    "EED-E": {
        "full_name": "Eye Exam for Patients with Diabetes (ECDS)",
        "numerator": (
            "Retinal or dilated eye exam by eye care professional (optometrist or ophthalmologist) "
            "in the measurement year, OR a negative retinal exam (no retinopathy) in the prior year."
        ),
        "denominator": "Members 18–75 with diabetes.",
        "pdc_threshold": None,
        "measurement_period": "Measurement year + one-year lookback for negative exams",
        "exclusions": [
            "Bilateral eye enucleation",
            "Hospice care",
            "Frailty AND advanced illness",
        ],
        "closure_criteria": (
            "Retinal exam by optometrist/ophthalmologist (CPT 92002, 92004, 92012, 92014, 92228, 92229), "
            "fundus photography with professional interpretation, or teleophthalmology read. "
            "Negative exam in the prior year satisfies the two-year window."
        ),
        "drug_classes": [],
        "icd_exclusion_codes": ["Z96.1", "Z51.5"],
        "notes": (
            "Referral leakage is the modal failure mode — member agrees to referral and never completes. "
            "Fix: in-office retinal imaging at PCP sites (Topcon NW400, IRIS) with teleophthalmology read. "
            "Supplemental data pipeline required — retinal imaging in PCP offices often billed as E/M only, "
            "missing from claims-based denominator."
        ),
        "source": "NCQA HEDIS MY 2026 Technical Specifications",
    },
    "SPD-E": {
        "full_name": "Statin Therapy for Patients with Diabetes (ECDS)",
        "numerator": (
            "Two rates: "
            "(a) Statin dispensing — at least one statin fill during the measurement year; "
            "(b) Statin adherence — PDC >= 0.80 for statins during the measurement year."
        ),
        "denominator": "Members 40–75 with diabetes and NO ASCVD diagnosis.",
        "pdc_threshold": 0.80,
        "measurement_period": "Full measurement year — ECDS-only (MY 2026, hybrid retired)",
        "exclusions": [
            "ASCVD diagnosis (falls into SPC-E instead)",
            "Hospice care",
            "Frailty AND advanced illness",
            "Myopathy or rhabdomyolysis (ICD-10 M62.82, M62.892)",
            "Liver disease with elevated LFTs",
        ],
        "closure_criteria": (
            "At least one statin dispensing event for rate (a). "
            "PDC >= 0.80 for statin medications for rate (b). "
            "90-day fills and mail-order conversion raise PDC 10–15 points."
        ),
        "drug_classes": ["statin"],
        "icd_exclusion_codes": ["I21", "I22", "I25", "Z51.5", "M62.82"],
        "notes": (
            "Clinical rationale: diabetes is a CAD risk equivalent — moderate-to-high intensity statin "
            "is guideline-concordant for nearly all diabetics 40–75 regardless of LDL "
            "(HPS trial: 25% MACE reduction; CARDS: 37% reduction in first CV event). "
            "Discontinuation: 40–50% of statin starts stop within one year. "
            "Myalgia-triage: rechallenge with different statin or every-other-day dosing before stopping."
        ),
        "source": "NCQA HEDIS MY 2026 Technical Specifications",
    },
    "BPD-E": {
        "full_name": "Blood Pressure Control for Patients with Diabetes (ECDS)",
        "numerator": "Most recent BP reading < 140/90 mmHg during the measurement year.",
        "denominator": "Members 18–85 with diabetes AND hypertension.",
        "pdc_threshold": None,
        "measurement_period": "Most recent BP reading in the measurement year",
        "exclusions": [
            "Hospice care",
            "Frailty AND advanced illness",
            "Pregnancy",
            "Acute illness readings (sepsis, shock)",
        ],
        "closure_criteria": (
            "Documented outpatient BP < 140 mmHg systolic AND < 90 mmHg diastolic. "
            "RPM/home BP readings are measure-compliant via voluntary ECDS as of MY 2026."
        ),
        "drug_classes": ["ace_inhibitor", "arb", "thiazide", "ccb", "spironolactone"],
        "icd_exclusion_codes": ["O10", "O11", "O13", "O14", "Z51.5"],
        "notes": (
            "Dominantly a data-capture problem: RPM and home BP readings often miss the HEDIS denominator "
            "under admin reporting. MY 2026 ECDS option changes this — ingest RPM feeds "
            "(Livongo/Teladoc, Omada, Withings). "
            "HEDIS threshold <140/90 is the compliance floor; ADA 2024 clinical target is <130/80. "
            "70%+ of diabetics are hypertensive — intensification to ACEi/ARB + thiazide or CCB "
            "is the standard escalation for uncontrolled BP."
        ),
        "source": "NCQA HEDIS MY 2026 Technical Specifications",
    },
}


class MeasureCriteriaTool:
    name = "measure_criteria"
    description = (
        "Look up HEDIS measure specification and exclusion criteria (NCQA public specs). "
        "Input: measure_id string. "
        "Diabetes MY 2026: GSD (glycemic status, triple-weighted inverse), KED (kidney health — "
        "eGFR+uACR both required), EED-E (eye exam), SPD-E (statin therapy), BPD-E (BP control). "
        "General: MAC (statin adherence), MAD (diabetes meds adherence), MAP (RASA), CBP, BCS, COL. "
        "Returns: numerator, denominator, exclusion criteria, closure requirements, clinical notes."
    )

    async def __call__(self, input: str) -> ToolResult:
        try:
            measure_id = input.strip().upper().replace(" ", "-")

            # Fuzzy match common aliases
            aliases = {
                # General
                "STATIN": "MAC", "CHOLESTEROL": "MAC",
                "DIABETES-MED": "MAD", "ORAL-DIABETES": "MAD",
                "HYPERTENSION-MED": "MAP", "ACE": "MAP", "ARB": "MAP",
                "BP": "CBP", "BLOOD-PRESSURE": "CBP",
                "HBAIC": "CDC-HbA1c", "A1C": "CDC-HbA1c", "HEMOGLOBIN": "CDC-HbA1c",
                "MAMMOGRAM": "BCS", "BREAST": "BCS",
                "COLONOSCOPY": "COL", "COLORECTAL": "COL",
                # Diabetes MY 2026
                "GLYCEMIC": "GSD", "GLYCEMIC-STATUS": "GSD", "A1C-CONTROL": "GSD",
                "KIDNEY": "KED", "KIDNEY-HEALTH": "KED", "EGFR": "KED", "UACR": "KED",
                "EYE": "EED-E", "RETINAL": "EED-E", "EYE-EXAM": "EED-E", "EED": "EED-E",
                "STATIN-DIABETES": "SPD-E", "SPD": "SPD-E",
                "BP-DIABETES": "BPD-E", "BPD": "BPD-E",
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
