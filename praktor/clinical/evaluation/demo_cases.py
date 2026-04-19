"""
10 synthetically generated demo cases for stakeholder demonstrations.

These are distinct from the golden dataset — they represent realistic
Medicare Advantage production traffic with more complex, multi-condition
scenarios. No reference outputs: agents produce real outputs that are
then AI-judged and available for HITL review.

Run:
    python -m praktor demo                    # seed + run all 10
    python -m praktor demo --seed-only        # seed members without running agents
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class DemoCase:
    case_id: str
    agent_type: str
    raw_member_id: str
    measurement_year: int
    description: str           # stakeholder-readable summary
    member_data: dict
    gaps: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)
    labs: list[dict] = field(default_factory=list)
    outreach: list[dict] = field(default_factory=list)


def _m(raw_id, lang="en", literacy="medium", sdoh="low",
        barriers=None, pcp="Dr. Rivera", miles=1.5, year=2024):
    return {
        "raw_member_id": raw_id, "plan_id": "MA-GOLD-DEMO",
        "measurement_year": year, "language": lang,
        "health_literacy": literacy, "pcp_id": f"PCP-{raw_id}",
        "pcp_name": pcp, "pcp_language": lang, "sdoh_risk": sdoh,
        "sdoh_barriers": json.dumps(barriers or []),
        "pharmacy_name": "Walgreens", "pharmacy_miles": miles,
    }


def _g(raw_id, mid, name, stars, days, pdc=None, last_svc=None, year=2024):
    return {
        "raw_member_id": raw_id, "measure_id": mid, "measure_name": name,
        "stars_weight": stars, "measurement_year": year,
        "days_remaining": days, "last_service_date": last_svc,
        "pdc_current": pdc, "pdc_threshold": 0.80, "status": "open",
    }


def _c(raw_id, date, drug, cls, ndc, days=30):
    return {
        "raw_member_id": raw_id, "service_date": date,
        "icd_codes": "[]", "cpt_codes": "[]", "ndc_code": ndc,
        "drug_name": drug, "drug_class": cls, "days_supply": days,
        "quantity": days, "provider_id": "PHARM-001", "claim_type": "rx",
    }


def _l(raw_id, date, name, val, unit, loinc="", ref=""):
    return {
        "raw_member_id": raw_id, "test_date": date, "test_name": name,
        "result_value": val, "result_unit": unit,
        "result_text": f"{val} {unit}", "loinc_code": loinc,
        "reference_range": ref,
    }


def _o(raw_id, date, channel, measure, outcome, notes=""):
    return {
        "raw_member_id": raw_id, "contact_date": date,
        "channel": channel, "measure_id": measure,
        "outcome": outcome, "notes": notes,
    }


DEMO_CASES: list[DemoCase] = [

    DemoCase(
        case_id="DEMO-001",
        agent_type="hedis_gap",
        raw_member_id="DEMO-H001",
        measurement_year=2024,
        description="Dual MAC+MAP gap — statin AND ACE adherence both at risk. "
                    "Spanish-speaking, low literacy, 55 days remaining.",
        member_data=_m("DEMO-H001", lang="es", literacy="low", sdoh="medium",
                       barriers=["language_barrier", "cost_concern"], pcp="Dr. Ramos"),
        gaps=[
            _g("DEMO-H001", "MAC", "Medication Adherence for Cholesterol (Statins)", 3.0, 55, pdc=0.72, last_svc="2024-01-30"),
            _g("DEMO-H001", "MAP", "Medication Adherence for Hypertension (ACE/ARB)", 3.0, 55, pdc=0.69, last_svc="2024-01-15"),
        ],
        claims=[
            _c("DEMO-H001", "2024-01-30", "Atorvastatin 40mg", "statin", "0071014210"),
            _c("DEMO-H001", "2024-01-15", "Lisinopril 20mg", "ace_inhibitor", "0093305420"),
        ],
    ),

    DemoCase(
        case_id="DEMO-002",
        agent_type="hedis_gap",
        raw_member_id="DEMO-H002",
        measurement_year=2024,
        description="Elderly member, CBP gap with very high BP (162/98). "
                    "Resistant hypertension pattern. PCP aware. English.",
        member_data=_m("DEMO-H002", literacy="low", sdoh="low", pcp="Dr. Chen"),
        gaps=[_g("DEMO-H002", "CBP", "Controlling High Blood Pressure", 2.0, 90, last_svc="2024-01-05")],
        labs=[
            _l("DEMO-H002", "2024-01-05", "Systolic Blood Pressure", 162, "mmHg", "55284-4", "<140"),
            _l("DEMO-H002", "2024-01-05", "Diastolic Blood Pressure", 98, "mmHg", "8462-4", "<90"),
        ],
        claims=[
            _c("DEMO-H002", "2024-01-10", "Amlodipine 10mg", "calcium_channel_blocker", "0093101556"),
            _c("DEMO-H002", "2024-01-10", "Metoprolol 50mg", "beta_blocker", "0093752501"),
            _c("DEMO-H002", "2024-01-10", "Lisinopril 40mg", "ace_inhibitor", "0093305440"),
        ],
        outreach=[_o("DEMO-H002", "2024-02-01", "phone", "CBP", "reached",
                     "Member aware, PCP visit scheduled for next month")],
    ),

    DemoCase(
        case_id="DEMO-003",
        agent_type="hedis_gap",
        raw_member_id="DEMO-H003",
        measurement_year=2024,
        description="BCS gap — younger eligible member (52yo), no prior mammogram ever. "
                    "High SDOH risk, transportation barrier. English, medium literacy.",
        member_data=_m("DEMO-H003", sdoh="high", barriers=["transportation"],
                       miles=4.2, pcp="Dr. Okafor"),
        gaps=[_g("DEMO-H003", "BCS", "Breast Cancer Screening", 1.0, 180, last_svc=None)],
        outreach=[
            _o("DEMO-H003", "2024-01-20", "phone", "BCS", "no_answer"),
            _o("DEMO-H003", "2024-02-15", "sms", "BCS", "no_answer"),
        ],
    ),

    DemoCase(
        case_id="DEMO-004",
        agent_type="hedis_gap",
        raw_member_id="DEMO-H004",
        measurement_year=2024,
        description="MAD gap (RASA) with recent ER visit for asthma. "
                    "PDC=0.68, exclusion criteria check needed. Cantonese-speaking.",
        member_data=_m("DEMO-H004", lang="zh", literacy="medium", pcp="Dr. Wong"),
        gaps=[_g("DEMO-H004", "MAD", "Medication Adherence for Asthma (RASA)", 3.0, 120, pdc=0.68, last_svc="2024-01-20")],
        claims=[
            _c("DEMO-H004", "2024-01-20", "Fluticasone/Salmeterol 250/50", "rasa", "0173045955"),
            {"raw_member_id": "DEMO-H004", "service_date": "2024-02-28",
             "icd_codes": '["J45.51"]', "cpt_codes": '["99283"]',
             "ndc_code": None, "drug_name": None, "drug_class": None,
             "days_supply": 0, "quantity": 0, "provider_id": "ER-001", "claim_type": "medical"},
        ],
    ),

    DemoCase(
        case_id="DEMO-005",
        agent_type="hedis_gap",
        raw_member_id="DEMO-H005",
        measurement_year=2024,
        description="COL gap — member 68yo, prior FIT test negative 2 years ago. "
                    "Eligible for colonoscopy or stool test. Engaged, high literacy.",
        member_data=_m("DEMO-H005", literacy="high", pcp="Dr. Patel", miles=0.8),
        gaps=[_g("DEMO-H005", "COL", "Colorectal Cancer Screening", 1.0, 150, last_svc="2022-04-01")],
        outreach=[_o("DEMO-H005", "2024-02-10", "portal", "COL", "reached",
                     "Member expressed interest in home FIT kit")],
    ),

    DemoCase(
        case_id="DEMO-006",
        agent_type="diabetes_hedis",
        raw_member_id="DEMO-D001",
        measurement_year=2026,
        description="Newly diagnosed T2DM, GSD first gap year. HbA1c=10.4% (very high). "
                    "No prior diabetes care coordination. English, high literacy.",
        member_data=_m("DEMO-D001", literacy="high", pcp="Dr. Gupta", year=2026),
        gaps=[_g("DEMO-D001", "GSD", "Glycemic Status Assessment for Patients with Diabetes", 3.0, 200, year=2026)],
        labs=[_l("DEMO-D001", "2025-09-01", "Hemoglobin A1c", 10.4, "%", "4548-4", "<7.0")],
        claims=[
            _c("DEMO-D001", "2025-10-01", "Metformin 1000mg", "biguanide", "0093834401"),
        ],
    ),

    DemoCase(
        case_id="DEMO-007",
        agent_type="diabetes_hedis",
        raw_member_id="DEMO-D002",
        measurement_year=2026,
        description="GSD + KED stacked. HbA1c=8.1%, eGFR=55 (CKD stage 3a), uACR missing. "
                    "Nephrologist involved. Spanish-speaking, medium literacy.",
        member_data=_m("DEMO-D002", lang="es", literacy="medium",
                       pcp="Dr. Morales", year=2026),
        gaps=[
            _g("DEMO-D002", "GSD", "Glycemic Status Assessment for Patients with Diabetes", 3.0, 155, year=2026),
            _g("DEMO-D002", "KED", "Kidney Health Evaluation for Patients with Diabetes", 1.0, 155, year=2026),
        ],
        labs=[
            _l("DEMO-D002", "2025-12-01", "Hemoglobin A1c", 8.1, "%", "4548-4", "<7.0"),
            _l("DEMO-D002", "2025-11-15", "eGFR", 55, "mL/min/1.73m2", "33914-3", ">60"),
        ],
    ),

    DemoCase(
        case_id="DEMO-008",
        agent_type="diabetes_hedis",
        raw_member_id="DEMO-D003",
        measurement_year=2026,
        description="3-gap stack: GSD + EED-E + SPD-E. A1c=9.6%, no eye exam in 3yr, "
                    "statin PDC=0.66. Inertia: phone x2 (no answer). Vietnamese-speaking.",
        member_data=_m("DEMO-D003", lang="vi", literacy="low", sdoh="medium",
                       barriers=["language_barrier"], pcp="Dr. Nguyen", year=2026),
        gaps=[
            _g("DEMO-D003", "GSD", "Glycemic Status Assessment for Patients with Diabetes", 3.0, 110, year=2026),
            _g("DEMO-D003", "EED-E", "Eye Exam for Patients with Diabetes", 1.0, 110, last_svc="2022-11-01", year=2026),
            _g("DEMO-D003", "SPD-E", "Statin Therapy for Patients with Diabetes", 1.0, 110, pdc=0.66, last_svc="2025-12-15", year=2026),
        ],
        labs=[_l("DEMO-D003", "2025-10-15", "Hemoglobin A1c", 9.6, "%", "4548-4", "<7.0")],
        outreach=[
            _o("DEMO-D003", "2026-01-10", "phone", "GSD", "no_answer"),
            _o("DEMO-D003", "2026-02-10", "phone", "GSD", "no_answer"),
        ],
    ),

    DemoCase(
        case_id="DEMO-009",
        agent_type="diabetes_hedis",
        raw_member_id="DEMO-D004",
        measurement_year=2026,
        description="BPD-E — BP=152/96 despite 3 antihypertensives. "
                    "Escalation step 1 (first inertia). PCP engaged. English, high literacy.",
        member_data=_m("DEMO-D004", literacy="high", pcp="Dr. Jackson", year=2026),
        gaps=[_g("DEMO-D004", "BPD-E", "Blood Pressure Control for Patients with Diabetes", 1.0, 145, last_svc="2026-01-20", year=2026)],
        labs=[_l("DEMO-D004", "2026-01-20", "Systolic Blood Pressure", 152, "mmHg", "55284-4", "<140")],
        claims=[
            _c("DEMO-D004", "2026-01-05", "Lisinopril 40mg", "ace_inhibitor", "0093305440"),
            _c("DEMO-D004", "2026-01-05", "Amlodipine 10mg", "calcium_channel_blocker", "0093101556"),
            _c("DEMO-D004", "2026-01-05", "Chlorthalidone 25mg", "thiazide_diuretic", "0093201025"),
        ],
        outreach=[_o("DEMO-D004", "2026-02-01", "portal", "BPD-E", "no_answer")],
    ),

    DemoCase(
        case_id="DEMO-010",
        agent_type="diabetes_hedis",
        raw_member_id="DEMO-D005",
        measurement_year=2026,
        description="High-complexity: GSD+KED+BPD-E open. A1c=11.8% (critical), "
                    "eGFR=42 (CKD stage 3b), BP=158/100. Inertia step 2. English, low literacy, high SDOH.",
        member_data=_m("DEMO-D005", literacy="low", sdoh="high",
                       barriers=["transportation", "cost_concern", "low_health_literacy"],
                       pcp="Dr. Williams", year=2026),
        gaps=[
            _g("DEMO-D005", "GSD", "Glycemic Status Assessment for Patients with Diabetes", 3.0, 85, year=2026),
            _g("DEMO-D005", "KED", "Kidney Health Evaluation for Patients with Diabetes", 1.0, 85, year=2026),
            _g("DEMO-D005", "BPD-E", "Blood Pressure Control for Patients with Diabetes", 1.0, 85, last_svc="2025-12-01", year=2026),
        ],
        labs=[
            _l("DEMO-D005", "2025-11-15", "Hemoglobin A1c", 11.8, "%", "4548-4", "<7.0"),
            _l("DEMO-D005", "2025-11-15", "eGFR", 42, "mL/min/1.73m2", "33914-3", ">60"),
            _l("DEMO-D005", "2025-12-01", "Systolic Blood Pressure", 158, "mmHg", "55284-4", "<140"),
        ],
        outreach=[
            _o("DEMO-D005", "2026-01-15", "phone", "GSD", "refused", "Hostile"),
            _o("DEMO-D005", "2026-02-20", "phone", "GSD", "no_answer"),
        ],
    ),
]


def seed_demo_members(store=None) -> None:
    """Seed all 10 demo members into ClinicalStore. Idempotent."""
    from praktor.clinical.data.clinical_store import ClinicalStore
    from praktor.clinical.schemas import hash_member_id

    if store is None:
        store = ClinicalStore()

    for case in DEMO_CASES:
        mhash = hash_member_id(case.raw_member_id)

        m = dict(case.member_data)
        m["member_id_hash"] = mhash
        store.upsert_member(m)

        for g in case.gaps:
            gd = dict(g)
            gd["member_id_hash"] = mhash
            store.insert_gap(gd)

        for c in case.claims:
            cd = dict(c)
            cd["member_id_hash"] = mhash
            store.insert_claim(cd)

        for lab in case.labs:
            ld = dict(lab)
            ld["member_id_hash"] = mhash
            store.insert_lab(ld)

        for o in case.outreach:
            od = dict(o)
            od["member_id_hash"] = mhash
            store.insert_outreach(od)
