"""Day 6: ingest synthetic notes + golds into MongoDB.

Idempotent: re-running upserts by `_id = patient_id`, so no duplicates.
Validates every gold JSON through PatientExtraction on the way in, so a
drifted gold would fail here rather than silently rotting in Mongo.

Prereq: `docker compose up -d` in the repo root.

Usage:
    uv run python scripts/day06_ingest.py
    uv run python scripts/day06_ingest.py --dry-run
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


def ingest_notes(notes_dir: Path, db, dry_run: bool) -> int:
    collection = db["raw_notes"]
    count = 0
    for path in sorted(notes_dir.glob("*.txt")):
        pid = path.stem
        doc = {
            "_id": pid,
            "patient_id": pid,
            "text_ca": path.read_text(encoding="utf-8"),
            "source_path": str(path.relative_to(path.parents[2])).replace("\\", "/"),
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
            "source_path": str(path.relative_to(path.parents[2])).replace("\\", "/"),
            "ingested_at": datetime.now(timezone.utc),
        }
        if dry_run:
            print(f"  [dry-run] would upsert gold_extractions/{pid} ({len(payload['drugs'])} drugs)")
        else:
            collection.update_one({"_id": pid}, {"$set": doc}, upsert=True)
            print(f"  upserted gold_extractions/{pid} ({len(payload['drugs'])} drugs)")
        ok += 1
    return ok, failed


def main(repo_root: Path, dry_run: bool) -> int:
    notes_dir = repo_root / "data" / "synthetic" / "notes"
    gold_dir = repo_root / "data" / "synthetic" / "gold"

    db = get_db()

    print("Ingesting raw notes...")
    n_notes = ingest_notes(notes_dir, db, dry_run)
    print(f"\nIngesting golds...")
    n_ok, n_failed = ingest_golds(gold_dir, db, dry_run)

    print()
    print(f"raw_notes        : {n_notes} document(s)")
    print(f"gold_extractions : {n_ok} ok, {n_failed} failed")
    if not dry_run:
        print(f"\nCollections live at mongodb://localhost:27017/meditab")
    return 0 if n_failed == 0 else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    sys.exit(main(repo_root, args.dry_run))
