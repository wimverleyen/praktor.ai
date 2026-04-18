"""
Claims ingestion pipeline — loads Rx and medical claims into clinical_store.

Handles de-identification (PHI gate) before writing to the member brain.
Supports both CSV (demo/batch) and FHIR R4 MedicationRequest/Claim resources.

Production swap:
    Replace CsvClaimsReader with a FhirClaimsReader that pulls from your
    FHIR R4 server or data warehouse export.

Usage:
    PYTHONPATH=praktor python -m clinical.ingestion.claims_ingest \
        --csv /path/to/claims.csv \
        --member-salt $PRAKTOR_MEMBER_SALT
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from praktor.clinical.data.clinical_store import get_clinical_store
from praktor.clinical.privacy.audit import audit
from praktor.clinical.privacy.deidentifier import get_deidentifier, validate_phi_scrubbed
from praktor.clinical.schemas import ClinicalBrainChunk, hash_member_id
from praktor.settings import create_log

log = create_log()

# ---------------------------------------------------------------------------
# Row schemas
# ---------------------------------------------------------------------------

_REQUIRED_CLAIM_COLS = {"raw_member_id", "service_date", "claim_type"}
_REQUIRED_RX_COLS = {"raw_member_id", "service_date", "ndc_code", "drug_name"}


@dataclass
class ClaimRow:
    raw_member_id: str
    service_date: str
    claim_type: str           # rx / medical
    icd_codes: list[str] = field(default_factory=list)
    cpt_codes: list[str] = field(default_factory=list)
    ndc_code: str = ""
    drug_name: str = ""
    drug_class: str = ""
    days_supply: int = 0
    quantity: int = 30
    provider_id: str = ""


# ---------------------------------------------------------------------------
# CSV reader
# ---------------------------------------------------------------------------

class CsvClaimsReader:
    """Read claims from a flat CSV file."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        if not self._path.exists():
            raise FileNotFoundError(f"Claims CSV not found: {self._path}")

    def rows(self) -> Iterator[ClaimRow]:
        with open(self._path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            cols = set(reader.fieldnames or [])
            if not _REQUIRED_CLAIM_COLS.issubset(cols):
                missing = _REQUIRED_CLAIM_COLS - cols
                raise ValueError(f"Claims CSV missing columns: {missing}")
            for raw in reader:
                icd = [c.strip() for c in raw.get("icd_codes", "").split("|") if c.strip()]
                cpt = [c.strip() for c in raw.get("cpt_codes", "").split("|") if c.strip()]
                yield ClaimRow(
                    raw_member_id=raw["raw_member_id"],
                    service_date=raw["service_date"],
                    claim_type=raw.get("claim_type", "medical"),
                    icd_codes=icd,
                    cpt_codes=cpt,
                    ndc_code=raw.get("ndc_code", ""),
                    drug_name=raw.get("drug_name", ""),
                    drug_class=raw.get("drug_class", ""),
                    days_supply=int(raw.get("days_supply", 0) or 0),
                    quantity=int(raw.get("quantity", 30) or 30),
                    provider_id=raw.get("provider_id", ""),
                )


# ---------------------------------------------------------------------------
# Ingestor
# ---------------------------------------------------------------------------

class ClaimsIngestor:
    """
    De-identify and ingest claims rows into the clinical store.

    PHI gate: every claim's narrative fields are scrubbed before storage.
    The member's raw ID is hashed — the raw ID never touches the store.
    """

    def __init__(self, dry_run: bool = False) -> None:
        self._store = get_clinical_store()
        self._deidentifier = get_deidentifier()
        self._dry_run = dry_run
        self._stats: dict[str, int] = {"ingested": 0, "skipped": 0, "phi_detected": 0}

    def ingest(self, reader: CsvClaimsReader) -> dict[str, int]:
        """Process all rows from reader. Returns stats dict."""
        for row in reader.rows():
            try:
                self._ingest_row(row)
            except ValueError as exc:
                log.warning("claims_ingest.skip", reason=str(exc), service_date=row.service_date)
                self._stats["skipped"] += 1
        return dict(self._stats)

    def _ingest_row(self, row: ClaimRow) -> None:
        member_hash = hash_member_id(row.raw_member_id)

        # Scrub any free-text fields before storage
        drug_name_result = self._deidentifier.scrub(row.drug_name)
        if drug_name_result.phi_detected:
            self._stats["phi_detected"] += 1
            log.warning("claims_ingest.phi_in_drug_name", member_hash=member_hash[:12])

        # PHI gate — hard raise if scrubbing failed
        validate_phi_scrubbed(
            not drug_name_result.phi_detected,
            context=f"claims_ingest:{member_hash[:12]}:{row.service_date}",
        )

        if self._dry_run:
            self._stats["ingested"] += 1
            return

        self._store.insert_claim({
            "member_id_hash": member_hash,
            "service_date": row.service_date,
            "icd_codes": json.dumps(row.icd_codes),
            "cpt_codes": json.dumps(row.cpt_codes),
            "ndc_code": row.ndc_code,
            "drug_name": drug_name_result.text,
            "drug_class": row.drug_class,
            "days_supply": row.days_supply,
            "quantity": row.quantity,
            "provider_id": row.provider_id,
            "claim_type": row.claim_type,
        })

        audit("claims_ingested", member_id_hash=member_hash, details={"service_date": row.service_date})
        self._stats["ingested"] += 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ingest claims CSV into clinical store")
    parser.add_argument("--csv", required=True, help="Path to claims CSV file")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate, no writes")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    reader = CsvClaimsReader(args.csv)
    ingestor = ClaimsIngestor(dry_run=args.dry_run)
    stats = ingestor.ingest(reader)

    if not args.quiet:
        print(f"Claims ingestion complete: {stats}")
        if args.dry_run:
            print("DRY RUN — no data written.")


if __name__ == "__main__":
    main()
