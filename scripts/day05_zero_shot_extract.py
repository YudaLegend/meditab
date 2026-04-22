"""Day 5: zero-shot extraction on one synthetic note; diff vs gold.

Runs the GeminiExtractor on a single patient, prints the extracted JSON,
and lists field-level differences vs the gold.

Usage:
    uv run python scripts/day05_zero_shot_extract.py                 # defaults to synthetic_001
    uv run python scripts/day05_zero_shot_extract.py --pid synthetic_004
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from meditab.llm_client import GeminiExtractor
from meditab.schema import DrugEntry, PatientExtraction

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()


def diff_extraction(
    extracted: PatientExtraction, gold: PatientExtraction
) -> list[str]:
    """Return a flat list of human-readable difference lines."""
    diffs: list[str] = []

    # Match drugs by `farmac` — the canonical key per the annotation schema.
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
                # Deeper AE-by-AE diff deferred to Day 10 eval harness.
                continue
            if ev != gv:
                diffs.append(f"[{farmac}.{field}] extracted={ev!r}  gold={gv!r}")
    return diffs


def main(pid: str, repo_root: Path) -> int:
    note_path = repo_root / "data" / "synthetic" / "notes" / f"{pid}.txt"
    gold_path = repo_root / "data" / "synthetic" / "gold" / f"{pid}.json"

    if not note_path.exists():
        print(f"Note not found: {note_path}")
        return 1
    if not gold_path.exists():
        print(f"Gold not found: {gold_path}")
        return 1

    note_ca = note_path.read_text(encoding="utf-8")
    gold = PatientExtraction.model_validate_json(
        gold_path.read_text(encoding="utf-8")
    )

    print(f"Extracting {pid}...\n")
    extractor = GeminiExtractor()
    extracted = extractor.extract(note_ca, pid, strategy="zero-shot", version="v1")

    print("--- Extracted ---")
    print(extracted.model_dump_json(indent=2))

    print("\n--- Diff vs gold ---")
    diffs = diff_extraction(extracted, gold)
    if not diffs:
        print("(no differences)")
    else:
        for line in diffs:
            print(f"  {line}")
    print(f"\n{len(diffs)} difference(s).")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", default="synthetic_001")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    sys.exit(main(args.pid, repo_root))
