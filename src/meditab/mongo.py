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
