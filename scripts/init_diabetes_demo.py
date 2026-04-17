"""
Seed synthetic diabetes HEDIS demo members — MY 2026.

Three engineered members for the VP AI Engineering → CIO demo:

  D001 — Maria Lopez: untested GSD (auto-fail, cheapest to close), metformin only,
          Spanish-speaking, high SDOH. Story: "one lab order closes the highest-leverage gap."

  D002 — James Chen: A1c 8.7% trending up, metformin+glipizide ×18 months (therapeutic
          inertia), eGFR 52, uACR missing (KED gap). Story: "clinical depth — inertia
          detection + SGLT2i/CREDENCE recommendation."

  D003 — Patricia Williams: GSD + KED + SPD-E + EED-E all open (4 gaps).
          Story: "gap-stacking economics — one PCP visit = 4 closures."

Usage:
    PYTHONPATH=praktor python scripts/init_diabetes_demo.py
    PYTHONPATH=praktor python scripts/init_diabetes_demo.py --quiet
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from clinical.schemas import hash_member_id, ClinicalBrainChunk
from clinical.data.clinical_store import get_clinical_store

TODAY = date.today()
YEAR = 2026
DEC_31 = date(YEAR, 12, 31)
DAYS_LEFT = (DEC_31 - TODAY).days


# ---------------------------------------------------------------------------
# Diabetes demo member definitions
# ---------------------------------------------------------------------------

DIABETES_DEMO_MEMBERS = [
    # ------------------------------------------------------------------
    # D001 — Maria Lopez
    # Story: untested GSD (no A1c in MY), metformin only, Spanish-speaking,
    #        high SDOH. "Cheapest gap to close — one standing lab order."
    # ------------------------------------------------------------------
    {
        "raw_id": "D001",
        "persona": "Maria Lopez",
        "plan_id": "PLAN-MA-DM-001",
        "measurement_year": YEAR,
        "language": "es",
        "health_literacy": "low",
        "pcp_id": "PCP-MORALES",
        "pcp_name": "Dr. Morales",
        "pcp_language": "es",
        "sdoh_risk": "high",
        "sdoh_barriers": '["transportation", "language", "food_insecurity"]',
        "pharmacy_name": "Farmacia El Sol",
        "pharmacy_miles": 0.4,
        "demo_story": "untested_gsd_cheapest_close",
        "gaps": [
            {
                "measure_id": "GSD",
                "measure_name": "Glycemic Status Assessment for Patients with Diabetes",
                "stars_weight": 3.0,
                "pdc_current": None,
                "pdc_threshold": None,
                "last_service_date": None,   # No A1c in MY → auto-fail
            },
        ],
        "pdc_scores": [],
        "labs": [
            # Last A1c was PRIOR year — not in MY 2026
            {
                "test_name": "HbA1c",
                "result_value": 7.4,
                "result_unit": "%",
                "result_text": "7.4% (within measurement window)",
                "loinc_code": "4548-4",
                "reference_range": "<7.0%",
                "test_date": f"{YEAR - 1}-10-15",  # 2025 — does not satisfy MY 2026
            },
        ],
        "claims_rx": [
            {
                "drug_name": "Metformin 500mg",
                "drug_class": "metformin",
                "days_supply": 90,
                "service_date": f"{YEAR}-01-12",
                "ndc_code": "00093-1048-01",
            },
            {
                "drug_name": "Metformin 500mg",
                "drug_class": "metformin",
                "days_supply": 90,
                "service_date": f"{YEAR - 1}-10-05",
                "ndc_code": "00093-1048-01",
            },
        ],
        "outreach": [],
    },

    # ------------------------------------------------------------------
    # D002 — James Chen
    # Story: A1c 8.7% trending up over 18 months, same regimen (metformin
    #        + glipizide), eGFR 52 (CKD stage 3a), uACR missing → KED gap.
    #        "Therapeutic inertia + SGLT2i/CREDENCE recommendation."
    # ------------------------------------------------------------------
    {
        "raw_id": "D002",
        "persona": "James Chen",
        "plan_id": "PLAN-MA-DM-001",
        "measurement_year": YEAR,
        "language": "en",
        "health_literacy": "medium",
        "pcp_id": "PCP-PATEL",
        "pcp_name": "Dr. Patel",
        "pcp_language": "en",
        "sdoh_risk": "low",
        "sdoh_barriers": "[]",
        "pharmacy_name": "CVS Pharmacy",
        "pharmacy_miles": 0.7,
        "demo_story": "therapeutic_inertia_sglt2i",
        "gaps": [
            {
                "measure_id": "GSD",
                "measure_name": "Glycemic Status Assessment for Patients with Diabetes",
                "stars_weight": 3.0,
                "pdc_current": None,
                "pdc_threshold": None,
                "last_service_date": f"{YEAR}-03-10",  # A1c 8.7% — POOR CONTROL (>8.0%)
            },
            {
                "measure_id": "KED",
                "measure_name": "Kidney Health Evaluation for Patients with Diabetes",
                "stars_weight": 1.0,
                "pdc_current": None,
                "pdc_threshold": None,
                "last_service_date": None,  # uACR missing — eGFR-only fails
            },
        ],
        "pdc_scores": [],
        "labs": [
            # A1c trending up over 18 months — inertia pattern
            {
                "test_name": "HbA1c",
                "result_value": 8.7,
                "result_unit": "%",
                "result_text": "8.7% (above goal, trending up)",
                "loinc_code": "4548-4",
                "reference_range": "<7.0%",
                "test_date": f"{YEAR}-03-10",
            },
            {
                "test_name": "HbA1c",
                "result_value": 8.4,
                "result_unit": "%",
                "result_text": "8.4%",
                "loinc_code": "4548-4",
                "reference_range": "<7.0%",
                "test_date": f"{YEAR - 1}-09-20",
            },
            {
                "test_name": "HbA1c",
                "result_value": 8.1,
                "result_unit": "%",
                "result_text": "8.1%",
                "loinc_code": "4548-4",
                "reference_range": "<7.0%",
                "test_date": f"{YEAR - 1}-03-15",
            },
            # eGFR present (CKD stage 3a) — but uACR ABSENT → KED fails
            {
                "test_name": "eGFR",
                "result_value": 52.0,
                "result_unit": "mL/min/1.73m2",
                "result_text": "52 mL/min/1.73m2 (CKD stage 3a)",
                "loinc_code": "33914-3",
                "reference_range": ">60",
                "test_date": f"{YEAR}-02-18",
            },
            # NO uACR — this is the KED gap
        ],
        "claims_rx": [
            # 18+ months on the same regimen — inertia evidence
            {
                "drug_name": "Metformin 1000mg",
                "drug_class": "metformin",
                "days_supply": 90,
                "service_date": f"{YEAR}-01-08",
                "ndc_code": "00093-1048-01",
            },
            {
                "drug_name": "Glipizide 5mg",
                "drug_class": "sulfonylurea",
                "days_supply": 90,
                "service_date": f"{YEAR}-01-08",
                "ndc_code": "00093-5098-01",
            },
            {
                "drug_name": "Metformin 1000mg",
                "drug_class": "metformin",
                "days_supply": 90,
                "service_date": f"{YEAR - 1}-10-10",
                "ndc_code": "00093-1048-01",
            },
            {
                "drug_name": "Glipizide 5mg",
                "drug_class": "sulfonylurea",
                "days_supply": 90,
                "service_date": f"{YEAR - 1}-10-10",
                "ndc_code": "00093-5098-01",
            },
            {
                "drug_name": "Metformin 1000mg",
                "drug_class": "metformin",
                "days_supply": 90,
                "service_date": f"{YEAR - 1}-07-12",
                "ndc_code": "00093-1048-01",
            },
            {
                "drug_name": "Glipizide 5mg",
                "drug_class": "sulfonylurea",
                "days_supply": 90,
                "service_date": f"{YEAR - 1}-07-12",
                "ndc_code": "00093-5098-01",
            },
        ],
        "outreach": [
            {
                "contact_date": f"{YEAR}-03-20",
                "channel": "phone",
                "measure_id": "GSD",
                "outcome": "reached",
                "notes": "Member aware of A1c trend, open to medication review",
            },
        ],
    },

    # ------------------------------------------------------------------
    # D003 — Patricia Williams
    # Story: 4 open gaps (GSD + KED + SPD-E + EED-E). No A1c tested.
    #        No statin. No eye exam. No kidney labs. No engagement in 8 months.
    #        "Gap-stacking — one PCP visit closes all 4."
    # ------------------------------------------------------------------
    {
        "raw_id": "D003",
        "persona": "Patricia Williams",
        "plan_id": "PLAN-MA-DM-001",
        "measurement_year": YEAR,
        "language": "en",
        "health_literacy": "medium",
        "pcp_id": "PCP-RODRIGUEZ",
        "pcp_name": "Dr. Rodriguez",
        "pcp_language": "en",
        "sdoh_risk": "medium",
        "sdoh_barriers": '["cost", "work_schedule"]',
        "pharmacy_name": "Walgreens",
        "pharmacy_miles": 1.5,
        "demo_story": "gap_stacking_four_measures",
        "gaps": [
            {
                "measure_id": "GSD",
                "measure_name": "Glycemic Status Assessment for Patients with Diabetes",
                "stars_weight": 3.0,
                "pdc_current": None,
                "pdc_threshold": None,
                "last_service_date": None,  # No A1c in MY → auto-fail (triple-weighted)
            },
            {
                "measure_id": "KED",
                "measure_name": "Kidney Health Evaluation for Patients with Diabetes",
                "stars_weight": 1.0,
                "pdc_current": None,
                "pdc_threshold": None,
                "last_service_date": None,  # No eGFR or uACR in MY
            },
            {
                "measure_id": "SPD-E",
                "measure_name": "Statin Therapy for Patients with Diabetes (ECDS)",
                "stars_weight": 1.0,
                "pdc_current": None,
                "pdc_threshold": 0.80,
                "last_service_date": None,  # No statin fill ever
            },
            {
                "measure_id": "EED-E",
                "measure_name": "Eye Exam for Patients with Diabetes (ECDS)",
                "stars_weight": 1.0,
                "pdc_current": None,
                "pdc_threshold": None,
                "last_service_date": f"{YEAR - 2}-08-15",  # >24 months ago — expired
            },
        ],
        "pdc_scores": [],
        "labs": [
            # No labs in MY 2026 — last lab was prior year
            {
                "test_name": "HbA1c",
                "result_value": 8.2,
                "result_unit": "%",
                "result_text": "8.2% (above goal, no follow-up scheduled)",
                "loinc_code": "4548-4",
                "reference_range": "<7.0%",
                "test_date": f"{YEAR - 1}-06-20",  # 2025 — does not satisfy MY 2026
            },
        ],
        "claims_rx": [
            # Diabetes meds only — no statin
            {
                "drug_name": "Metformin 500mg",
                "drug_class": "metformin",
                "days_supply": 90,
                "service_date": f"{YEAR}-02-01",
                "ndc_code": "00093-1048-01",
            },
        ],
        "outreach": [
            {
                "contact_date": f"{YEAR - 1}-08-10",
                "channel": "letter",
                "measure_id": "GSD",
                "outcome": "unknown",
                "notes": "Annual wellness outreach letter — no response",
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------

def seed_diabetes_demo(verbose: bool = True) -> list[str]:
    """Seed diabetes demo members. Returns list of member_id_hashes."""
    store = get_clinical_store()
    hashes = []

    for m in DIABETES_DEMO_MEMBERS:
        raw_id = m["raw_id"]
        member_hash = hash_member_id(raw_id)
        hashes.append(member_hash)

        if verbose:
            print(f"Seeding {raw_id} ({m['persona']}) → {member_hash[:12]}…")

        store.upsert_member({
            "member_id_hash": member_hash,
            "plan_id": m["plan_id"],
            "measurement_year": m["measurement_year"],
            "language": m["language"],
            "health_literacy": m["health_literacy"],
            "pcp_id": m["pcp_id"],
            "pcp_name": m["pcp_name"],
            "pcp_language": m["pcp_language"],
            "sdoh_risk": m["sdoh_risk"],
            "sdoh_barriers": m["sdoh_barriers"],
            "pharmacy_name": m["pharmacy_name"],
            "pharmacy_miles": m["pharmacy_miles"],
        })

        for gap in m["gaps"]:
            store.insert_gap({
                "member_id_hash": member_hash,
                "measure_id": gap["measure_id"],
                "measure_name": gap["measure_name"],
                "stars_weight": gap["stars_weight"],
                "measurement_year": YEAR,
                "days_remaining": DAYS_LEFT,
                "last_service_date": gap.get("last_service_date"),
                "pdc_current": gap.get("pdc_current"),
                "pdc_threshold": gap.get("pdc_threshold", 0.80),
                "status": "open",
            })

        for lab in m["labs"]:
            store.insert_lab({
                "member_id_hash": member_hash,
                "test_date": lab["test_date"],
                "test_name": lab["test_name"],
                "result_value": lab["result_value"],
                "result_unit": lab["result_unit"],
                "result_text": lab["result_text"],
                "loinc_code": lab["loinc_code"],
                "reference_range": lab["reference_range"],
            })

        for rx in m["claims_rx"]:
            store.insert_claim({
                "member_id_hash": member_hash,
                "service_date": rx["service_date"],
                "icd_codes": '["E11.9"]',
                "cpt_codes": "[]",
                "ndc_code": rx["ndc_code"],
                "drug_name": rx["drug_name"],
                "drug_class": rx["drug_class"],
                "days_supply": rx["days_supply"],
                "quantity": rx.get("quantity", 90),
                "provider_id": m["pcp_id"],
                "claim_type": "rx",
            })

        for o in m["outreach"]:
            store.insert_outreach({
                "member_id_hash": member_hash,
                "contact_date": o["contact_date"],
                "channel": o["channel"],
                "measure_id": o["measure_id"],
                "outcome": o["outcome"],
                "notes": o["notes"],
            })

        if verbose:
            gap_ids = [g["measure_id"] for g in m["gaps"]]
            stars_total = sum(g["stars_weight"] for g in m["gaps"])
            print(f"  Gaps: {gap_ids} | Stars exposure: {stars_total:.0f}x | "
                  f"Language: {m['language']} | Story: {m['demo_story']}")

    if verbose:
        print(f"\nSeeded {len(hashes)} diabetes demo members (MY {YEAR}).")
        print("Stories: untested_gsd | therapeutic_inertia | gap_stacking")
        print("Run demo: PYTHONPATH=praktor python scripts/demo_diabetes_agent.py --dry-run")

    return hashes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Seed diabetes HEDIS demo members (MY 2026)")
    parser.add_argument("--quiet", action="store_true", help="Suppress output")
    args = parser.parse_args()
    seed_diabetes_demo(verbose=not args.quiet)


if __name__ == "__main__":
    main()
