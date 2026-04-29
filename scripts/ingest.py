"""Ingest notes (and optionally golds) into MongoDB.

Idempotent: re-running upserts by `_id = patient_id`, so no duplicates.
Validates every gold JSON through PatientExtraction on the way in, so a
drifted gold would fail here rather than silently rotting in Mongo.

Prereq: Mongo reachable at MONGO_URI (default localhost:27017).

Usage:
    # Default: ingest synthetic notes only (golds skipped — pass --gold-dir to opt in)
    uv run python scripts/ingest.py

    # Hospital day 1: real notes, no golds yet
    uv run python scripts/ingest.py --notes-dir /path/to/hospital/anonymized

    # Once clinician has annotated some golds:
    uv run python scripts/ingest.py --notes-dir /path/to/notes --gold-dir /path/to/gold

    # Preview without writing
    uv run python scripts/ingest.py --dry-run
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from meditab.mongo import get_db
from meditab.schema import PatientExtraction

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()


def _safe_source_path(path: Path) -> str:
    """Best-effort relative path for the source_path field. Falls back to
    the absolute path string if the file isn't nested deep enough relative
    to the repo (e.g. hospital data lives outside the repo tree)."""
    try:
        return str(path.relative_to(path.parents[2])).replace("\\", "/")
    except (ValueError, IndexError):
        return str(path).replace("\\", "/")


def ingest_notes(notes_dir: Path, db, dry_run: bool) -> int:
    collection = db["raw_notes"]
    count = 0
    for path in sorted(notes_dir.glob("*.txt")):
        pid = path.stem
        doc = {
            "_id": pid,
            "patient_id": pid,
            "text_ca": path.read_text(encoding="utf-8"),
            "source_path": _safe_source_path(path),
            "ingested_at": datetime.now(timezone.utc),
        }
        if dry_run:
            print(f"  [dry-run] would upsert raw_notes/{pid} ({len(doc['text_ca'])} chars)")
        else:
            collection.update_one({"_id": pid}, {"$set": doc}, upsert=True)
            print(f"  upserted raw_notes/{pid} ({len(doc['text_ca'])} chars)")
        count += 1
    return count


def ingest_golds(gold_dir: Path, db, dry_run: bool) -> tuple[int, int]:
    collection = db["gold_extractions"]
    ok = 0
    failed = 0
    for path in sorted(gold_dir.glob("*.json")):
        pid = path.stem
        try:
            # Validate through Pydantic — catches drift between schema and gold.
            extraction = PatientExtraction.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            print(f"  SKIP gold/{pid} — validation failed: {exc}")
            failed += 1
            continue

        # mode="json" serializes `date` objects as ISO strings for Mongo.
        payload = extraction.model_dump(mode="json")
        doc = {
            "_id": pid,
            **payload,
            "source_path": _safe_source_path(path),
            "ingested_at": datetime.now(timezone.utc),
        }
        if dry_run:
            print(f"  [dry-run] would upsert gold_extractions/{pid} ({len(payload['drugs'])} drugs)")
        else:
            collection.update_one({"_id": pid}, {"$set": doc}, upsert=True)
            print(f"  upserted gold_extractions/{pid} ({len(payload['drugs'])} drugs)")
        ok += 1
    return ok, failed


def main(notes_dir: Path, gold_dir: Path | None, dry_run: bool) -> int:
    db = get_db()

    print(f"Ingesting raw notes from {notes_dir}...")
    n_notes = ingest_notes(notes_dir, db, dry_run)

    n_ok, n_failed = 0, 0
    if gold_dir is None:
        print("\n[skip] gold ingestion — no --gold-dir provided")
    elif not gold_dir.exists():
        print(f"\n[skip] gold ingestion — {gold_dir} does not exist")
    else:
        print(f"\nIngesting golds from {gold_dir}...")
        n_ok, n_failed = ingest_golds(gold_dir, db, dry_run)

    print()
    print(f"raw_notes        : {n_notes} document(s)")
    if gold_dir is not None:
        print(f"gold_extractions : {n_ok} ok, {n_failed} failed")
    return 0 if n_failed == 0 else 2


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--notes-dir", type=Path,
        default=repo_root / "data" / "synthetic" / "notes",
        help="Directory of *.txt clinical notes. Default: synthetic set.",
    )
    parser.add_argument(
        "--gold-dir", type=Path, default=None,
        help="Directory of *.json gold extractions. Omit to skip gold ingestion.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sys.exit(main(args.notes_dir, args.gold_dir, args.dry_run))
