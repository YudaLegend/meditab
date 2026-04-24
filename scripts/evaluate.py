"""Evaluate a batch run against gold.

Reads all `llm_extractions` rows for a `run_id`, joins to `gold_extractions`
by `patient_id`, scores per field per drug per patient via `meditab.eval`,
aggregates, prints a summary table, and writes one summary row to a new
`eval_results` collection (plus per-field rows to `eval_field_scores` for
Day 11 drilldown).

Judge calls (for resposta_clinica, motiu_discontinuacio) go to the LLM
picked by MEDITAB_JUDGE_PROVIDER (default: gemini). Every verdict lands in
`llm_judgements` with its (judge_model, judge_version) — audit trail.

Usage:
    uv run python scripts/evaluate.py                         # latest run
    uv run python scripts/evaluate.py --run-id 69713142...    # specific
    uv run python scripts/evaluate.py --limit 3               # smoke
    MEDITAB_JUDGE_PROVIDER=groq uv run python scripts/evaluate.py
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from dotenv import load_dotenv

from meditab.eval import PatientScore, score_patient
from meditab.judge import (
    JUDGE_PROMPT_STRATEGY,
    JUDGE_PROMPT_VERSION,
    make_judge,
)
from meditab.mongo import get_db
from meditab.schema import PatientExtraction

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()


# ------------------------------ run selection -----------------------------


def _latest_run_id(db) -> str:
    """Return the run_id of the most recently stored llm_extractions row."""
    doc = db["llm_extractions"].find_one(sort=[("run_at", -1)])
    if doc is None:
        raise RuntimeError(
            "llm_extractions is empty — run Day 8 or Day 9 first"
        )
    return doc["run_id"]


def _load_run_rows(db, run_id: str) -> list[dict[str, Any]]:
    rows = list(db["llm_extractions"].find({"run_id": run_id}))
    if not rows:
        raise RuntimeError(f"no llm_extractions rows for run_id={run_id!r}")
    return rows


def _load_gold(db, patient_id: str) -> PatientExtraction | None:
    doc = db["gold_extractions"].find_one({"_id": patient_id})
    if doc is None:
        return None
    for f in ("_id", "source_path", "ingested_at"):
        doc.pop(f, None)
    return PatientExtraction.model_validate(doc)


# ------------------------------ aggregation -------------------------------


def _aggregate_field_scores(
    patient_scores: list[PatientScore],
) -> dict[str, float]:
    """Mean per-field score across ALL matched drug pairs in ALL patients."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for ps in patient_scores:
        for ds in ps.drug_scores:
            for fs in ds.field_scores:
                buckets[fs.field].append(fs.score)
    return {field: mean(scores) for field, scores in buckets.items() if scores}


def _aggregate_drug_prf(
    patient_scores: list[PatientScore],
) -> tuple[float, float, float]:
    """Macro-averaged drug-level precision/recall/F1 across patients."""
    if not patient_scores:
        return 0.0, 0.0, 0.0
    p = mean(ps.drug_precision for ps in patient_scores)
    r = mean(ps.drug_recall for ps in patient_scores)
    f1 = mean(ps.drug_f1 for ps in patient_scores)
    return p, r, f1


# --------------------------------- main -----------------------------------


def _persist_field_scores(
    db, run_id: str, sample_meta: dict, patient_score: PatientScore,
    evaluated_at: datetime,
) -> None:
    """Write one doc per (patient, drug, field) into eval_field_scores.
    Also writes sentinel rows for missed / hallucinated drugs so Day 11
    can query "everything that went wrong" in a single pass without
    joining back to eval_results.
    """
    common = {
        "run_id": run_id,
        "patient_id": patient_score.patient_id,
        "evaluated_at": evaluated_at,
        "model": sample_meta["model"],
        "prompt_strategy": sample_meta["prompt_strategy"],
        "prompt_version": sample_meta["prompt_version"],
    }
    for ds in patient_score.drug_scores:
        for fs in ds.field_scores:
            db["eval_field_scores"].update_one(
                {
                    "run_id": run_id,
                    "patient_id": patient_score.patient_id,
                    "farmac": ds.farmac,
                    "field": fs.field,
                },
                {"$set": {**common, "farmac": ds.farmac, "field": fs.field,
                          "score": fs.score, "details": fs.details}},
                upsert=True,
            )
    # Drug-level errors recorded as pseudo-fields (score always 0.0) so the
    # query "give me everything scoring < 1.0 in run X" catches them too.
    for farmac in patient_score.missed_drugs:
        db["eval_field_scores"].update_one(
            {"run_id": run_id, "patient_id": patient_score.patient_id,
             "farmac": farmac, "field": "_missed_drug"},
            {"$set": {**common, "farmac": farmac, "field": "_missed_drug",
                      "score": 0.0, "details": "present in gold, absent in extraction"}},
            upsert=True,
        )
    for farmac in patient_score.hallucinated_drugs:
        db["eval_field_scores"].update_one(
            {"run_id": run_id, "patient_id": patient_score.patient_id,
             "farmac": farmac, "field": "_hallucinated_drug"},
            {"$set": {**common, "farmac": farmac, "field": "_hallucinated_drug",
                      "score": 0.0, "details": "in extraction, not in gold"}},
            upsert=True,
        )


