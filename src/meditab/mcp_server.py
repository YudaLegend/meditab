"""MCP server v0 — exposes four patient-data tools over stdio.

This is the Pattern B surface (see HANDOFF "Operational model"): the server
doesn't know or care who is calling it. Day 7 wires up a plain Python client
(`scripts/day07_mcp_smoke.py`). A future Pattern A layer (LLM as agent) would
connect to the same tools without any change here.

Tools:
    list_patients()                       -> list[str]
    get_patient(patient_id)               -> str
    get_gold(patient_id)                  -> dict
    store_extraction(patient_id, model, prompt_strategy, prompt_version,
                     run_id, extraction)  -> dict  (ack payload)

Run standalone (mostly for debugging):
    uv run python -m meditab.mcp_server

You normally don't invoke this yourself — the MCP client spawns it as a
subprocess over stdio.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from meditab.mongo import get_db
from meditab.schema import PatientExtraction

mcp = FastMCP("meditab")


# ------------------------------ read tools -------------------------------


@mcp.tool()
def list_patients() -> list[str]:
    """Return all patient IDs present in `raw_notes`, sorted ascending."""
    # TODO(day7):
    #   - db = get_db()
    #   - query raw_notes, project only _id
    #   - return a sorted list of patient_id strings
    db = get_db()
    docs = db["raw_notes"].find({}, {"_id":1})
    return sorted([doc["_id"] for doc in docs])



@mcp.tool()
def get_patient(patient_id: str) -> str:
    """Return the raw Catalan clinical note text for `patient_id`.

    Raises ValueError if the patient is not in `raw_notes`.
    """
    # TODO(day7):
    #   - fetch the single doc where _id == patient_id
    #   - if missing, raise ValueError(f"patient {patient_id!r} not found")
    #   - return doc["text_ca"]
    db = get_db()
    doc = db.raw_notes.find_one({ "_id": patient_id })
    if doc is None:
        raise ValueError(f"patient {patient_id!r} not found")
    return doc["text_ca"]


@mcp.tool()
def get_gold(patient_id: str) -> dict[str, Any]:
    """Return the clinician-gold `PatientExtraction` for `patient_id` as a plain dict.

    Raises ValueError if there is no gold for this patient.
    """
    # TODO(day7):
    #   - fetch the gold doc by _id
    #   - strip the Mongo-only fields that aren't part of PatientExtraction
    #     (_id, source_path, ingested_at) — the caller wants the schema payload
    #   - return the dict
    db = get_db()
    doc = db.gold_extractions.find_one({"_id": patient_id})
    if doc is None:
        raise ValueError(f"gold for patient {patient_id!r} not found")
    
    for field in ("_id", "source_path", "ingested_at"):
        doc.pop(field, None)
    return doc
        



# ------------------------------ write tool -------------------------------


@mcp.tool()
def store_extraction(
    patient_id: str,
    model: str,
    prompt_strategy: str,
    prompt_version: str,
    run_id: str,
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """Persist an LLM-produced extraction into `llm_extractions`.

    Metadata fields let Week 4 sweeps stay queryable:
        model           — vendor model id, e.g. "gemini-2.5-flash"
        prompt_strategy — "zero-shot" | "few-shot-5" | "cot" | ...
        prompt_version  — bumped whenever the prompt text changes
        run_id          — groups all patient rows from one batch execution

    Across different run_ids full history is preserved. Day 9 will add a
    unique index on (run_id, patient_id) and switch this to an upsert so
    retries within a batch overwrite instead of accumulate.

    Returns an ack: {"ok", "patient_id", "model", "run_id", "run_at"}.
    """
    validated = PatientExtraction.model_validate(extraction)
    run_at = datetime.now(timezone.utc)

    db = get_db()
    doc = {
        "patient_id": patient_id,
        "model": model,
        "prompt_strategy": prompt_strategy,
        "prompt_version": prompt_version,
        "run_id": run_id,
        "run_at": run_at,
        "extraction": validated.model_dump(mode="json"),
    }
    db["llm_extractions"].insert_one(doc)
    return {
        "ok": True,
        "patient_id": patient_id,
        "model": model,
        "run_id": run_id,
        "run_at": run_at.isoformat(),
    }



# -------------------------------- entrypoint ------------------------------


if __name__ == "__main__":
    # Default transport is stdio — matches what the Day 7 client expects.
    mcp.run()
