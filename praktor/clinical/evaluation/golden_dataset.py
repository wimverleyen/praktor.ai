"""
Golden dataset: 20 clinically realistic scenarios for offline evaluation.

Sample size rationale
─────────────────────
Power analysis (one-sample t-test against quality threshold 7.0/10):
    σ = 2.0  (conservative LLM judge score variance)
    δ = 1.0  (minimum clinically meaningful difference)
    α = 0.05, power = 0.80
    n = (z_α/2 + z_β)² × σ² / δ²
      = (1.96 + 0.84)² × 4.0 / 1.0
      ≈ 31.4  →  start with 20, expand to 32 if CI too wide

20 samples (10 per agent type) gives ~72% power — adequate for a
baseline pass/fail decision.  Expand to 32 once the first eval run
reveals inter-judge reliability (Cohen's κ target ≥ 0.60).

Dataset layout
──────────────
10 HEDIS gap scenarios  (H001–H010): statin, RASA, ACE/ARB, CBP, BCS, COL
10 Diabetes scenarios   (D001–D010): GSD, KED, EED-E, SPD-E, BPD-E, stacked

Each sample provides:
  • clinical data to seed into ClinicalStore (member, gaps, claims, labs, outreach)
  • a reference output (ideal agent response written by a clinical expert)
  • expected action_type and measure_id for structured comparison
  • outcome label (closed / not_closed / pending)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoldenSample:
    sample_id: str
    agent_type: str          # "hedis_gap" | "diabetes_hedis"
    raw_member_id: str       # passed to hash_member_id()
    measurement_year: int
    clinical_scenario: str   # rich description used as judge member_context
    reference_output: str    # ideal agent response text
    expected_action: str
    expected_measures: list[str]
    outcome: str             # closed | not_closed | pending
    # Clinical data to seed
    member_data: dict = field(default_factory=dict)
    gaps: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)
    labs: list[dict] = field(default_factory=list)
    outreach: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper — shared measurement year
# ---------------------------------------------------------------------------
_HY = 2024   # HEDIS measurement year
_DY = 2026   # Diabetes measurement year


def _member(raw_id: str, lang: str = "en", literacy: str = "medium",
            sdoh: str = "low", barriers: list | None = None,
            pcp: str = "Dr. Smith", pharmacy_miles: float = 1.2,
            year: int = _HY) -> dict:
    return {
        "raw_member_id": raw_id,
        "plan_id": "MA-GOLD-2024",
        "measurement_year": year,
        "language": lang,
        "health_literacy": literacy,
        "pcp_id": f"PCP-{raw_id}",
        "pcp_name": pcp,
        "pcp_language": lang,
        "sdoh_risk": sdoh,
        "sdoh_barriers": json.dumps(barriers or []),
        "pharmacy_name": "CVS Pharmacy",
        "pharmacy_miles": pharmacy_miles,
    }


def _gap(raw_id: str, measure_id: str, measure_name: str, stars: float,
         days_left: int, pdc: float | None = None, last_svc: str | None = None,
         year: int = _HY) -> dict:
    return {
        "raw_member_id": raw_id,
        "measure_id": measure_id,
        "measure_name": measure_name,
        "stars_weight": stars,
        "measurement_year": year,
        "days_remaining": days_left,
        "last_service_date": last_svc,
        "pdc_current": pdc,
        "pdc_threshold": 0.80,
        "status": "open",
    }


def _claim(raw_id: str, date: str, drug: str, drug_class: str,
           ndc: str, days_supply: int = 30) -> dict:
    return {
        "raw_member_id": raw_id,
        "service_date": date,
        "icd_codes": "[]",
        "cpt_codes": "[]",
        "ndc_code": ndc,
        "drug_name": drug,
        "drug_class": drug_class,
        "days_supply": days_supply,
        "quantity": days_supply,
        "provider_id": "PHARM-001",
        "claim_type": "rx",
    }


def _lab(raw_id: str, date: str, name: str, value: float,
         unit: str, loinc: str = "", ref: str = "") -> dict:
    return {
        "raw_member_id": raw_id,
        "test_date": date,
        "test_name": name,
        "result_value": value,
        "result_unit": unit,
        "result_text": f"{value} {unit}",
        "loinc_code": loinc,
        "reference_range": ref,
    }


def _outreach(raw_id: str, date: str, channel: str, measure: str,
              outcome: str, notes: str = "") -> dict:
    return {
        "raw_member_id": raw_id,
        "contact_date": date,
        "channel": channel,
        "measure_id": measure,
        "outcome": outcome,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# HEDIS Gap Golden Samples (H001–H010)
# ---------------------------------------------------------------------------

_HEDIS_SAMPLES: list[GoldenSample] = [

    GoldenSample(
        sample_id="H001",
        agent_type="hedis_gap",
        raw_member_id="GOLD-H001",
        measurement_year=_HY,
        clinical_scenario=(
            "English-speaking member with MAC (statin) gap. PDC=0.71, last fill 47 days ago. "
            "No prior outreach. PCP is Dr. Maria Lopez (English). Pharmacy 1.2 miles away. "
            "Medium health literacy. Low SDOH risk."
        ),
        reference_output=(
            "ACTION_TYPE: pcp_warm_outreach\n"
            "PRIORITY_SCORE: 8.5\n"
            "MEASURE: MAC\n"
            "CLOSURE_PROBABILITY: 0.72\n"
            "RATIONALE: Member's statin PDC is 0.71, below the 0.80 threshold. Last fill was 47 days ago, "
            "indicating a current gap. No prior outreach attempts — PCP warm contact is the highest-yield "
            "first step given the established relationship with Dr. Lopez.\n"
            "DRAFT_MESSAGE: Hi, this is the care team from your health plan. We noticed your statin "
            "prescription may need a refill. Your doctor Dr. Lopez wanted us to reach out to help keep "
            "your heart health on track. Can we help schedule a refill or connect you with your pharmacy?\n"
            "LANGUAGE: en"
        ),
        expected_action="pcp_warm_outreach",
        expected_measures=["MAC"],
        outcome="closed",
        member_data=_member("GOLD-H001", lang="en", literacy="medium"),
        gaps=[_gap("GOLD-H001", "MAC", "Medication Adherence for Cholesterol (Statins)", 3.0, 90, pdc=0.71, last_svc="2024-02-10")],
        claims=[
            _claim("GOLD-H001", "2024-01-25", "Atorvastatin 40mg", "statin", "0071014210", 30),
            _claim("GOLD-H001", "2024-02-10", "Atorvastatin 40mg", "statin", "0071014210", 30),
        ],
        outreach=[],
    ),

    GoldenSample(
        sample_id="H002",
        agent_type="hedis_gap",
        raw_member_id="GOLD-H002",
        measurement_year=_HY,
        clinical_scenario=(
            "Spanish-speaking member with MAC (statin) gap. PDC=0.65, last fill 62 days ago. "
            "Phone outreach 30 days ago — refused. Low health literacy. PCP speaks English only. "
            "Pharmacy 0.8 miles away. Medium SDOH risk."
        ),
        reference_output=(
            "ACTION_TYPE: pharmacy_refill_reminder\n"
            "PRIORITY_SCORE: 9.0\n"
            "MEASURE: MAC\n"
            "CLOSURE_PROBABILITY: 0.68\n"
            "RATIONALE: PDC=0.65 is critically below threshold. Phone channel refused — switch to pharmacy "
            "SMS in Spanish. Pharmacy is 0.8 miles away (accessible). Low literacy favors short SMS over portal. "
            "Language-concordant messaging critical: member refused English phone call.\n"
            "DRAFT_MESSAGE: Hola, su farmacia CVS quiere recordarle que su medicamento para el colesterol "
            "necesita recarga. Llame al (555) 123-4567 o pase a recogerlo. ¡Su salud es importante!\n"
            "LANGUAGE: es"
        ),
        expected_action="pharmacy_refill_reminder",
        expected_measures=["MAC"],
        outcome="closed",
        member_data=_member("GOLD-H002", lang="es", literacy="low", sdoh="medium",
                            barriers=["language_barrier"]),
        gaps=[_gap("GOLD-H002", "MAC", "Medication Adherence for Cholesterol (Statins)", 3.0, 75, pdc=0.65, last_svc="2024-01-28")],
        claims=[
            _claim("GOLD-H002", "2023-12-30", "Rosuvastatin 20mg", "statin", "0310372230", 30),
            _claim("GOLD-H002", "2024-01-28", "Rosuvastatin 20mg", "statin", "0310372230", 30),
        ],
        outreach=[_outreach("GOLD-H002", "2024-03-01", "phone", "MAC", "refused", "Member said not interested")],
    ),

    GoldenSample(
        sample_id="H003",
        agent_type="hedis_gap",
        raw_member_id="GOLD-H003",
        measurement_year=_HY,
        clinical_scenario=(
            "English-speaking member with MAD (RASA) gap. PDC=0.74. Portal message sent 45 days ago — "
            "no response. High health literacy. PCP is Dr. James Chen (English). 2.1 miles to pharmacy."
        ),
        reference_output=(
            "ACTION_TYPE: member_direct_outreach\n"
            "PRIORITY_SCORE: 7.5\n"
            "MEASURE: MAD\n"
            "CLOSURE_PROBABILITY: 0.65\n"
            "RATIONALE: PDC=0.74 for RASA, 6 points below threshold. Prior portal message went unanswered "
            "after 45 days — escalate to direct phone call. High health literacy supports detailed explanation. "
            "Pharmacy is 2.1 miles — slightly less convenient, emphasize home delivery option.\n"
            "DRAFT_MESSAGE: Hello, this is your health plan care team calling about your asthma controller "
            "medication. Your records show a possible gap in your RASA prescription. We can help arrange "
            "home delivery at no extra cost. Please call us back at (800) 555-0100.\n"
            "LANGUAGE: en"
        ),
        expected_action="member_direct_outreach",
        expected_measures=["MAD"],
        outcome="not_closed",
        member_data=_member("GOLD-H003", lang="en", literacy="high", pharmacy_miles=2.1),
        gaps=[_gap("GOLD-H003", "MAD", "Medication Adherence for Asthma (RASA)", 3.0, 110, pdc=0.74, last_svc="2024-02-01")],
        claims=[
            _claim("GOLD-H003", "2024-01-05", "Fluticasone/Salmeterol 250/50", "rasa", "0173045955", 30),
            _claim("GOLD-H003", "2024-02-01", "Fluticasone/Salmeterol 250/50", "rasa", "0173045955", 30),
        ],
        outreach=[_outreach("GOLD-H003", "2024-02-15", "portal", "MAD", "no_answer", "Sent portal message, no response")],
    ),

    GoldenSample(
        sample_id="H004",
        agent_type="hedis_gap",
        raw_member_id="GOLD-H004",
        measurement_year=_HY,
        clinical_scenario=(
            "English-speaking member with MAP (ACE/ARB) gap. PDC=0.67. Urgent: 42 days remaining "
            "in measurement year. No prior outreach. Medium literacy. Pharmacy 1.0 mile away."
        ),
        reference_output=(
            "ACTION_TYPE: pharmacy_refill_reminder\n"
            "PRIORITY_SCORE: 9.5\n"
            "MEASURE: MAP\n"
            "CLOSURE_PROBABILITY: 0.80\n"
            "RATIONALE: MAP carries 3.0x Stars weight. PDC=0.67, needs immediate action with only 42 days "
            "left. Pharmacy is 1 mile away and accessible. Direct pharmacy refill reminder is fastest path "
            "to closure — no appointment scheduling needed. Time-critical.\n"
            "DRAFT_MESSAGE: Urgent reminder from your health plan: your blood pressure medication (ACE inhibitor) "
            "needs a refill to stay on track for the year. Your pharmacy is nearby at 1.0 mile. Please refill "
            "today — call (555) 200-3000 or we can have it delivered.\n"
            "LANGUAGE: en"
        ),
        expected_action="pharmacy_refill_reminder",
        expected_measures=["MAP"],
        outcome="closed",
        member_data=_member("GOLD-H004", lang="en", literacy="medium", pharmacy_miles=1.0),
        gaps=[_gap("GOLD-H004", "MAP", "Medication Adherence for Hypertension (ACE/ARB)", 3.0, 42, pdc=0.67, last_svc="2024-01-15")],
        claims=[
            _claim("GOLD-H004", "2023-12-15", "Lisinopril 10mg", "ace_inhibitor", "0093305356", 30),
            _claim("GOLD-H004", "2024-01-15", "Lisinopril 10mg", "ace_inhibitor", "0093305356", 30),
        ],
        outreach=[],
    ),

    GoldenSample(
        sample_id="H005",
        agent_type="hedis_gap",
        raw_member_id="GOLD-H005",
        measurement_year=_HY,
        clinical_scenario=(
            "English-speaking member with CBP (controlled blood pressure) gap. "
            "Last BP reading 145/92 mmHg (3 months ago at PCP visit). No medication gap. "
            "PCP is Dr. Sarah Williams (English). Medium literacy. No prior outreach."
        ),
        reference_output=(
            "ACTION_TYPE: scheduling_assist\n"
            "PRIORITY_SCORE: 8.0\n"
            "MEASURE: CBP\n"
            "CLOSURE_PROBABILITY: 0.75\n"
            "RATIONALE: CBP gap requires a BP reading ≤140/90 on record this year. Last reading was 145/92 "
            "(3 months ago) — above threshold. Medication adherence is not the issue. Member needs a PCP "
            "follow-up visit to have BP rechecked after any treatment adjustments.\n"
            "DRAFT_MESSAGE: Hello! Your health plan noticed your last blood pressure reading was slightly "
            "elevated. Dr. Williams would like to recheck it — this can often be done in a quick 15-minute visit. "
            "Can we help schedule an appointment? Call (555) 300-4000 or visit our portal.\n"
            "LANGUAGE: en"
        ),
        expected_action="scheduling_assist",
        expected_measures=["CBP"],
        outcome="closed",
        member_data=_member("GOLD-H005", lang="en", literacy="medium", pcp="Dr. Sarah Williams"),
        gaps=[_gap("GOLD-H005", "CBP", "Controlling High Blood Pressure", 2.0, 150, last_svc="2024-01-10")],
        labs=[_lab("GOLD-H005", "2024-01-10", "Systolic Blood Pressure", 145, "mmHg", "55284-4", "<140")],
        outreach=[],
    ),

    GoldenSample(
        sample_id="H006",
        agent_type="hedis_gap",
        raw_member_id="GOLD-H006",
        measurement_year=_HY,
        clinical_scenario=(
            "English-speaking female member, 54 years old, with BCS (breast cancer screening) gap. "
            "No mammogram in 2 years. 120 days remaining in measurement year. High health literacy. "
            "PCP is Dr. Patricia Green (English). No prior outreach."
        ),
        reference_output=(
            "ACTION_TYPE: scheduling_assist\n"
            "PRIORITY_SCORE: 7.5\n"
            "MEASURE: BCS\n"
            "CLOSURE_PROBABILITY: 0.82\n"
            "RATIONALE: Member is overdue for biennial mammogram (last done >2 years ago). No exclusion "
            "criteria noted. High health literacy supports self-scheduling via portal. 120-day window provides "
            "adequate time for scheduling assist.\n"
            "DRAFT_MESSAGE: Hello! Your health care team wants to remind you that you're due for your "
            "routine mammogram screening. Staying up to date with breast cancer screening is an important "
            "part of your care. Would you like help scheduling? Call (555) 400-5000 or book online at "
            "our member portal.\n"
            "LANGUAGE: en"
        ),
        expected_action="scheduling_assist",
        expected_measures=["BCS"],
        outcome="closed",
        member_data=_member("GOLD-H006", lang="en", literacy="high", pcp="Dr. Patricia Green"),
        gaps=[_gap("GOLD-H006", "BCS", "Breast Cancer Screening", 1.0, 120, last_svc="2022-03-15")],
        outreach=[],
    ),

    GoldenSample(
        sample_id="H007",
        agent_type="hedis_gap",
        raw_member_id="GOLD-H007",
        measurement_year=_HY,
        clinical_scenario=(
            "Member with COL (colorectal cancer screening) gap. ICD codes include Z85.038 "
            "(personal history of colon polyp). Colonoscopy due. 200 days remaining. "
            "English-speaking. Medium literacy. PCP is Dr. Thomas Brown."
        ),
        reference_output=(
            "ACTION_TYPE: scheduling_assist\n"
            "PRIORITY_SCORE: 8.0\n"
            "MEASURE: COL\n"
            "CLOSURE_PROBABILITY: 0.70\n"
            "RATIONALE: COL gap — member has history of colon polyp (Z85.038), increasing priority for "
            "colonoscopy (not just FIT/FOBT). Personal history does not exclude — it increases urgency. "
            "Scheduling assist for gastroenterology referral is appropriate. Safety note: prior polyp "
            "history was checked and does not trigger exclusion.\n"
            "DRAFT_MESSAGE: Hello! Your health team sees you're due for your colorectal cancer screening. "
            "Given your medical history, a colonoscopy is recommended. We can help refer you to a "
            "gastroenterologist at no additional cost. Please call (555) 500-6000 to schedule.\n"
            "LANGUAGE: en"
        ),
        expected_action="scheduling_assist",
        expected_measures=["COL"],
        outcome="pending",
        member_data=_member("GOLD-H007", lang="en", literacy="medium", pcp="Dr. Thomas Brown"),
        gaps=[_gap("GOLD-H007", "COL", "Colorectal Cancer Screening", 1.0, 200, last_svc="2018-06-01")],
        claims=[
            {"raw_member_id": "GOLD-H007", "service_date": "2020-06-01",
             "icd_codes": '["Z85.038"]', "cpt_codes": '["45378"]',
             "ndc_code": None, "drug_name": None, "drug_class": None,
             "days_supply": 0, "quantity": 0, "provider_id": "GI-001", "claim_type": "medical"},
        ],
        outreach=[],
    ),

    GoldenSample(
        sample_id="H008",
        agent_type="hedis_gap",
        raw_member_id="GOLD-H008",
        measurement_year=_HY,
        clinical_scenario=(
            "Member with two open gaps: MAC (statin, PDC=0.69) and CBP (last BP 148/94). "
            "English. Medium literacy. 95 days remaining. PCP is Dr. Linda Martinez. No prior outreach."
        ),
        reference_output=(
            "ACTION_TYPE: pcp_warm_outreach\n"
            "PRIORITY_SCORE: 9.0\n"
            "MEASURE: MAC\n"
            "CLOSURE_PROBABILITY: 0.74\n"
            "RATIONALE: Two gaps open — MAC (3.0x Stars, PDC=0.69) and CBP (2.0x). MAC prioritized by Stars "
            "weight. PCP warm outreach addresses both: refill reminder AND BP recheck can be bundled into "
            "one PCP call. Dr. Martinez can coordinate both actions in one patient touchpoint.\n"
            "DRAFT_MESSAGE: Hi, this is your health plan care team. Dr. Martinez asked us to reach out — "
            "we noticed your cholesterol medication may need a refill, and it would also be a great time "
            "to have your blood pressure rechecked. Can we help schedule a visit or a refill? Call us "
            "at (800) 555-0200.\n"
            "LANGUAGE: en"
        ),
        expected_action="pcp_warm_outreach",
        expected_measures=["MAC", "CBP"],
        outcome="closed",
        member_data=_member("GOLD-H008", lang="en", literacy="medium", pcp="Dr. Linda Martinez"),
        gaps=[
            _gap("GOLD-H008", "MAC", "Medication Adherence for Cholesterol (Statins)", 3.0, 95, pdc=0.69, last_svc="2024-01-20"),
            _gap("GOLD-H008", "CBP", "Controlling High Blood Pressure", 2.0, 95, last_svc="2024-01-20"),
        ],
        claims=[
            _claim("GOLD-H008", "2024-01-20", "Atorvastatin 20mg", "statin", "0071014120", 30),
        ],
        labs=[_lab("GOLD-H008", "2024-01-20", "Systolic Blood Pressure", 148, "mmHg", "55284-4", "<140")],
        outreach=[],
    ),

    GoldenSample(
        sample_id="H009",
        agent_type="hedis_gap",
        raw_member_id="GOLD-H009",
        measurement_year=_HY,
        clinical_scenario=(
            "Member with MAD (RASA) gap. ICD codes include J44.1 (COPD with exacerbation) and "
            "recent hospitalization within 30 days. Exclusion criteria for MAD applies: "
            "acute respiratory illness exclusion. Member recently discharged."
        ),
        reference_output=(
            "ACTION_TYPE: exclusion_flag\n"
            "PRIORITY_SCORE: 2.0\n"
            "MEASURE: MAD\n"
            "CLOSURE_PROBABILITY: 0.0\n"
            "RATIONALE: Member meets MAD exclusion criteria: hospitalization for COPD exacerbation (J44.1) "
            "within the measurement period. Per NCQA specifications, members with acute respiratory conditions "
            "requiring hospitalization are excluded from MAD measurement. Flagging for exclusion processing — "
            "no outreach action needed. Exclusion will improve plan Stars rate.\n"
            "DRAFT_MESSAGE: N/A — exclusion flag processing. No member contact required.\n"
            "LANGUAGE: en"
        ),
        expected_action="exclusion_flag",
        expected_measures=["MAD"],
        outcome="not_closed",
        member_data=_member("GOLD-H009", lang="en", literacy="medium"),
        gaps=[_gap("GOLD-H009", "MAD", "Medication Adherence for Asthma (RASA)", 3.0, 130, pdc=0.71, last_svc="2024-01-05")],
        claims=[
            {"raw_member_id": "GOLD-H009", "service_date": "2024-03-01",
             "icd_codes": '["J44.1"]', "cpt_codes": '["99223"]',
             "ndc_code": None, "drug_name": None, "drug_class": None,
             "days_supply": 0, "quantity": 0, "provider_id": "HOSP-001", "claim_type": "medical"},
        ],
        outreach=[],
    ),

    GoldenSample(
        sample_id="H010",
        agent_type="hedis_gap",
        raw_member_id="GOLD-H010",
        measurement_year=_HY,
        clinical_scenario=(
            "Member with MAP (ACE/ARB) gap. PDC=0.61. Phone refused 3 times (2024-01-10, 2024-02-05, "
            "2024-03-01). Letter refused once (2024-03-20). Multiple failed outreach attempts. "
            "Member is non-compliant. 60 days remaining."
        ),
        reference_output=(
            "ACTION_TYPE: escalate\n"
            "PRIORITY_SCORE: 7.0\n"
            "MEASURE: MAP\n"
            "CLOSURE_PROBABILITY: 0.25\n"
            "RATIONALE: Member has refused 4 outreach contacts (3 phone, 1 letter) for MAP (3.0x Stars). "
            "Standard outreach channels are exhausted. Escalating to care manager for a complex case "
            "review — may require home visit or social worker intervention to understand barriers. "
            "Closure probability is low given pattern of non-engagement.\n"
            "DRAFT_MESSAGE: [Care Manager Referral] Member has refused 4 contacts re: MAP gap. "
            "PDC=0.61. 60 days remaining. Recommend care manager review for high-risk non-adherence "
            "intervention. Consider home visit or community health worker engagement.\n"
            "LANGUAGE: en"
        ),
        expected_action="escalate",
        expected_measures=["MAP"],
        outcome="not_closed",
        member_data=_member("GOLD-H010", lang="en", literacy="low", sdoh="high",
                            barriers=["transportation", "cost_concern"]),
        gaps=[_gap("GOLD-H010", "MAP", "Medication Adherence for Hypertension (ACE/ARB)", 3.0, 60, pdc=0.61, last_svc="2023-12-01")],
        outreach=[
            _outreach("GOLD-H010", "2024-01-10", "phone", "MAP", "refused", "Member hung up"),
            _outreach("GOLD-H010", "2024-02-05", "phone", "MAP", "refused", "Member refused, said not interested"),
            _outreach("GOLD-H010", "2024-03-01", "phone", "MAP", "refused", "Hostile — asked not to call"),
            _outreach("GOLD-H010", "2024-03-20", "letter", "MAP", "refused", "Letter returned with 'refused' written on it"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Diabetes HEDIS Golden Samples (D001–D010)
# ---------------------------------------------------------------------------

_DIABETES_SAMPLES: list[GoldenSample] = [

    GoldenSample(
        sample_id="D001",
        agent_type="diabetes_hedis",
        raw_member_id="GOLD-D001",
        measurement_year=_DY,
        clinical_scenario=(
            "Diabetes member with GSD (glycemic status) gap. HbA1c=8.9% (test 14 months ago — out of "
            "annual window). No inertia detected (first gap year). English. Medium literacy. "
            "PCP is Dr. Robert Kim."
        ),
        reference_output=(
            "ACTION_TYPE: scheduling_assist\n"
            "PRIORITY_SCORE: 9.0\n"
            "MEASURES_ADDRESSED: GSD\n"
            "GAPS_STACKED: 1\n"
            "CLOSURE_PROBABILITY: 0.88\n"
            "INERTIA_DETECTED: no\n"
            "ESCALATION_LADDER_STEP: N/A\n"
            "RATIONALE: GSD requires HbA1c test within the measurement year. Last test was 14 months ago "
            "(outside the 12-month window). HbA1c=8.9% — above control threshold. No prior outreach or "
            "inertia pattern. Scheduling a lab visit is the fastest closure path.\n"
            "DRAFT_MESSAGE: Hello! Your care team wants to make sure your diabetes is well-managed. "
            "Your annual HbA1c blood test is overdue. This simple lab test helps Dr. Kim adjust your "
            "treatment if needed. Can we help schedule a lab visit? Call (555) 600-7000.\n"
            "LANGUAGE: en"
        ),
        expected_action="scheduling_assist",
        expected_measures=["GSD"],
        outcome="closed",
        member_data=_member("GOLD-D001", lang="en", literacy="medium", pcp="Dr. Robert Kim", year=_DY),
        gaps=[_gap("GOLD-D001", "GSD", "Glycemic Status Assessment for Patients with Diabetes", 3.0, 180, year=_DY)],
        labs=[_lab("GOLD-D001", "2025-01-15", "Hemoglobin A1c", 8.9, "%", "4548-4", "<7.0")],
        outreach=[],
    ),

    GoldenSample(
        sample_id="D002",
        agent_type="diabetes_hedis",
        raw_member_id="GOLD-D002",
        measurement_year=_DY,
        clinical_scenario=(
            "Diabetes member with KED (kidney health evaluation) gap. eGFR was done (62 mL/min, normal) "
            "but uACR test never ordered this year. BOTH eGFR and uACR required for KED closure. "
            "English. High literacy. PCP is Dr. Jennifer Walsh."
        ),
        reference_output=(
            "ACTION_TYPE: member_direct_outreach\n"
            "PRIORITY_SCORE: 7.5\n"
            "MEASURES_ADDRESSED: KED\n"
            "GAPS_STACKED: 1\n"
            "CLOSURE_PROBABILITY: 0.85\n"
            "INERTIA_DETECTED: no\n"
            "ESCALATION_LADDER_STEP: N/A\n"
            "RATIONALE: KED requires both eGFR AND uACR in the measurement year. eGFR=62 (done). "
            "uACR is missing — one additional urine test closes the gap. High literacy member can "
            "self-schedule via portal or call. Direct outreach to explain the specific missing test "
            "is efficient.\n"
            "DRAFT_MESSAGE: Hello! Your health plan noticed that your kidney health check is almost "
            "complete for this year — your eGFR blood test is done, but we still need a urine test "
            "(called uACR) to close your annual kidney health gap. This is a simple urine sample. "
            "Can we help schedule it? Call (555) 700-8000 or book online.\n"
            "LANGUAGE: en"
        ),
        expected_action="member_direct_outreach",
        expected_measures=["KED"],
        outcome="closed",
        member_data=_member("GOLD-D002", lang="en", literacy="high", pcp="Dr. Jennifer Walsh", year=_DY),
        gaps=[_gap("GOLD-D002", "KED", "Kidney Health Evaluation for Patients with Diabetes", 1.0, 200, year=_DY)],
        labs=[
            _lab("GOLD-D002", "2026-01-20", "eGFR", 62, "mL/min/1.73m2", "33914-3", ">60"),
        ],
        outreach=[],
    ),

    GoldenSample(
        sample_id="D003",
        agent_type="diabetes_hedis",
        raw_member_id="GOLD-D003",
        measurement_year=_DY,
        clinical_scenario=(
            "Diabetes member with two gaps: GSD (HbA1c=9.2%, no test this year) and EED-E (no eye exam "
            "in 2 years). 2 gaps stacked. English. Medium literacy. PCP is Dr. Michael Chen."
        ),
        reference_output=(
            "ACTION_TYPE: scheduling_assist\n"
            "PRIORITY_SCORE: 8.5\n"
            "MEASURES_ADDRESSED: GSD, EED-E\n"
            "GAPS_STACKED: 2\n"
            "CLOSURE_PROBABILITY: 0.78\n"
            "INERTIA_DETECTED: no\n"
            "ESCALATION_LADDER_STEP: N/A\n"
            "RATIONALE: Two diabetes gaps identified — GSD (3.0x Stars) and EED-E. HbA1c=9.2% is poorly "
            "controlled; eye exam also overdue (2+ years). Both require referrals: lab order for HbA1c "
            "AND ophthalmology for retinal exam. Bundle scheduling into one PCP visit to improve compliance.\n"
            "DRAFT_MESSAGE: Hello! We noticed two important diabetes-related tests are due this year — "
            "your HbA1c blood test and your annual diabetic eye exam. Dr. Chen can order both in one "
            "visit. Can we help schedule that appointment? Call (555) 800-9000.\n"
            "LANGUAGE: en"
        ),
        expected_action="scheduling_assist",
        expected_measures=["GSD", "EED-E"],
        outcome="closed",
        member_data=_member("GOLD-D003", lang="en", literacy="medium", pcp="Dr. Michael Chen", year=_DY),
        gaps=[
            _gap("GOLD-D003", "GSD", "Glycemic Status Assessment for Patients with Diabetes", 3.0, 160, year=_DY),
            _gap("GOLD-D003", "EED-E", "Eye Exam for Patients with Diabetes", 1.0, 160, last_svc="2023-11-01", year=_DY),
        ],
        labs=[_lab("GOLD-D003", "2025-02-10", "Hemoglobin A1c", 9.2, "%", "4548-4", "<7.0")],
        outreach=[],
    ),

    GoldenSample(
        sample_id="D004",
        agent_type="diabetes_hedis",
        raw_member_id="GOLD-D004",
        measurement_year=_DY,
        clinical_scenario=(
            "Diabetes member with SPD-E (statin therapy) gap. Member IS prescribed statin (Atorvastatin) "
            "but PDC=0.71 (below 0.80 threshold). Two missed fills detected — inertia. English. "
            "Medium literacy. Pharmacy 1.5 miles."
        ),
        reference_output=(
            "ACTION_TYPE: pharmacy_refill_reminder\n"
            "PRIORITY_SCORE: 8.0\n"
            "MEASURES_ADDRESSED: SPD-E\n"
            "GAPS_STACKED: 1\n"
            "CLOSURE_PROBABILITY: 0.76\n"
            "INERTIA_DETECTED: yes\n"
            "ESCALATION_LADDER_STEP: 1\n"
            "RATIONALE: SPD-E gap — statin is prescribed but PDC=0.71. Two consecutive missed fills "
            "indicate treatment inertia (Escalation Step 1). Pharmacy reminder is the right first escalation "
            "action — remind member of refill, offer auto-refill enrollment to prevent future gaps.\n"
            "DRAFT_MESSAGE: Hi! Your health plan noticed your statin prescription hasn't been refilled "
            "recently. Staying consistent with this medication is important for your diabetes care. "
            "Your pharmacy can set up automatic refills — would you like us to arrange that? "
            "Call (555) 900-0100.\n"
            "LANGUAGE: en"
        ),
        expected_action="pharmacy_refill_reminder",
        expected_measures=["SPD-E"],
        outcome="closed",
        member_data=_member("GOLD-D004", lang="en", literacy="medium", pharmacy_miles=1.5, year=_DY),
        gaps=[_gap("GOLD-D004", "SPD-E", "Statin Therapy for Patients with Diabetes", 1.0, 140, pdc=0.71, last_svc="2026-01-10", year=_DY)],
        claims=[
            _claim("GOLD-D004", "2025-12-01", "Atorvastatin 40mg", "statin", "0071014210", 30),
            _claim("GOLD-D004", "2026-01-10", "Atorvastatin 40mg", "statin", "0071014210", 30),
        ],
        outreach=[],
    ),

    GoldenSample(
        sample_id="D005",
        agent_type="diabetes_hedis",
        raw_member_id="GOLD-D005",
        measurement_year=_DY,
        clinical_scenario=(
            "Diabetes member with BPD-E gap. BP=148/94 at last reading (2 months ago). "
            "No medication gap — on Amlodipine and Lisinopril. No inertia (first time at this level). "
            "English. Medium literacy. PCP is Dr. Anna Park."
        ),
        reference_output=(
            "ACTION_TYPE: pcp_warm_outreach\n"
            "PRIORITY_SCORE: 8.0\n"
            "MEASURES_ADDRESSED: BPD-E\n"
            "GAPS_STACKED: 1\n"
            "CLOSURE_PROBABILITY: 0.72\n"
            "INERTIA_DETECTED: no\n"
            "ESCALATION_LADDER_STEP: N/A\n"
            "RATIONALE: BPD-E requires BP ≤140/90. Last reading 148/94 (above threshold). Medications are "
            "filled (no PDC gap) — the issue is treatment effectiveness, not adherence. PCP warm outreach "
            "to schedule a BP recheck and possible medication adjustment is the appropriate action.\n"
            "DRAFT_MESSAGE: Hello! Dr. Park's care team is following up on your blood pressure. "
            "Your last reading was a little high, and we'd like to recheck it and see if any "
            "adjustments would help. Can we schedule a short visit? Call (555) 100-2000.\n"
            "LANGUAGE: en"
        ),
        expected_action="pcp_warm_outreach",
        expected_measures=["BPD-E"],
        outcome="closed",
        member_data=_member("GOLD-D005", lang="en", literacy="medium", pcp="Dr. Anna Park", year=_DY),
        gaps=[_gap("GOLD-D005", "BPD-E", "Blood Pressure Control for Patients with Diabetes", 1.0, 170, last_svc="2026-01-15", year=_DY)],
        labs=[_lab("GOLD-D005", "2026-01-15", "Systolic Blood Pressure", 148, "mmHg", "55284-4", "<140")],
        claims=[
            _claim("GOLD-D005", "2026-01-05", "Amlodipine 5mg", "calcium_channel_blocker", "0093101556", 30),
            _claim("GOLD-D005", "2026-01-05", "Lisinopril 10mg", "ace_inhibitor", "0093305356", 30),
        ],
        outreach=[],
    ),

    GoldenSample(
        sample_id="D006",
        agent_type="diabetes_hedis",
        raw_member_id="GOLD-D006",
        measurement_year=_DY,
        clinical_scenario=(
            "Diabetes member with 2 gaps stacked: GSD (HbA1c=8.4%, no test this year) AND KED "
            "(eGFR done at 58 mL/min but uACR missing). English. High literacy. No inertia. "
            "PCP is Dr. David Nguyen."
        ),
        reference_output=(
            "ACTION_TYPE: scheduling_assist\n"
            "PRIORITY_SCORE: 9.0\n"
            "MEASURES_ADDRESSED: GSD, KED\n"
            "GAPS_STACKED: 2\n"
            "CLOSURE_PROBABILITY: 0.83\n"
            "INERTIA_DETECTED: no\n"
            "ESCALATION_LADDER_STEP: N/A\n"
            "RATIONALE: Two gaps: GSD (3.0x Stars, needs HbA1c) and KED (needs uACR — eGFR=58 done). "
            "Both can be closed in a single lab visit: HbA1c (blood) + uACR (urine). High-yield combined "
            "lab order. Dr. Nguyen can order both. No inertia — first contact.\n"
            "DRAFT_MESSAGE: Hello! Your diabetes health check-up has two items due: an HbA1c blood test "
            "and a kidney urine test (uACR). Good news — both can be done in one lab visit! Can we help "
            "schedule that? Call (555) 200-3000 or book online.\n"
            "LANGUAGE: en"
        ),
        expected_action="scheduling_assist",
        expected_measures=["GSD", "KED"],
        outcome="closed",
        member_data=_member("GOLD-D006", lang="en", literacy="high", pcp="Dr. David Nguyen", year=_DY),
        gaps=[
            _gap("GOLD-D006", "GSD", "Glycemic Status Assessment for Patients with Diabetes", 3.0, 165, year=_DY),
            _gap("GOLD-D006", "KED", "Kidney Health Evaluation for Patients with Diabetes", 1.0, 165, year=_DY),
        ],
        labs=[
            _lab("GOLD-D006", "2025-12-15", "Hemoglobin A1c", 8.4, "%", "4548-4", "<7.0"),
            _lab("GOLD-D006", "2026-01-10", "eGFR", 58, "mL/min/1.73m2", "33914-3", ">60"),
        ],
        outreach=[],
    ),

    GoldenSample(
        sample_id="D007",
        agent_type="diabetes_hedis",
        raw_member_id="GOLD-D007",
        measurement_year=_DY,
        clinical_scenario=(
            "Diabetes member with GSD (HbA1c=9.2%) and SPD-E (PDC=0.64, statin). Inertia detected: "
            "portal outreach 60 days ago (no response), phone 30 days ago (no answer). "
            "Escalation step 2. English. Medium literacy."
        ),
        reference_output=(
            "ACTION_TYPE: pcp_warm_outreach\n"
            "PRIORITY_SCORE: 9.5\n"
            "MEASURES_ADDRESSED: GSD, SPD-E\n"
            "GAPS_STACKED: 2\n"
            "CLOSURE_PROBABILITY: 0.58\n"
            "INERTIA_DETECTED: yes\n"
            "ESCALATION_LADDER_STEP: 2\n"
            "RATIONALE: Inertia detected — 2 failed outreach attempts (portal + phone). HbA1c=9.2% (poorly "
            "controlled) and statin PDC=0.64. Escalation Step 2: PCP warm outreach. The PCP relationship "
            "is the strongest lever when member doesn't respond to plan contacts.\n"
            "DRAFT_MESSAGE: [PCP Office Action Requested] Member has 2 open diabetes quality gaps: "
            "HbA1c overdue (last=9.2%) and statin adherence (PDC=0.64). Two prior plan contacts unanswered. "
            "Please reach out at next PCP visit or proactively call member re: lab and statin refill.\n"
            "LANGUAGE: en"
        ),
        expected_action="pcp_warm_outreach",
        expected_measures=["GSD", "SPD-E"],
        outcome="not_closed",
        member_data=_member("GOLD-D007", lang="en", literacy="medium", year=_DY),
        gaps=[
            _gap("GOLD-D007", "GSD", "Glycemic Status Assessment for Patients with Diabetes", 3.0, 120, year=_DY),
            _gap("GOLD-D007", "SPD-E", "Statin Therapy for Patients with Diabetes", 1.0, 120, pdc=0.64, last_svc="2025-12-01", year=_DY),
        ],
        labs=[_lab("GOLD-D007", "2025-11-01", "Hemoglobin A1c", 9.2, "%", "4548-4", "<7.0")],
        outreach=[
            _outreach("GOLD-D007", "2026-01-05", "portal", "GSD", "no_answer", "Portal message, no response"),
            _outreach("GOLD-D007", "2026-02-05", "phone", "GSD", "no_answer", "Left voicemail, no callback"),
        ],
    ),

    GoldenSample(
        sample_id="D008",
        agent_type="diabetes_hedis",
        raw_member_id="GOLD-D008",
        measurement_year=_DY,
        clinical_scenario=(
            "Complex diabetes member with all 5 measures open: GSD, KED, EED-E, SPD-E, BPD-E. "
            "Multiple failed outreach (phone x3, letter x1). Escalation step 3. "
            "English. Low literacy. Medium SDOH risk."
        ),
        reference_output=(
            "ACTION_TYPE: escalate\n"
            "PRIORITY_SCORE: 10.0\n"
            "MEASURES_ADDRESSED: GSD, KED, EED-E, SPD-E, BPD-E\n"
            "GAPS_STACKED: 5\n"
            "CLOSURE_PROBABILITY: 0.30\n"
            "INERTIA_DETECTED: yes\n"
            "ESCALATION_LADDER_STEP: 3\n"
            "RATIONALE: All 5 MY2026 diabetes measures open. 4 failed outreach attempts (3 phone, 1 letter). "
            "Escalation Step 3: Complex Case Manager referral. Standard plan outreach exhausted. Member "
            "requires intensive care management — possible home visit, social worker, or CHW engagement. "
            "Low literacy and medium SDOH risk reinforce need for in-person support.\n"
            "DRAFT_MESSAGE: [Complex Case Manager Referral] Member has all 5 diabetes quality gaps open "
            "(GSD, KED, EED-E, SPD-E, BPD-E). 4 failed contacts. Low health literacy, medium SDOH risk. "
            "Recommend home visit or community health worker. Priority: highest.\n"
            "LANGUAGE: en"
        ),
        expected_action="escalate",
        expected_measures=["GSD", "KED", "EED-E", "SPD-E", "BPD-E"],
        outcome="not_closed",
        member_data=_member("GOLD-D008", lang="en", literacy="low", sdoh="medium",
                            barriers=["transportation", "cost_concern", "low_health_literacy"], year=_DY),
        gaps=[
            _gap("GOLD-D008", "GSD", "Glycemic Status Assessment for Patients with Diabetes", 3.0, 80, year=_DY),
            _gap("GOLD-D008", "KED", "Kidney Health Evaluation for Patients with Diabetes", 1.0, 80, year=_DY),
            _gap("GOLD-D008", "EED-E", "Eye Exam for Patients with Diabetes", 1.0, 80, last_svc="2023-06-01", year=_DY),
            _gap("GOLD-D008", "SPD-E", "Statin Therapy for Patients with Diabetes", 1.0, 80, pdc=0.58, year=_DY),
            _gap("GOLD-D008", "BPD-E", "Blood Pressure Control for Patients with Diabetes", 1.0, 80, last_svc="2025-09-01", year=_DY),
        ],
        labs=[
            _lab("GOLD-D008", "2025-08-01", "Hemoglobin A1c", 10.1, "%", "4548-4", "<7.0"),
            _lab("GOLD-D008", "2025-09-01", "Systolic Blood Pressure", 152, "mmHg", "55284-4", "<140"),
        ],
        outreach=[
            _outreach("GOLD-D008", "2026-01-10", "phone", "GSD", "refused"),
            _outreach("GOLD-D008", "2026-01-25", "phone", "GSD", "no_answer"),
            _outreach("GOLD-D008", "2026-02-15", "phone", "GSD", "refused"),
            _outreach("GOLD-D008", "2026-03-01", "letter", "GSD", "no_answer"),
        ],
    ),

    GoldenSample(
        sample_id="D009",
        agent_type="diabetes_hedis",
        raw_member_id="GOLD-D009",
        measurement_year=_DY,
        clinical_scenario=(
            "Spanish-speaking diabetes member with GSD (HbA1c=11.2%, critically uncontrolled). "
            "Phone refused twice. Inertia detected. Escalation step 2. Low health literacy. "
            "PCP speaks English only. Pharmacy 0.5 miles."
        ),
        reference_output=(
            "ACTION_TYPE: telehealth_offer\n"
            "PRIORITY_SCORE: 9.5\n"
            "MEASURES_ADDRESSED: GSD\n"
            "GAPS_STACKED: 1\n"
            "CLOSURE_PROBABILITY: 0.55\n"
            "INERTIA_DETECTED: yes\n"
            "ESCALATION_LADDER_STEP: 2\n"
            "RATIONALE: HbA1c=11.2% is critically elevated — clinical urgency is high. Phone refused twice. "
            "PCP doesn't speak Spanish, creating a language barrier. Escalation Step 2: telehealth with a "
            "Spanish-speaking endocrinologist avoids transport barrier and language mismatch. SMS in Spanish "
            "to invite telehealth visit.\n"
            "DRAFT_MESSAGE: Hola, nos preocupa su salud. Su nivel de azúcar en sangre está muy alto y "
            "necesita atención pronto. Le ofrecemos una consulta por videollamada con un médico que habla "
            "español, desde su casa, sin costo. ¿Puede responder a este mensaje o llamarnos al (555) 300-4000?\n"
            "LANGUAGE: es"
        ),
        expected_action="telehealth_offer",
        expected_measures=["GSD"],
        outcome="pending",
        member_data=_member("GOLD-D009", lang="es", literacy="low", sdoh="medium",
                            barriers=["language_barrier"], pharmacy_miles=0.5,
                            pcp="Dr. James White", year=_DY),
        gaps=[_gap("GOLD-D009", "GSD", "Glycemic Status Assessment for Patients with Diabetes", 3.0, 100, year=_DY)],
        labs=[_lab("GOLD-D009", "2025-10-01", "Hemoglobin A1c", 11.2, "%", "4548-4", "<7.0")],
        outreach=[
            _outreach("GOLD-D009", "2026-01-20", "phone", "GSD", "refused", "Member said no in Spanish"),
            _outreach("GOLD-D009", "2026-02-20", "phone", "GSD", "refused", "Hostile refusal"),
        ],
    ),

    GoldenSample(
        sample_id="D010",
        agent_type="diabetes_hedis",
        raw_member_id="GOLD-D010",
        measurement_year=_DY,
        clinical_scenario=(
            "Elderly diabetes member (estimated age 82) with GSD gap. eGFR=12 mL/min (ESRD-range). "
            "ICD codes: N18.6 (ESRD), Z99.2 (dialysis). KED and GSD exclusion criteria apply per NCQA: "
            "dialysis patients are excluded from KED; HbA1c unreliable in ESRD for GSD. "
            "English. Low literacy."
        ),
        reference_output=(
            "ACTION_TYPE: exclusion_flag\n"
            "PRIORITY_SCORE: 1.0\n"
            "MEASURES_ADDRESSED: GSD\n"
            "GAPS_STACKED: 1\n"
            "CLOSURE_PROBABILITY: 0.0\n"
            "INERTIA_DETECTED: no\n"
            "ESCALATION_LADDER_STEP: N/A\n"
            "RATIONALE: Member has ESRD (N18.6) on dialysis (Z99.2). Per NCQA MY2026 specifications: "
            "(1) KED exclusion: dialysis patients are explicitly excluded. (2) GSD exclusion: HbA1c "
            "is unreliable in ESRD/dialysis — fructosamine or alternative glycemic monitoring is used. "
            "Flagging both gaps for exclusion processing. No outreach needed — exclusions benefit plan Stars.\n"
            "DRAFT_MESSAGE: N/A — exclusion flag processing. Dialysis patient excluded from GSD and KED. "
            "No member contact required.\n"
            "LANGUAGE: en"
        ),
        expected_action="exclusion_flag",
        expected_measures=["GSD"],
        outcome="not_closed",
        member_data=_member("GOLD-D010", lang="en", literacy="low", sdoh="high",
                            barriers=["dialysis", "frailty"], year=_DY),
        gaps=[
            _gap("GOLD-D010", "GSD", "Glycemic Status Assessment for Patients with Diabetes", 3.0, 150, year=_DY),
            _gap("GOLD-D010", "KED", "Kidney Health Evaluation for Patients with Diabetes", 1.0, 150, year=_DY),
        ],
        labs=[
            _lab("GOLD-D010", "2026-01-05", "eGFR", 12.0, "mL/min/1.73m2", "33914-3", ">60"),
            _lab("GOLD-D010", "2026-01-05", "Hemoglobin A1c", 6.8, "%", "4548-4", "<7.0"),
        ],
        claims=[
            {"raw_member_id": "GOLD-D010", "service_date": "2026-01-10",
             "icd_codes": '["N18.6", "Z99.2"]', "cpt_codes": '["90935"]',
             "ndc_code": None, "drug_name": None, "drug_class": None,
             "days_supply": 0, "quantity": 0, "provider_id": "DIALYSIS-001", "claim_type": "medical"},
        ],
        outreach=[],
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_golden_samples(agent_type: str | None = None) -> list[GoldenSample]:
    """Return all golden samples, optionally filtered by agent_type."""
    all_samples = _HEDIS_SAMPLES + _DIABETES_SAMPLES
    if agent_type:
        return [s for s in all_samples if s.agent_type == agent_type]
    return all_samples


def seed_golden_members(store=None) -> None:
    """
    Seed all 20 golden member records into the ClinicalStore.

    Idempotent — uses INSERT OR REPLACE and INSERT OR IGNORE.
    Call once before running offline_eval.
    """
    from praktor.clinical.data.clinical_store import ClinicalStore
    from praktor.clinical.schemas import hash_member_id

    if store is None:
        store = ClinicalStore()

    for sample in load_golden_samples():
        member_hash = hash_member_id(sample.raw_member_id)

        # Seed member
        m = dict(sample.member_data)
        m["member_id_hash"] = member_hash
        store.upsert_member(m)

        # Seed gaps
        for g in sample.gaps:
            gd = dict(g)
            gd["member_id_hash"] = member_hash
            store.insert_gap(gd)

        # Seed claims
        for c in sample.claims:
            cd = dict(c)
            cd["member_id_hash"] = member_hash
            store.insert_claim(cd)

        # Seed labs
        for lab in sample.labs:
            ld = dict(lab)
            ld["member_id_hash"] = member_hash
            store.insert_lab(ld)

        # Seed outreach
        for o in sample.outreach:
            od = dict(o)
            od["member_id_hash"] = member_hash
            store.insert_outreach(od)
