"""MCP server v0 — exposes four patient-data tools over stdio.

This is the Pattern B surface (see HANDOFF "Operational model"): the server
doesn't know or care who is calling it. Day 7 wires up a plain Python client
(`scripts/day07_mcp_smoke.py`). A future Pattern A layer (LLM as agent) would
connect to the same tools without any change here.

Tools:
    list_patients()                       -> list[str]
    get_patient(patient_id)               -> str
    get_gold(patient_id)                  -> dict
    store_extraction(patient_id, model, extraction) -> dict  (ack payload)

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
    raise NotImplementedError("TODO(day7): implement list_patients")


@mcp.tool()
def get_patient(patient_id: str) -> str:
    """Return the raw Catalan clinical note text for `patient_id`.

    Raises ValueError if the patient is not in `raw_notes`.
    """
    # TODO(day7):
    #   - fetch the single doc where _id == patient_id
    #   - if missing, raise ValueError(f"patient {patient_id!r} not found")
    #   - return doc["text_ca"]
    raise NotImplementedError("TODO(day7): implement get_patient")


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
    raise NotImplementedError("TODO(day7): implement get_gold")


# ------------------------------ write tool -------------------------------


@mcp.tool()
def store_extraction(
    patient_id: str,
    model: str,
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """Persist an LLM-produced extraction into `llm_extractions`.

    `extraction` must be a JSON-compatible dict that validates as a
    `PatientExtraction`. One row per (patient_id, model, run_at) — we do NOT
    deduplicate across runs, because Day 9 batch experiments want the history.

    Returns an ack: {"ok": True, "patient_id": ..., "model": ..., "run_at": ISO}.
    """
    # Validate before writing so a malformed payload fails loudly here rather
    # than corrupting the collection. (This IS the scaffolding — don't change.)
    validated = PatientExtraction.model_validate(extraction)
    run_at = datetime.now(timezone.utc)

    # TODO(day7):
    #   - db = get_db()
    #   - build the doc:
    #       {
    #         "patient_id": patient_id,
    #         "model": model,
    #         "run_at": run_at,
    #         "extraction": validated.model_dump(mode="json"),
    #       }
    #   - insert_one into db["llm_extractions"]
    #   - return {"ok": True, "patient_id": patient_id, "model": model,
    #             "run_at": run_at.isoformat()}
    raise NotImplementedError("TODO(day7): implement store_extraction")


# -------------------------------- entrypoint ------------------------------


if __name__ == "__main__":
    # Default transport is stdio — matches what the Day 7 client expects.
    mcp.run()
