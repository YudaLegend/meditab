"""MongoDB connection helper.

One function: `get_db()`. Reads `MONGO_URI` from env (default localhost). The
hospital machine will set `MONGO_URI` to their internal Mongo; this module
doesn't care.

Collections:
    raw_notes         — one doc per patient: original .txt content.
    gold_extractions  — one doc per patient: clinician-annotated gold.
    llm_extractions   — one doc per (patient, model, run); added Day 9.
"""

from __future__ import annotations

import os

from pymongo import MongoClient
from pymongo.database import Database

DEFAULT_URI = "mongodb://localhost:27017"
DB_NAME = "meditab"


def get_client() -> MongoClient:
    uri = os.getenv("MONGO_URI", DEFAULT_URI)
    return MongoClient(uri)


def get_db(client: MongoClient | None = None) -> Database:
    return (client or get_client())[DB_NAME]


def ensure_indexes(db: Database | None = None) -> None:
    """Declare every index the app depends on. Idempotent — safe to call on
    every server boot. One place to look when ops asks 'what indexes does
    meditab need?'.

    Index inventory:
        llm_extractions: unique on (run_id, patient_id) — makes Day 9 batch
        retries idempotent (same key → upsert overwrites; no accumulation).
        eval_results:    unique on run_id — one summary row per extraction
        run; Day 10 eval re-runs upsert into it.
        llm_judgements:  (run_id, patient_id) compound (non-unique) — fast
        drilldown for error analysis ("show me every judge verdict on run X").
    """
    db = db or get_db()
    db["llm_extractions"].create_index(
        [("run_id", 1), ("patient_id", 1)],
        unique=True,
        name="uniq_run_patient",
    )
    db["eval_results"].create_index(
        [("run_id", 1)], unique=True, name="uniq_eval_run"
    )
    db["llm_judgements"].create_index(
        [("run_id", 1), ("patient_id", 1)], name="judge_run_patient"
    )
    db["eval_field_scores"].create_index(
        [("run_id", 1), ("patient_id", 1), ("farmac", 1), ("field", 1)],
        unique=True,
        name="uniq_eval_field",
    )

