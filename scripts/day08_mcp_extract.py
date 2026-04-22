"""Day 8: end-to-end extraction through MCP.

First real use of Pattern B. The data path has *no disk I/O*:
    get_patient(pid)   → Catalan note
    extractor.extract  → PatientExtraction
    store_extraction   → writes to llm_extractions (tagged with run metadata)
    get_gold(pid)      → gold for the diff

If this runs green on one patient, Day 9's batch loop is trivial.

Prereq:
    docker compose up -d
    uv run python scripts/day06_ingest.py   # if collections are empty

Usage:
    uv run python scripts/day08_mcp_extract.py
    uv run python scripts/day08_mcp_extract.py --pid synthetic_004
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from meditab.llm_client import make_extractor
from meditab.schema import DrugEntry, PatientExtraction

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()


SERVER_PARAMS = StdioServerParameters(
    command="uv",
    args=["run", "python", "-m", "meditab.mcp_server"],
)

# Fixed run config for Day 8 — Week 4 will vary these.
PROMPT_STRATEGY = "zero-shot"
PROMPT_VERSION = "v1"


# --------------------------- MCP result helpers ---------------------------


def _unwrap_text(result) -> str:
    """For tools returning `str` or `dict` — one text block."""
    return result.content[0].text


# --------------------------------- diff -----------------------------------


def diff_extraction(
    extracted: PatientExtraction, gold: PatientExtraction
) -> list[str]:
    """Same shape as Day 5's diff. Lifted here so Day 8 runs standalone.
    Day 10 will move this into a proper eval module."""
    diffs: list[str] = []
    ext_by = {d.farmac: d for d in extracted.drugs}
    gold_by = {d.farmac: d for d in gold.drugs}

    for farmac in set(ext_by) - set(gold_by):
        diffs.append(f"[hallucinated drug] {farmac!r} — not in gold")
    for farmac in set(gold_by) - set(ext_by):
        diffs.append(f"[missed drug]       {farmac!r} — gold has it, extractor missed")

    for farmac in sorted(set(ext_by) & set(gold_by)):
        e = ext_by[farmac]
        g = gold_by[farmac]
        for field in DrugEntry.model_fields:
            ev = getattr(e, field)
            gv = getattr(g, field)
            if field == "efectes_adversos":
                if len(ev) != len(gv):
                    diffs.append(
                        f"[{farmac}.{field}] count {len(ev)} vs gold {len(gv)}"
                    )
                continue
            if ev != gv:
                diffs.append(f"[{farmac}.{field}] extracted={ev!r}  gold={gv!r}")
    return diffs


# --------------------------------- main -----------------------------------


async def run_extraction(pid: str) -> int:
    extractor = make_extractor()  # laptop: Gemini; hospital: Bedrock (Week 3)
    run_id = uuid.uuid4().hex
    print(
        f"run_id={run_id[:8]}...  model={extractor.model_id}  "
        f"strategy={PROMPT_STRATEGY}/{PROMPT_VERSION}"
    )

    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- 1. fetch the note via MCP ---
            result = await session.call_tool("get_patient", {"patient_id": pid})
            note_ca = _unwrap_text(result)
            print(f"Fetched note — {len(note_ca)} chars")

            # --- 2. fetch the gold via MCP (may be absent on real hospital
            #        data until the clinician finishes annotating — skip the
            #        diff in that case). ---
            try:
                result = await session.call_tool("get_gold", {"patient_id": pid})
                gold_dict = json.loads(_unwrap_text(result))
                gold = PatientExtraction.model_validate(gold_dict)
                print(f"Fetched gold — {len(gold.drugs)} drugs")
            except Exception as exc:
                gold = None
                print(f"No gold for {pid} — diff will be skipped ({exc})")

            # --- 3. run the LLM ---
            print("\nExtracting...")
            extracted = extractor.extract(
                note_ca, pid, strategy=PROMPT_STRATEGY, version=PROMPT_VERSION
            )

            # --- 4. persist the extraction via MCP ---
            result = await session.call_tool(
                "store_extraction",
                {
                    "patient_id": pid,
                    "model": extractor.model_id,
                    "prompt_strategy": PROMPT_STRATEGY,
                    "prompt_version": PROMPT_VERSION,
                    "run_id": run_id,
                    "extraction": extracted.model_dump(mode="json"),
                },
            )
            ack = json.loads(_unwrap_text(result))
            assert ack["ok"] is True
            print(f"Stored — run_at={ack['run_at']}")

            # --- 5. diff vs gold (only when gold is available) ---
            if gold is not None:
                print("\n--- Diff vs gold ---")
                diffs = diff_extraction(extracted, gold)
                if not diffs:
                    print("(no differences)")
                else:
                    for line in diffs:
                        print(f"  {line}")
                print(f"\n{len(diffs)} difference(s).")

            print(
                f"\nQuery this run later with:"
                f'\n  db.llm_extractions.find({{"run_id": "{run_id}"}})'
            )

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", default="synthetic_001")
    args = parser.parse_args()

    sys.exit(asyncio.run(run_extraction(args.pid)))
