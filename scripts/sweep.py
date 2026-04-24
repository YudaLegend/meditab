"""Full sweep: providers × models × prompt strategies, one command.

Each row in `CELLS` is one combination to run. For each cell we:
    1. export MEDITAB_LLM_PROVIDER + optional model override into the env,
    2. spawn extract_batch.py (captures run_id from stdout),
    3. spawn evaluate.py --run-id <that run_id>,
    4. record the run_id + cell metadata.
At the end we pull every cell's row out of `eval_results` and print one
comparison table — same providers-models-prompts down the rows, same
fields across the columns.

Edit `CELLS` to change the sweep. That list is the single source of truth
for what you're comparing. Judge provider is taken from
MEDITAB_JUDGE_PROVIDER — keep it pinned while extraction cells vary, so
score deltas reflect extraction changes, not judge drift.

Usage:
    # default CELLS (see below)
    MEDITAB_JUDGE_PROVIDER=groq uv run python scripts/sweep.py

    # smoke — 2 patients per cell
    MEDITAB_JUDGE_PROVIDER=groq uv run python scripts/sweep.py --limit 2
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()


# --------------------------- the sweep definition -------------------------


@dataclass(frozen=True)
class Cell:
    """One extraction+eval combination to run.

    provider: which MEDITAB_LLM_PROVIDER to set for this cell ("groq",
              "gemini", "bedrock").
    model:    optional model override — e.g. "meta-llama/llama-3.3-70b-versatile"
              for Groq. None means "use the provider's default".
              Wired in per-provider via GROQ_MODEL / GEMINI_MODEL /
              BEDROCK_MODEL env vars; the extractor class reads these.
    strategy: prompt strategy key registered in meditab.prompts.PROMPTS
              (e.g. "zero-shot", "few-shot", "cot").
    version:  prompt version key. Bumped when prompt text changes.
    """

    provider: str
    model: str | None
    strategy: str
    version: str = "v1"

    @property
    def label(self) -> str:
        m = (self.model or f"{self.provider}-default").split("/")[-1][:30]
        return f"{self.provider}/{m} · {self.strategy}/{self.version}"


# ---- edit this list to change what the sweep runs -------------------------

CELLS: list[Cell] = [
    # Laptop dev: Llama 4 Scout on Groq, all three prompting strategies.
    Cell(provider="groq", model=None, strategy="zero-shot", version="v1"),
    Cell(provider="groq", model=None, strategy="few-shot",  version="v1"),
    Cell(provider="groq", model=None, strategy="cot",       version="v1"),

    # Example hospital-day rows (uncomment when Bedrock is available):
    # Cell("bedrock", "anthropic.claude-haiku-20240307-v1:0", "zero-shot"),
    # Cell("bedrock", "meta.llama3-70b-instruct-v1:0",        "zero-shot"),
    # Cell("bedrock", "mistral.mistral-large-2402-v1:0",      "zero-shot"),
]


# --------------------------- run_id extraction ----------------------------

# Stable across every extract_batch.py print that mentions run_id.
_RUN_ID_FULL_RE = re.compile(r'"run_id":\s*"([0-9a-f]{32})"')
_RUN_ID_SHORT_RE = re.compile(r"run_id=([0-9a-f]{8,})")


def _extract_run_id(output: str) -> str:
    m = _RUN_ID_FULL_RE.search(output)
    if m:
        return m.group(1)
    m = _RUN_ID_SHORT_RE.search(output)
    if m:
        return m.group(1)
    raise RuntimeError("could not find run_id in batch output")


# --------------------------- sub-process plumbing -------------------------


def _run_and_capture(cmd: list[str], env: dict[str, str]) -> tuple[str, int]:
    """Stream a subprocess's output to our stdout AND capture it for parsing.
    Never raises on non-zero rc — the caller decides.
    """
    print(f"\n$ {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", bufsize=1,
        env=env,
    )
    lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="")
        lines.append(line)
    return "".join(lines), proc.wait()


def _env_for_cell(cell: Cell) -> dict[str, str]:
    """Return a copy of os.environ with this cell's provider + model set.

    We set the model via the provider-specific env var the extractor classes
    already read (GROQ_MODEL / GEMINI_MODEL / BEDROCK_MODEL). None leaves
    the env var unset, which falls back to each class's built-in default.
    """
    env = {**os.environ, "MEDITAB_LLM_PROVIDER": cell.provider}
    if cell.model is not None:
        key = {
            "groq": "GROQ_MODEL",
            "gemini": "GEMINI_MODEL",
            "bedrock": "BEDROCK_MODEL",
        }[cell.provider]
        env[key] = cell.model
    return env


def _run_one_cell(cell: Cell, limit: int | None) -> str:
    """Run extract + eval for one cell. Returns the extraction run_id.

    Extraction partial failures (rc=1: some patients rejected) are OK —
    we still want to eval the rest. Only structural failures (rc>1 or no
    run_id parseable) abort.
    """
    env = _env_for_cell(cell)

    extract_cmd = [
        "uv", "run", "python", "scripts/extract_batch.py",
        "--strategy", cell.strategy, "--version", cell.version,
    ]
    if limit is not None:
        extract_cmd += ["--limit", str(limit)]
    out, rc = _run_and_capture(extract_cmd, env)
    if rc not in (0, 1):
        raise RuntimeError(
            f"extraction failed structurally (rc={rc}): {' '.join(extract_cmd)}"
        )
    if rc == 1:
        print("  [sweep] partial failure — continuing to eval")
    run_id = _extract_run_id(out)

    eval_cmd = ["uv", "run", "python", "scripts/evaluate.py",
                "--run-id", run_id]
    _, rc = _run_and_capture(eval_cmd, env)
    if rc != 0:
        raise RuntimeError(f"eval failed (rc={rc}): {' '.join(eval_cmd)}")
    return run_id


# ----------------------------- comparison table ---------------------------


def _print_comparison(cells: list[Cell], run_ids: list[str]) -> None:
    from meditab.mongo import get_db

    db = get_db()
    rows_by_run = {
        r["run_id"]: r
        for r in db["eval_results"].find({"run_id": {"$in": run_ids}})
    }

    # Collect every field name that appeared in any row, preserving order.
    all_fields: list[str] = []
    seen: set[str] = set()
    for rid in run_ids:
        row = rows_by_run.get(rid, {})
        for f in row.get("field_means", {}):
            if f not in seen:
                all_fields.append(f)
                seen.add(f)

    print("\n" + "=" * 120)
    print("SWEEP COMPARISON")
    print("=" * 120)
    header = (
        f'{"cell":<50} {"n_ok":>5} {"macro":>7} {"drugF1":>7}  '
        + "  ".join(f"{f[:12]:>12}" for f in all_fields)
    )
    print(header)
    print("-" * len(header))
    for cell, rid in zip(cells, run_ids):
        r = rows_by_run.get(rid)
        if r is None:
            print(f'{cell.label:<50} (no eval_results row)')
            continue
        fm = r.get("field_means", {})
        print(
            f'{cell.label:<50} {r["n_patients_scored"]:>5} '
            f'{r["overall_field_macro"]:>7.3f} {r["drug_f1"]:>7.3f}  '
            + "  ".join(f'{fm.get(f, 0.0):>12.3f}' for f in all_fields)
        )
    print("=" * 120)


# ---------------------------------- main ----------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N patients per cell.")
    args = parser.parse_args()

    print(f"CELLS ({len(CELLS)}):")
    for c in CELLS:
        print(f"  - {c.label}")
    judge = os.getenv("MEDITAB_JUDGE_PROVIDER", "gemini")
    print(f"judge provider (pinned): {judge}")
    if args.limit:
        print(f"limit per cell: {args.limit}")

    run_ids: list[str] = []
    for cell in CELLS:
        print(f"\n>>> CELL: {cell.label}")
        run_ids.append(_run_one_cell(cell, args.limit))

    _print_comparison(CELLS, run_ids)
    print("\nsweep done. run_ids:")
    for cell, rid in zip(CELLS, run_ids):
        print(f"  {cell.label}  →  {rid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
