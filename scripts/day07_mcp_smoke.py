"""Day 7: MCP smoke test — spawns the server over stdio and calls each tool.

This is our Pattern B proof: the server is a plain subprocess, the client
is plain Python, and there is no LLM in the loop. If this script prints
"ALL TOOLS OK" at the end, the MCP surface is ready for Day 8 (refactor
extraction to go through MCP).

Prereq:
    docker compose up -d          # Mongo must be live
    uv run python scripts/day06_ingest.py   # only if collections are empty

Usage:
    uv run python scripts/day07_mcp_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding="utf-8")


# How we launch the server. `python -m meditab.mcp_server` works because the
# package is installed into the uv-managed venv (see pyproject.toml).
SERVER_PARAMS = StdioServerParameters(
    command="uv",
    args=["run", "python", "-m", "meditab.mcp_server"],
)


def _unwrap_text(result) -> str:
    """FastMCP tool results come back as a list of content blocks. For Day 7
    all our tool return values are serialized into a single text block, so we
    grab .text off the first block."""
    return result.content[0].text


async def run_smoke() -> int:
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- discover: prove tool schemas made it across the wire ---
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(f"Discovered tools: {names}")
            expected = {"list_patients", "get_patient", "get_gold", "store_extraction"}
            assert set(names) == expected, f"missing tools: {expected - set(names)}"

            # --- list_patients ---
            # TODO(day7):
            #   - call session.call_tool("list_patients", {})
            #   - parse the JSON text out via _unwrap_text + json.loads
            #   - assert it's a non-empty list of strings
            #   - pick pids[0] as `sample_id` to reuse below
            #   - print "list_patients OK — N patients"
            raise NotImplementedError("TODO(day7): call list_patients")

            # --- get_patient ---
            # TODO(day7):
            #   - call session.call_tool("get_patient", {"patient_id": sample_id})
            #   - _unwrap_text → string; assert len > 0
            #   - print "get_patient OK — N chars"

            # --- get_gold ---
            # TODO(day7):
            #   - call get_gold for sample_id
            #   - json.loads the text
            #   - assert gold["patient_id"] == sample_id
            #   - assert "drugs" in gold
            #   - print "get_gold OK — N drugs"

            # --- store_extraction ---
            # TODO(day7):
            #   - reuse the gold payload from above as a stand-in extraction
            #     (it's a valid PatientExtraction by construction) — this is
            #     just a write-path smoke test, not a real LLM run
            #   - call session.call_tool("store_extraction", {
            #         "patient_id": sample_id,
            #         "model": "smoke-test",
            #         "extraction": gold,
            #     })
            #   - json.loads the ack; assert ack["ok"] is True
            #   - print "store_extraction OK — run_at=..."

            print("\nALL TOOLS OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_smoke()))
