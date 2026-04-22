"""Day 4: validate every synthetic gold JSON against meditab.schema.

Load each file in data/synthetic/gold/, try to parse it as PatientExtraction,
and print a table of pass/fail. Failures here are exactly the edge cases the
Day 3 generator happened to produce — study them, they're the real value of
this exercise.

Usage:
    uv run python scripts/day04_validate_golds.py
    uv run python scripts/day04_validate_golds.py --verbose   # full error trees
"""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

# `src/` layout: running via `uv run` already puts src on the path.
from meditab.schema import PatientExtraction

sys.stdout.reconfigure(encoding="utf-8")


def validate_one(path: Path) -> tuple[bool, str]:
    """Return (ok, message). `message` is empty on success, else a short summary."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc}"

    try:
        PatientExtraction.model_validate(raw)
    except ValidationError as exc:
        # TODO: format this more nicely. For now, count errors and show the first.
        # Pydantic's exc.errors() returns a list of dicts with 'loc', 'msg', 'type'.
        errors = exc.errors()
        first = errors[0]
        loc = ".".join(str(p) for p in first["loc"])
        return False, f"{len(errors)} error(s); first at {loc}: {first['msg']}"

    return True, ""


def main(gold_dir: Path, verbose: bool) -> int:
    files = sorted(gold_dir.glob("*.json"))
    if not files:
        print(f"No .json files under {gold_dir}")
        return 1

    passed: list[Path] = []
    failed: list[tuple[Path, str]] = []

    for f in files:
        ok, msg = validate_one(f)
        if ok:
            passed.append(f)
            print(f"  PASS  {f.name}")
        else:
            failed.append((f, msg))
            print(f"  FAIL  {f.name} — {msg}")

    print()
    print(f"Summary: {len(passed)}/{len(files)} passed, {len(failed)} failed.")

    if verbose and failed:
        print("\n--- Full error detail for failures ---")
        for path, _ in failed:
            raw = json.loads(path.read_text(encoding="utf-8"))
            try:
                PatientExtraction.model_validate(raw)
            except ValidationError as exc:
                print(f"\n### {path.name}")
                # TODO: if you want to diff the offending fields against the
                # raw JSON, this is where you'd do it.
                print(exc)

    return 0 if not failed else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    gold_dir = repo_root / "data" / "synthetic" / "gold"
    sys.exit(main(gold_dir, verbose=args.verbose))
