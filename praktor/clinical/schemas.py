"""
Shared data schemas for the clinical reasoning layer.

All member identifiers are hashed before storage — never raw MRN or member_id.
phi_scrubbed=True is enforced as a hard gate before any FAISS write or LLM call.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Member identity helpers
# ---------------------------------------------------------------------------

_MEMBER_SALT = os.getenv("PRAKTOR_MEMBER_SALT", "praktor-clinical-default-salt")
_salt_warned = False


def hash_member_id(raw_member_id: str) -> str:
    """
    One-way hash for member identifiers.
    Uses PRAKTOR_MEMBER_SALT env var — set a unique secret per environment.
    Returns 64-char hex string (full SHA-256).
    """
    global _salt_warned
    if not _salt_warned and _MEMBER_SALT == "praktor-clinical-default-salt":
        logging.getLogger(__name__).warning(
            "PRAKTOR_MEMBER_SALT is not set. "
            "Member ID hashes use a public default — set a unique secret before any non-local deployment."
        )
        _salt_warned = True
    salted = f"{_MEMBER_SALT}:{raw_member_id}"
    return hashlib.sha256(salted.encode()).hexdigest()


def short_id(member_id_hash: str) -> str:
    """First 12 chars for display labels only — never for storage or lookup."""
    return member_id_hash[:12]


# ---------------------------------------------------------------------------
# HEDIS gap record
# ---------------------------------------------------------------------------

@dataclass
class HEDISGap:
    """One open HEDIS gap for a member in the current measurement year."""

    member_id_hash: str
    measure_id: str           # e.g. "MAC", "MAD", "MAP", "CDC-HbA1c", "BCS"
    measure_name: str         # human-readable
    stars_weight: float       # 1.0, 2.0, or 3.0 (triple-weighted = medication adherence)
    measurement_year: int
    days_remaining: int       # days until Dec 31 of measurement_year
    last_service_date: str | None = None   # ISO 8601 or None
    estimated_stars_impact: float = 0.0   # weight × plan-level gap rate contribution
    pdc_current: float | None = None      # current PDC (medication adherence measures)
    pdc_threshold: float = 0.80           # NCQA threshold (0.80 for all adherence measures)

    @property
    def pdc_gap(self) -> float | None:
        """How far below threshold — positive means gap exists."""
        if self.pdc_current is None:
            return None
        return max(0.0, self.pdc_threshold - self.pdc_current)

    @property
    def priority_score(self) -> float:
        """
        Stars weight × urgency (inverse days remaining) × closability.
        Higher = act first.
        """
        urgency = max(0.1, 1.0 - (self.days_remaining / 365.0))
        closability = 1.0 if (self.pdc_gap or 0) < 0.15 else 0.6
        return round(self.stars_weight * urgency * closability, 3)


# ---------------------------------------------------------------------------
# Clinical brain chunk (FAISS unit)
# ---------------------------------------------------------------------------

@dataclass
class ClinicalBrainChunk:
    """
    One document chunk stored in the member's FAISS second brain.

    phi_scrubbed MUST be True before any chunk reaches FAISS or an LLM prompt.
    The privacy gate in member_brain.py raises ValueError if False.
    """

    member_id_hash: str
    source_type: Literal[
        "claim", "ehr_lab", "ehr_vital", "ehr_note",
        "outreach", "sdoh", "rx_fill", "pdc_score"
    ]
    date: str                    # ISO 8601
    content: str                 # de-identified text or structured summary
    phi_scrubbed: bool           # HARD GATE — must be True
    icd_codes: list[str] = field(default_factory=list)
    cpt_codes: list[str] = field(default_factory=list)
    ndc_codes: list[str] = field(default_factory=list)
    provenance: str = ""         # source system + extract date


# ---------------------------------------------------------------------------
# Next Best Action recommendation
# ---------------------------------------------------------------------------

@dataclass
class NextBestAction:
    """Recommendation produced by the HEDIS gap closure agent."""

    member_id_hash: str
    gap_measure_id: str
    action_type: Literal[
        "pcp_warm_outreach",
        "pharmacy_refill_reminder",
        "scheduling_assist",
        "telehealth_offer",
        "member_direct_outreach",
        "exclusion_flag",
        "escalate",
    ]
    priority_score: float
    rationale: str               # from ReAct reasoning chain
    draft_content: str           # ready-to-use outreach message
    language: str                # member preferred language (ISO 639-1)
    closure_probability: float   # model-estimated 0.0–1.0
    reasoning_span_id: str = ""  # OTel span ID — audit trail
    timestamp: float = field(default_factory=time.time)

    @property
    def should_escalate(self) -> bool:
        return self.action_type == "escalate" or self.closure_probability < 0.4


# ---------------------------------------------------------------------------
# Clinical judge score
# ---------------------------------------------------------------------------

@dataclass
class ClinicalJudgeScore:
    """
    9-criterion quality score for a HEDIS NextBestAction recommendation.

    5 base performance dimensions (shared with all agents):
      accuracy, completeness, relevance, conciseness, clarity

    4 clinical extensions (HEDIS-specific):
      gap_identification_accuracy, action_appropriateness,
      evidence_citation_quality, safety_flag_coverage
    """

    recommendation_id: str
    # --- 5 base performance dimensions ---
    accuracy: float = 5.0            # 0–10: factually correct
    completeness: float = 5.0        # 0–10: all required info present
    relevance: float = 5.0           # 0–10: addresses the question
    conciseness: float = 5.0         # 0–10: appropriately brief
    clarity: float = 5.0             # 0–10: clear and easy to understand
    # --- 4 clinical extensions ---
    gap_identification_accuracy: float = 5.0  # 0–10: right gap, right reason
    action_appropriateness: float = 5.0       # 0–10: right action for this member
    evidence_citation_quality: float = 5.0    # 0–10: reasoning grounded in record
    safety_flag_coverage: float = 5.0         # 0–10: exclusions + contraindications
    reasoning: str = ""
    outcome: str | None = None       # "closed" | "not_closed" | "pending"

    @property
    def base_overall(self) -> float:
        """Mean of the 5 base dimensions."""
        return round(
            (self.accuracy + self.completeness + self.relevance
             + self.conciseness + self.clarity) / 5.0,
            2,
        )

    @property
    def clinical_overall(self) -> float:
        """Mean of the 4 clinical extension dimensions."""
        return round(
            (self.gap_identification_accuracy + self.action_appropriateness
             + self.evidence_citation_quality + self.safety_flag_coverage) / 4.0,
            2,
        )

    @property
    def overall(self) -> float:
        """Mean across all 9 criteria."""
        return round(
            (self.accuracy + self.completeness + self.relevance + self.conciseness
             + self.clarity + self.gap_identification_accuracy
             + self.action_appropriateness + self.evidence_citation_quality
             + self.safety_flag_coverage) / 9.0,
            2,
        )

    def summary(self) -> str:
        return (
            f"overall={self.overall:.1f}/10  "
            f"[base: acc={self.accuracy:.1f} cmp={self.completeness:.1f} "
            f"rel={self.relevance:.1f} con={self.conciseness:.1f} cla={self.clarity:.1f}]  "
            f"[clinical: gap_id={self.gap_identification_accuracy:.1f} "
            f"action={self.action_appropriateness:.1f} "
            f"evidence={self.evidence_citation_quality:.1f} "
            f"safety={self.safety_flag_coverage:.1f}]"
        )


# ---------------------------------------------------------------------------
# Diabetes HEDIS judge score
# ---------------------------------------------------------------------------

@dataclass
class DiabetesJudgeScore:
    """
    10-criterion quality score for a diabetes HEDIS recommendation.

    5 base performance dimensions (shared with all agents):
      accuracy, completeness, relevance, conciseness, clarity

    5 diabetes extensions (MY 2026):
      inertia_detection_accuracy, escalation_ladder_correctness,
      gap_stacking_completeness, evidence_anchor_quality,
      safety_exclusion_coverage
    """

    recommendation_id: str
    # --- 5 base performance dimensions ---
    accuracy: float = 5.0
    completeness: float = 5.0
    relevance: float = 5.0
    conciseness: float = 5.0
    clarity: float = 5.0
    # --- 5 diabetes extensions ---
    inertia_detection_accuracy: float = 5.0
    escalation_ladder_correctness: float = 5.0
    gap_stacking_completeness: float = 5.0
    evidence_anchor_quality: float = 5.0
    safety_exclusion_coverage: float = 5.0
    reasoning: str = ""
    outcome: str | None = None

    @property
    def base_overall(self) -> float:
        return round(
            (self.accuracy + self.completeness + self.relevance
             + self.conciseness + self.clarity) / 5.0, 2,
        )

    @property
    def diabetes_overall(self) -> float:
        return round(
            (self.inertia_detection_accuracy + self.escalation_ladder_correctness
             + self.gap_stacking_completeness + self.evidence_anchor_quality
             + self.safety_exclusion_coverage) / 5.0, 2,
        )

    @property
    def overall(self) -> float:
        return round(
            (self.accuracy + self.completeness + self.relevance + self.conciseness
             + self.clarity + self.inertia_detection_accuracy
             + self.escalation_ladder_correctness + self.gap_stacking_completeness
             + self.evidence_anchor_quality + self.safety_exclusion_coverage) / 10.0, 2,
        )

    def summary(self) -> str:
        return (
            f"overall={self.overall:.1f}/10  "
            f"[base: acc={self.accuracy:.1f} cmp={self.completeness:.1f} "
            f"rel={self.relevance:.1f} con={self.conciseness:.1f} cla={self.clarity:.1f}]  "
            f"[diabetes: inertia={self.inertia_detection_accuracy:.1f} "
            f"ladder={self.escalation_ladder_correctness:.1f} "
            f"stacking={self.gap_stacking_completeness:.1f} "
            f"evidence={self.evidence_anchor_quality:.1f} "
            f"safety={self.safety_exclusion_coverage:.1f}]"
        )


# ---------------------------------------------------------------------------
# HEDIS measure catalogue (Phase 1: public NCQA specs only)
# ---------------------------------------------------------------------------

HEDIS_MEASURES: dict[str, dict] = {
    # Triple-weighted (3x STARS) — medication adherence
    "MAC": {
        "name": "Medication Adherence for Cholesterol (Statins)",
        "stars_weight": 3.0,
        "description": "Members 18+ with a statin fill who achieved PDC >= 0.80.",
        "threshold": 0.80,
        "closure_action": "pharmacy_refill_reminder",
        "drug_classes": ["statin"],
        "icd_relevant": ["Z87.39", "I10", "E78.00", "I25.10"],
        "source": "NCQA HEDIS 2024",
    },
    "MAD": {
        "name": "Medication Adherence for Diabetes (Oral Hypoglycemics)",
        "stars_weight": 3.0,
        "description": "Members 18–75 with diabetes and oral hypoglycemic fills who achieved PDC >= 0.80.",
        "threshold": 0.80,
        "closure_action": "pharmacy_refill_reminder",
        "drug_classes": ["oral_hypoglycemic", "metformin", "glp1"],
        "icd_relevant": ["E11", "E11.9", "E11.65"],
        "source": "NCQA HEDIS 2024",
    },
    "MAP": {
        "name": "Medication Adherence for Hypertension (RASA)",
        "stars_weight": 3.0,
        "description": "Members 18–85 with hypertension and RASA fills who achieved PDC >= 0.80.",
        "threshold": 0.80,
        "closure_action": "pharmacy_refill_reminder",
        "drug_classes": ["ace_inhibitor", "arb", "rasa"],
        "icd_relevant": ["I10", "I11", "I12", "I13"],
        "source": "NCQA HEDIS 2024",
    },
    # Double-weighted (2x STARS)
    "CBP": {
        "name": "Controlling High Blood Pressure",
        "stars_weight": 2.0,
        "description": "Members 18–85 with hypertension whose blood pressure was adequately controlled (<140/90).",
        "threshold": None,
        "closure_action": "scheduling_assist",
        "drug_classes": [],
        "icd_relevant": ["I10"],
        "source": "NCQA HEDIS 2024",
    },
    # Single-weighted (1x STARS)
    "CDC-HbA1c": {
        "name": "Comprehensive Diabetes Care: HbA1c Testing",
        "stars_weight": 1.0,
        "description": "Members 18–75 with diabetes who had an HbA1c test in the measurement year.",
        "threshold": None,
        "closure_action": "scheduling_assist",
        "drug_classes": [],
        "icd_relevant": ["E11", "E10", "E13"],
        "source": "NCQA HEDIS 2024",
    },
    "CDC-HbA1c-Control": {
        "name": "Comprehensive Diabetes Care: HbA1c Control (<8%)",
        "stars_weight": 1.0,
        "description": "Members 18–75 with diabetes whose most recent HbA1c was <8.0%.",
        "threshold": None,
        "closure_action": "telehealth_offer",
        "drug_classes": [],
        "icd_relevant": ["E11", "E10", "E13"],
        "source": "NCQA HEDIS 2024",
    },
    "BCS": {
        "name": "Breast Cancer Screening",
        "stars_weight": 1.0,
        "description": "Women 50–74 who had a mammogram in the past 2 years.",
        "threshold": None,
        "closure_action": "scheduling_assist",
        "drug_classes": [],
        "icd_relevant": [],
        "source": "NCQA HEDIS 2024",
    },
    "COL": {
        "name": "Colorectal Cancer Screening",
        "stars_weight": 1.0,
        "description": "Members 45–75 with appropriate colorectal cancer screening.",
        "threshold": None,
        "closure_action": "scheduling_assist",
        "drug_classes": [],
        "icd_relevant": [],
        "source": "NCQA HEDIS 2024",
    },
    # ---------------------------------------------------------------------------
    # Diabetes-specific measures (MY 2026) — from SKILL.md
    # ---------------------------------------------------------------------------
    "GSD": {
        "name": "Glycemic Status Assessment for Patients with Diabetes",
        "stars_weight": 3.0,   # triple-weighted, inverse-scored in MA Stars
        "description": (
            "Members 18–75 with diabetes. Reports three rates: A1c <8.0% (good control), "
            "A1c <7.0% (tighter control subgroup), A1c >9.0% (poor control — INVERSE, "
            "triple-weighted). Missing or unknown result = poor control."
        ),
        "threshold": None,
        "closure_action": "scheduling_assist",
        "drug_classes": [],
        "icd_relevant": ["E11", "E10", "E13", "E11.9", "E11.65"],
        "source": "NCQA HEDIS MY 2026 Technical Specifications",
        "inverse_measure": True,
        "notes": (
            "GMI (Glucose Management Indicator) from CGM is an accepted numerator as of MY 2026. "
            "Untested members auto-fail — highest closure leverage at lowest cost."
        ),
    },
    "KED": {
        "name": "Kidney Health Evaluation for Patients with Diabetes",
        "stars_weight": 1.0,
        "description": (
            "Members 18–85 with diabetes. BOTH eGFR AND uACR required in the measurement year. "
            "eGFR alone fails. uACR alone fails. Both tests must be present."
        ),
        "threshold": None,
        "closure_action": "scheduling_assist",
        "drug_classes": [],
        "icd_relevant": ["E11", "E10", "E13"],
        "source": "NCQA HEDIS MY 2026 Technical Specifications",
        "notes": (
            "uACR is the earliest marker of diabetic kidney disease. "
            "SGLT2i initiation indicated for uACR-positive members (CREDENCE, DAPA-CKD, EMPA-KIDNEY). "
            "Most open gaps are eGFR-only — standing uACR order closes them."
        ),
    },
    "EED-E": {
        "name": "Eye Exam for Patients with Diabetes (ECDS)",
        "stars_weight": 1.0,
        "description": (
            "Members 18–75 with diabetes. Retinal or dilated eye exam by eye care professional "
            "in the measurement year, OR negative exam (no retinopathy) in the prior year."
        ),
        "threshold": None,
        "closure_action": "scheduling_assist",
        "drug_classes": [],
        "icd_relevant": ["E11", "E10", "E13"],
        "source": "NCQA HEDIS MY 2026 Technical Specifications",
        "notes": (
            "Two-year window for negative exams reflects slow retinopathy progression. "
            "Teleophthalmology and in-office retinal imaging (Topcon, IRIS) are measure-compliant. "
            "Supplemental data pipeline from imaging vendors critical — claims miss 20-30% of exams."
        ),
    },
    "SPD-E": {
        "name": "Statin Therapy for Patients with Diabetes (ECDS)",
        "stars_weight": 1.0,
        "description": (
            "Members 40–75 with diabetes and no ASCVD. Two rates: "
            "(a) statin dispensing — at least one statin fill in MY; "
            "(b) statin adherence — PDC >= 0.80. ECDS-only as of MY 2026."
        ),
        "threshold": 0.80,
        "closure_action": "pharmacy_refill_reminder",
        "drug_classes": ["statin"],
        "icd_relevant": ["E11", "E10", "E13"],
        "source": "NCQA HEDIS MY 2026 Technical Specifications",
        "notes": (
            "Diabetes is a CAD risk equivalent — statin is guideline-concordant for nearly all "
            "diabetics 40–75 regardless of LDL (HPS, CARDS, ASCOT-LLA trials). "
            "40-50% of statin starts discontinue within one year. "
            "90-day fills and mail-order conversion raise PDC 10-15 points."
        ),
    },
    "BPD-E": {
        "name": "Blood Pressure Control for Patients with Diabetes (ECDS)",
        "stars_weight": 1.0,
        "description": (
            "Members 18–85 with diabetes. Most recent BP reading < 140/90 mmHg in the MY. "
            "Voluntary ECDS reporting added MY 2026."
        ),
        "threshold": None,
        "closure_action": "scheduling_assist",
        "drug_classes": ["ace_inhibitor", "arb", "thiazide", "ccb"],
        "icd_relevant": ["E11", "E10", "E13", "I10"],
        "source": "NCQA HEDIS MY 2026 Technical Specifications",
        "notes": (
            "Dominantly a data-capture problem. Home BP and RPM readings often never enter "
            "the HEDIS denominator under admin reporting. ECDS from RPM platforms "
            "(Livongo, Omada, Withings) is the MY 2026 unlock. "
            "ADA 2024 clinical target <130/80 — HEDIS threshold <140/90 is the compliance floor."
        ),
    },
}
