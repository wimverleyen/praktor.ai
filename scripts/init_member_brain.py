"""
Initialize the clinical member brain from data extracts or demo seed data.

Usage:
    # Seed with synthetic demo data (no real data required)
    PYTHONPATH=praktor python scripts/init_member_brain.py --seed-demo

    # Ingest from CSV extracts
    PYTHONPATH=praktor python scripts/init_member_brain.py \
        --claims /path/to/claims.csv \
        --members /path/to/members.csv \
        --gaps /path/to/gaps.csv

Demo members (5 synthetic, fully de-identified):
    m001 — Statin adherence gap (MAC, 3x), Spanish-speaking, high SDOH risk
    m002 — Diabetes med adherence gap (MAD, 3x), Vietnamese, PDC=0.71
    m003 — Hypertension RASA gap (MAP, 3x) + HbA1c gap, English, low literacy
    m004 — Breast cancer screening gap (BCS, 1x), English, low SDOH risk
    m005 — Colorectal screening gap (COL, 1x) + Statin gap (MAC, 3x), Mandarin
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "praktor"))

from clinical.schemas import hash_member_id, ClinicalBrainChunk
from clinical.data.clinical_store import get_clinical_store
from clinical.privacy.deidentifier import scrub_text


TODAY = date.today()
YEAR = TODAY.year
DEC_31 = date(YEAR, 12, 31)
DAYS_LEFT = (DEC_31 - TODAY).days


# ---------------------------------------------------------------------------
# Synthetic demo members
# ---------------------------------------------------------------------------

DEMO_MEMBERS = [
    {
        "raw_id": "DEMO-001",
        "plan_id": "PLAN-MA-001",
        "measurement_year": YEAR,
        "language": "es",
        "health_literacy": "low",
        "pcp_id": "PCP-GARCIA",
        "pcp_name": "Dr. Garcia",
        "pcp_language": "es",
        "sdoh_risk": "high",
        "sdoh_barriers": '["transportation", "language"]',
        "pharmacy_name": "CVS Pharmacy",
        "pharmacy_miles": 0.3,
        "gaps": [
            {
                "measure_id": "MAC",
                "measure_name": "Medication Adherence for Cholesterol (Statins)",
                "stars_weight": 3.0,
                "pdc_current": 0.62,
                "pdc_threshold": 0.80,
                "last_service_date": None,
            }
        ],
        "pdc_scores": [
            {
                "drug_class": "statin",
                "measure_id": "MAC",
                "pdc": 0.62,
                "fills_count": 3,
                "last_fill_date": f"{YEAR}-{TODAY.month:02d}-01",
                "next_fill_due": (TODAY - timedelta(days=15)).isoformat(),
                "days_until_gap": 0,
            }
        ],
        "labs": [
            {"test_name": "LDL Cholesterol", "result_value": 148.0, "result_unit": "mg/dL",
             "result_text": "148 mg/dL (elevated)", "loinc_code": "2089-1",
             "reference_range": "<100 mg/dL", "test_date": f"{YEAR-1}-11-15"},
        ],
        "claims_rx": [
            {"drug_name": "Rosuvastatin 20mg", "drug_class": "statin", "days_supply": 30,
             "service_date": f"{YEAR}-02-10", "ndc_code": "00310-0755-30"},
            {"drug_name": "Rosuvastatin 20mg", "drug_class": "statin", "days_supply": 30,
             "service_date": f"{YEAR}-01-08", "ndc_code": "00310-0755-30"},
        ],
        "outreach": [],
    },
    {
        "raw_id": "DEMO-002",
        "plan_id": "PLAN-MA-001",
        "measurement_year": YEAR,
        "language": "vi",
        "health_literacy": "medium",
        "pcp_id": "PCP-NGUYEN",
        "pcp_name": "Dr. Nguyen",
        "pcp_language": "vi",
        "sdoh_risk": "medium",
        "sdoh_barriers": '["language"]',
        "pharmacy_name": "Walgreens",
        "pharmacy_miles": 1.2,
        "gaps": [
            {
                "measure_id": "MAD",
                "measure_name": "Medication Adherence for Diabetes (Oral Hypoglycemics)",
                "stars_weight": 3.0,
                "pdc_current": 0.71,
                "pdc_threshold": 0.80,
                "last_service_date": None,
            }
        ],
        "pdc_scores": [
            {
                "drug_class": "metformin",
                "measure_id": "MAD",
                "pdc": 0.71,
                "fills_count": 5,
                "last_fill_date": f"{YEAR}-{max(1, TODAY.month-1):02d}-15",
                "next_fill_due": (TODAY + timedelta(days=5)).isoformat(),
                "days_until_gap": 5,
            }
        ],
        "labs": [
            {"test_name": "HbA1c", "result_value": 7.8, "result_unit": "%",
             "result_text": "7.8%", "loinc_code": "4548-4",
             "reference_range": "<7.0%", "test_date": f"{YEAR}-03-20"},
        ],
        "claims_rx": [
            {"drug_name": "Metformin 1000mg", "drug_class": "metformin", "days_supply": 90,
             "service_date": f"{YEAR}-01-20", "ndc_code": "00093-1048-01"},
        ],
        "outreach": [
            {"contact_date": f"{YEAR}-03-01", "channel": "phone", "measure_id": "MAD",
             "outcome": "no_answer", "notes": "Left voicemail"},
        ],
    },
    {
        "raw_id": "DEMO-003",
        "plan_id": "PLAN-MA-001",
        "measurement_year": YEAR,
        "language": "en",
        "health_literacy": "low",
        "pcp_id": "PCP-SMITH",
        "pcp_name": "Dr. Smith",
        "pcp_language": "en",
        "sdoh_risk": "medium",
        "sdoh_barriers": '["health_literacy", "cost"]',
        "pharmacy_name": "Rite Aid",
        "pharmacy_miles": 2.1,
        "gaps": [
            {
                "measure_id": "MAP",
                "measure_name": "Medication Adherence for Hypertension (RASA)",
                "stars_weight": 3.0,
                "pdc_current": 0.58,
                "pdc_threshold": 0.80,
                "last_service_date": None,
            },
            {
                "measure_id": "CDC-HbA1c",
                "measure_name": "Comprehensive Diabetes Care: HbA1c Testing",
                "stars_weight": 1.0,
                "pdc_current": None,
                "pdc_threshold": None,
                "last_service_date": f"{YEAR-1}-08-01",
            },
        ],
        "pdc_scores": [
            {
                "drug_class": "ace_inhibitor",
                "measure_id": "MAP",
                "pdc": 0.58,
                "fills_count": 2,
                "last_fill_date": f"{YEAR}-02-28",
                "next_fill_due": (TODAY - timedelta(days=30)).isoformat(),
                "days_until_gap": 0,
            }
        ],
        "labs": [
            {"test_name": "HbA1c", "result_value": 8.9, "result_unit": "%",
             "result_text": "8.9%", "loinc_code": "4548-4",
             "reference_range": "<7.0%", "test_date": f"{YEAR-1}-08-01"},
        ],
        "claims_rx": [
            {"drug_name": "Lisinopril 10mg", "drug_class": "ace_inhibitor", "days_supply": 30,
             "service_date": f"{YEAR}-02-01", "ndc_code": "00093-5098-01"},
        ],
        "outreach": [
            {"contact_date": f"{YEAR}-02-15", "channel": "letter", "measure_id": "MAP",
             "outcome": "unknown", "notes": "Mailed medication adherence letter"},
        ],
    },
    {
        "raw_id": "DEMO-004",
        "plan_id": "PLAN-MA-001",
        "measurement_year": YEAR,
        "language": "en",
        "health_literacy": "high",
        "pcp_id": "PCP-JOHNSON",
        "pcp_name": "Dr. Johnson",
        "pcp_language": "en",
        "sdoh_risk": "low",
        "sdoh_barriers": "[]",
        "pharmacy_name": "CVS Pharmacy",
        "pharmacy_miles": 0.5,
        "gaps": [
            {
                "measure_id": "BCS",
                "measure_name": "Breast Cancer Screening",
                "stars_weight": 1.0,
                "pdc_current": None,
                "pdc_threshold": None,
                "last_service_date": f"{YEAR-3}-06-10",
            }
        ],
        "pdc_scores": [],
        "labs": [],
        "claims_rx": [],
        "outreach": [],
    },
    {
        "raw_id": "DEMO-005",
        "plan_id": "PLAN-MA-001",
        "measurement_year": YEAR,
        "language": "zh",
        "health_literacy": "medium",
        "pcp_id": "PCP-CHEN",
        "pcp_name": "Dr. Chen",
        "pcp_language": "zh",
        "sdoh_risk": "medium",
        "sdoh_barriers": '["language"]',
        "pharmacy_name": "Walgreens",
        "pharmacy_miles": 0.8,
        "gaps": [
            {
                "measure_id": "MAC",
                "measure_name": "Medication Adherence for Cholesterol (Statins)",
                "stars_weight": 3.0,
                "pdc_current": 0.74,
                "pdc_threshold": 0.80,
                "last_service_date": None,
            },
            {
                "measure_id": "COL",
                "measure_name": "Colorectal Cancer Screening",
                "stars_weight": 1.0,
                "pdc_current": None,
                "pdc_threshold": None,
                "last_service_date": f"{YEAR-6}-09-15",
            },
        ],
        "pdc_scores": [
            {
                "drug_class": "statin",
                "measure_id": "MAC",
                "pdc": 0.74,
                "fills_count": 4,
                "last_fill_date": f"{YEAR}-{max(1, TODAY.month-1):02d}-20",
                "next_fill_due": (TODAY + timedelta(days=10)).isoformat(),
                "days_until_gap": 10,
            }
        ],
        "labs": [],
        "claims_rx": [
            {"drug_name": "Atorvastatin 40mg", "drug_class": "statin", "days_supply": 90,
             "service_date": f"{YEAR}-01-25", "ndc_code": "00069-0159-30"},
        ],
        "outreach": [],
    },
]


# ---------------------------------------------------------------------------
# Seeding logic
# ---------------------------------------------------------------------------

def seed_demo(verbose: bool = True) -> list[str]:
    """Seed synthetic demo data. Returns list of member_id_hashes created."""
    store = get_clinical_store()
    hashes = []

    for m in DEMO_MEMBERS:
        raw_id = m["raw_id"]
        member_hash = hash_member_id(raw_id)
        hashes.append(member_hash)

        if verbose:
            print(f"Seeding {raw_id} → {member_hash[:12]}…")

        # Member profile
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

        # Gaps
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

        # PDC scores
        for pdc in m["pdc_scores"]:
            store.upsert_pdc({
                "member_id_hash": member_hash,
                "drug_class": pdc["drug_class"],
                "measure_id": pdc["measure_id"],
                "pdc": pdc["pdc"],
                "fills_count": pdc["fills_count"],
                "last_fill_date": pdc["last_fill_date"],
                "next_fill_due": pdc["next_fill_due"],
                "days_until_gap": pdc["days_until_gap"],
                "computed_date": TODAY.isoformat(),
            })

        # Labs
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

        # Rx claims
        for rx in m["claims_rx"]:
            store.insert_claim({
                "member_id_hash": member_hash,
                "service_date": rx["service_date"],
                "icd_codes": "[]",
                "cpt_codes": "[]",
                "ndc_code": rx["ndc_code"],
                "drug_name": rx["drug_name"],
                "drug_class": rx["drug_class"],
                "days_supply": rx["days_supply"],
                "quantity": rx.get("quantity", 30),
                "provider_id": m["pcp_id"],
                "claim_type": "rx",
            })

        # Outreach
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
            print(f"  Gaps: {gap_ids} | Language: {m['language']} | SDOH: {m['sdoh_risk']}")

    if verbose:
        print(f"\nSeeded {len(hashes)} demo members.")
        print("STARS triple-weighted gaps: MAC×2, MAD×1, MAP×1")
        print("Run demo: PYTHONPATH=praktor python scripts/demo_hedis_agent.py")

    return hashes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Initialize clinical member brain from data or demo seed"
    )
    parser.add_argument("--seed-demo", action="store_true",
                        help="Seed with synthetic demo data (5 members)")
    parser.add_argument("--claims", help="Path to claims CSV extract")
    parser.add_argument("--members", help="Path to members CSV extract")
    parser.add_argument("--gaps", help="Path to HEDIS gaps CSV extract")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.seed_demo:
        hashes = seed_demo(verbose=not args.quiet)
        print("\nMember hashes (use in demo_hedis_agent.py):")
        for h in hashes:
            print(f"  {h}")
        return

    if args.claims or args.members or args.gaps:
        print("CSV ingestion: coming in Phase 2.")
        print("For now, use --seed-demo to generate test data.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