def main(run_id: str | None, limit: int | None) -> int:
    db = get_db()
    run_id = run_id or _latest_run_id(db)
    rows = _load_run_rows(db, run_id)
    if limit is not None:
        rows = rows[:limit]

    # Sample metadata (all rows in a batch share these).
    sample = rows[0]
    print(
        f"run_id={run_id[:8]}...  rows={len(rows)}  "
        f"model={sample['model']}  "
        f"prompt={sample['prompt_strategy']}/{sample['prompt_version']}"
    )

    judge = make_judge()
    print(
        f"judge={judge.judge_model}  "
        f"prompt={JUDGE_PROMPT_STRATEGY}/{JUDGE_PROMPT_VERSION}\n"
    )

    t0 = time.perf_counter()
    evaluated_at = datetime.now(timezone.utc)
    patient_scores: list[PatientScore] = []
    skipped: list[str] = []

    for row in rows:
        pid = row["patient_id"]
        gold = _load_gold(db, pid)
        if gold is None:
            skipped.append(pid)
            continue
        extracted = PatientExtraction.model_validate(row["extraction"])
        ps = score_patient(gold, extracted, judge, run_id=run_id)
        patient_scores.append(ps)

        # Persist per-field rows as we go — Day 11 will drill into these.
        _persist_field_scores(db, run_id, sample, ps, evaluated_at)

        drug_f1 = ps.drug_f1
        field_mean = (
            mean(f.score for ds in ps.drug_scores for f in ds.field_scores)
            if ps.drug_scores else 0.0
        )
        print(
            f"  {pid}  drug-F1={drug_f1:.2f}  field-mean={field_mean:.2f}  "
            f"paired={len(ps.drug_scores)}  "
            f"missed={len(ps.missed_drugs)}  "
            f"hallucinated={len(ps.hallucinated_drugs)}"
        )

    elapsed = time.perf_counter() - t0

    if skipped:
        print(f"\n[warn] skipped {len(skipped)} patient(s) — no gold: {skipped}")

    if not patient_scores:
        print("\nno patients scored — abort")
        return 1

    # --- aggregates ---
    field_means = _aggregate_field_scores(patient_scores)
    drug_p, drug_r, drug_f1 = _aggregate_drug_prf(patient_scores)

    print("\n--- per-field mean (across all matched drug pairs) ---")
    for f in sorted(field_means, key=lambda k: field_means[k]):
        print(f"  {f:<22} {field_means[f]:.3f}")

    overall_field_macro = mean(field_means.values()) if field_means else 0.0
    print(f"\n  {'FIELD macro-mean':<22} {overall_field_macro:.3f}")
    print(f"  {'DRUG precision':<22} {drug_p:.3f}")
    print(f"  {'DRUG recall':<22} {drug_r:.3f}")
    print(f"  {'DRUG F1':<22} {drug_f1:.3f}")
    print(f"\neval elapsed: {elapsed:.1f}s  (mostly judge latency)")

    # --- persist summary ---
    db["eval_results"].update_one(
        {"run_id": run_id},
        {
            "$set": {
                "run_id": run_id,
                "evaluated_at": datetime.now(timezone.utc),
                "model": sample["model"],
                "prompt_strategy": sample["prompt_strategy"],
                "prompt_version": sample["prompt_version"],
                "judge_model": judge.judge_model,
                "judge_strategy": JUDGE_PROMPT_STRATEGY,
                "judge_version": JUDGE_PROMPT_VERSION,
                "n_patients_scored": len(patient_scores),
                "n_patients_skipped": len(skipped),
                "field_means": field_means,
                "drug_precision": drug_p,
                "drug_recall": drug_r,
                "drug_f1": drug_f1,
                "overall_field_macro": overall_field_macro,
                "eval_elapsed_s": elapsed,
            }
        },
        upsert=True,
    )
    print(f"\nstored to eval_results.{run_id}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None,
                        help="Extraction run to evaluate (default: latest).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Score only the first N patients (smoke).")
    args = parser.parse_args()
    sys.exit(main(args.run_id, args.limit))
