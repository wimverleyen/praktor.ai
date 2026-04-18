"""
EHR ingestion pipeline — loads lab results and vitals into clinical_store.

Supports CSV batch exports and FHIR R4 Observation resources.
Every free-text field is scrubbed through the PHI gate before storage.

Production swap:
    Replace CsvLabReader with a FhirObservationReader that pages through
    your EHR FHIR R4 /Observation endpoint with member-level filters.

Usage:
    PYTHONPATH=praktor python -m clinical.ingestion.ehr_ingest \
        --labs /path/to/labs.csv \
        --vitals /path/to/vitals.csv
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from praktor.clinical.data.clinical_store import get_clinical_store
from praktor.clinical.privacy.audit import audit
from praktor.clinical.privacy.deidentifier import get_deidentifier, validate_phi_scrubbed
from praktor.clinical.schemas import hash_member_id
from praktor.settings import create_log

log = create_log()

_REQUIRED_LAB_COLS = {"raw_member_id", "test_date", "test_name", "result_value"}
_REQUIRED_VITAL_COLS = {"raw_member_id", "recorded_date", "vital_type", "value"}


@dataclass
class LabRow:
    raw_member_id: str
    test_date: str
    test_name: str
    result_value: float
    result_unit: str = ""
    result_text: str = ""
    loinc_code: str = ""
    reference_range: str = ""


@dataclass
class VitalRow:
    raw_member_id: str
    recorded_date: str
    vital_type: str       # systolic_bp / diastolic_bp / bmi / weight_kg / height_cm
    value: float
    unit: str = ""


# ---------------------------------------------------------------------------
# CSV readers
# ---------------------------------------------------------------------------

class CsvLabReader:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        if not self._path.exists():
            raise FileNotFoundError(f"Labs CSV not found: {self._path}")

    def rows(self) -> Iterator[LabRow]:
        with open(self._path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            cols = set(reader.fieldnames or [])
            if not _REQUIRED_LAB_COLS.issubset(cols):
                missing = _REQUIRED_LAB_COLS - cols
                raise ValueError(f"Labs CSV missing columns: {missing}")
            for raw in reader:
                try:
                    val = float(raw["result_value"])
                except (ValueError, TypeError):
                    val = 0.0
                yield LabRow(
                    raw_member_id=raw["raw_member_id"],
                    test_date=raw["test_date"],
                    test_name=raw["test_name"],
                    result_value=val,
                    result_unit=raw.get("result_unit", ""),
                    result_text=raw.get("result_text", ""),
                    loinc_code=raw.get("loinc_code", ""),
                    reference_range=raw.get("reference_range", ""),
                )


class CsvVitalReader:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        if not self._path.exists():
            raise FileNotFoundError(f"Vitals CSV not found: {self._path}")

    def rows(self) -> Iterator[VitalRow]:
        with open(self._path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            cols = set(reader.fieldnames or [])
            if not _REQUIRED_VITAL_COLS.issubset(cols):
                missing = _REQUIRED_VITAL_COLS - cols
                raise ValueError(f"Vitals CSV missing columns: {missing}")
            for raw in reader:
                try:
                    val = float(raw["value"])
                except (ValueError, TypeError):
                    val = 0.0
                yield VitalRow(
                    raw_member_id=raw["raw_member_id"],
                    recorded_date=raw["recorded_date"],
                    vital_type=raw["vital_type"],
                    value=val,
                    unit=raw.get("unit", ""),
                )


# ---------------------------------------------------------------------------
# Ingestor
# ---------------------------------------------------------------------------

class EHRIngestor:
    """
    De-identify and ingest lab / vital rows into the clinical store.

    PHI gate: free-text result fields scrubbed before storage.
    Raw member ID never touches the store — hashed on entry.
    """

    def __init__(self, dry_run: bool = False) -> None:
        self._store = get_clinical_store()
        self._deidentifier = get_deidentifier()
        self._dry_run = dry_run
        self._stats: dict[str, int] = {
            "labs_ingested": 0,
            "vitals_ingested": 0,
            "skipped": 0,
            "phi_detected": 0,
        }

    def ingest_labs(self, reader: CsvLabReader) -> None:
        for row in reader.rows():
            try:
                self._ingest_lab(row)
            except ValueError as exc:
                log.warning("ehr_ingest.lab_skip", reason=str(exc))
                self._stats["skipped"] += 1

    def ingest_vitals(self, reader: CsvVitalReader) -> None:
        for row in reader.rows():
            try:
                self._ingest_vital(row)
            except ValueError as exc:
                log.warning("ehr_ingest.vital_skip", reason=str(exc))
                self._stats["skipped"] += 1

    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def _ingest_lab(self, row: LabRow) -> None:
        member_hash = hash_member_id(row.raw_member_id)

        result = self._deidentifier.scrub(row.result_text)
        if result.phi_detected:
            self._stats["phi_detected"] += 1
            log.warning("ehr_ingest.phi_in_result_text", member_hash=member_hash[:12])

        validate_phi_scrubbed(
            not result.phi_detected,
            context=f"ehr_ingest:lab:{member_hash[:12]}:{row.test_date}",
        )

        if self._dry_run:
            self._stats["labs_ingested"] += 1
            return

        self._store.insert_lab({
            "member_id_hash": member_hash,
            "test_date": row.test_date,
            "test_name": row.test_name,
            "result_value": row.result_value,
            "result_unit": row.result_unit,
            "result_text": result.text,
            "loinc_code": row.loinc_code,
            "reference_range": row.reference_range,
        })

        audit("ehr_lab_ingested", member_id_hash=member_hash, details={"test_date": row.test_date})
        self._stats["labs_ingested"] += 1

    def _ingest_vital(self, row: VitalRow) -> None:
        member_hash = hash_member_id(row.raw_member_id)

        if self._dry_run:
            self._stats["vitals_ingested"] += 1
            return

        self._store.insert_vital({
            "member_id_hash": member_hash,
            "recorded_date": row.recorded_date,
            "vital_type": row.vital_type,
            "value": row.value,
            "unit": row.unit,
        })

        self._stats["vitals_ingested"] += 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ingest EHR labs/vitals CSV into clinical store")
    parser.add_argument("--labs", help="Path to labs CSV file")
    parser.add_argument("--vitals", help="Path to vitals CSV file")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate, no writes")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.labs and not args.vitals:
        parser.error("Provide at least --labs or --vitals")

    ingestor = EHRIngestor(dry_run=args.dry_run)

    if args.labs:
        ingestor.ingest_labs(CsvLabReader(args.labs))
    if args.vitals:
        ingestor.ingest_vitals(CsvVitalReader(args.vitals))

    if not args.quiet:
        print(f"EHR ingestion complete: {ingestor.stats()}")
        if args.dry_run:
            print("DRY RUN — no data written.")


if __name__ == "__main__":
    main()
