"""Batch extraction across every patient in raw_notes.

Scales extract_one.py to all patients, all through MCP. Every invocation
gets a fresh run_id; every row written by this invocation shares that
run_id in llm_extractions. evaluate.py filters by run_id.

Design calls:
  - One run_id per invocation (not per patient).
  - Per-patient try/except — one bad apple does not kill the batch.
  - Structured JSONL log at logs/batch_<run_id8>.jsonl, one line per patient.
  - MCP session is opened once; all patients share it.

Prereq:
    uv run python scripts/ingest.py   # if collections are empty

Usage:
    uv run python scripts/extract_batch.py
    uv run python scripts/extract_batch.py --limit 3      # smoke
    uv run python scripts/extract_batch.py --strategy few-shot --version v1
    MEDITAB_LLM_PROVIDER=groq uv run python scripts/extract_batch.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from meditab.llm_client import make_extractor

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()


SERVER_PARAMS = StdioServerParameters(
    command="uv",
    args=["run", "python", "-m", "meditab.mcp_server"],
)

DEFAULT_STRATEGY = "zero-shot"
DEFAULT_VERSION = "v1"

LOG_DIR = Path("logs")


# --------------------------- MCP result helpers ---------------------------


def _unwrap_text(result) -> str:
    """Tools returning str or dict — one TextContent block."""
    return result.content[0].text


def _unwrap_list(result) -> list[str]:
    """Tools returning list[X] — FastMCP splits into one block per element
    (same quirk Day 7 smoke test called out)."""
    return [block.text for block in result.content]


# --------------------------- JSONL logging --------------------------------


class JsonlLogger:
    """Append-only JSONL sink. Flushes on every write so tail -f works and
    a crash mid-batch still leaves valid parseable lines on disk."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", encoding="utf-8")
        self.path = path

    def write(self, row: dict[str, Any]) -> None:
        self._fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------- per-patient body ------------------------------


async def extract_one(
    session: ClientSession,
    pid: str,
    *,
    extractor,
    run_id: str,
    strategy: str,
    version: str,
) -> dict[str, Any]:
    """Run the full extract-and-store cycle for one patient.

    Returns a JSONL-ready dict describing the outcome. This function is
    responsible for TIMING and for wrapping the LLM/store calls in a
    try/except so a single-patient failure becomes a log row, not a crash.

    Shape of returned dict:
        ok    -> {"ts", "run_id", "pid", "status": "ok",   "elapsed_ms", "n_drugs"}
        fail  -> {"ts", "run_id", "pid", "status": "fail", "elapsed_ms", "error"}
    """
    t0 = time.perf_counter()
    try:
        result = await session.call_tool("get_patient", {"patient_id": pid})
        note_ca = _unwrap_text(result)

        extracted = extractor.extract(
            note_ca, pid, strategy=strategy, version=version
        )

        await session.call_tool(
            "store_extraction",
            {
                "patient_id": pid,
                "model": extractor.model_id,
                "prompt_strategy": strategy,
                "prompt_version": version,
                "run_id": run_id,
                "extraction": extracted.model_dump(mode="json"),
            },
        )
    except Exception as exc:
        return {
            "pid": pid,
            "status": "fail",
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "error": repr(exc),
        }

    return {
        "pid": pid,
        "status": "ok",
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        "n_drugs": len(extracted.drugs),
    }


# ---------------------------------- main -----------------------------------


async def run_batch(limit: int | None, strategy: str, version: str) -> int:
    extractor = make_extractor()
    run_id = uuid.uuid4().hex
    log_path = LOG_DIR / f"batch_{run_id[:8]}.jsonl"
    logger = JsonlLogger(log_path)

    print(
        f"run_id={run_id[:8]}...  model={extractor.model_id}  "
        f"strategy={strategy}/{version}"
    )
    print(f"log: {log_path}")

    n_ok = n_fail = 0
    t_batch = time.perf_counter()

    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Fetch the full patient list through MCP — same surface the
            # hospital-day code will use.
            result = await session.call_tool("list_patients", {})
            patients = _unwrap_list(result)
            if limit is not None:
                patients = patients[:limit]
            print(f"patients to process: {len(patients)}")

            for i, pid in enumerate(patients, 1):
                row = await extract_one(
                    session,
                    pid,
                    extractor=extractor,
                    run_id=run_id,
                    strategy=strategy,
                    version=version,
                )
                # Every row gets ts + run_id added here so extract_one
                # doesn't have to remember.
                row = {"ts": _now_iso(), "run_id": run_id, **row}
                logger.write(row)

                if row["status"] == "ok":
                    n_ok += 1
                    print(
                        f"  [{i:02d}/{len(patients)}] {pid}  ok  "
                        f"{row['elapsed_ms']} ms  {row['n_drugs']} drug(s)"
                    )
                else:
                    n_fail += 1
                    print(
                        f"  [{i:02d}/{len(patients)}] {pid}  FAIL  "
                        f"{row['elapsed_ms']} ms  {row['error']}"
                    )

    logger.close()
    elapsed_batch_s = time.perf_counter() - t_batch
    print(
        f"\nbatch done  ok={n_ok}  fail={n_fail}  "
        f"total={elapsed_batch_s:.1f}s  log={log_path}"
    )
    print(
        f'\nQuery this run:\n'
        f'  db.llm_extractions.find({{"run_id": "{run_id}"}})'
    )
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N patients (smoke mode).")
    parser.add_argument("--strategy", default=DEFAULT_STRATEGY,
                        help="Prompt strategy registered in meditab.prompts "
                             "(e.g. 'zero-shot', 'few-shot', 'cot').")
    parser.add_argument("--version", default=DEFAULT_VERSION,
                        help="Prompt version (e.g. 'v1').")
    args = parser.parse_args()
    sys.exit(asyncio.run(run_batch(args.limit, args.strategy, args.version)))
