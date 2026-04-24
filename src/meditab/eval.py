"""Per-field scoring for clinical extractions against gold.

Policy (locked in 2026-04-23, see HANDOFF decision log):
    farmac                  exact (schema-normalized)
    categoria               token-F1 on normalized strings
    dosi_min/max_mg_dia     numeric equality ± 1 mg
    dosi_notes              exact if either null; token-F1 otherwise
    data_inici / data_fi    exact
    is_ongoing              exact
    durada_mesos            equal ± 1 month
    resposta_clinica        LLM-as-judge
    motiu_discontinuacio    LLM-as-judge
    efectes_adversos        count match + concatenated descripcio token-F1
                            (per-AE matching deferred to eval v2)

Drug-level matching: pair gold ↔ extracted by `farmac` exact match.
Unmatched on either side counts as missed/hallucinated at the patient level.

All comparators return a float in [0.0, 1.0]. 1.0 = full match, 0.0 = miss.

This module has NO network calls. The judge is passed in as a dependency so
eval is unit-testable with a fake. `scripts/evaluate.py` wires in the
real `Judge` from `meditab.judge`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from meditab.schema import DrugEntry, PatientExtraction


# ---------------------------- comparator judge ----------------------------


class JudgeProtocol(Protocol):
    """Minimal surface the eval expects from a judge — one method. Lets us
    unit-test eval with a fake that returns scripted verdicts."""

    def judge_equivalence(
        self,
        field_name: str,
        gold_text: str,
        extracted_text: str,
        *,
        patient_id: str,
        run_id: str,
    ) -> float:
        """Return a score in [0.0, 1.0]. 1.0 = same clinical meaning,
        0.5 = partial, 0.0 = not equivalent."""
        ...


# ------------------------------ data shapes -------------------------------


@dataclass
class FieldScore:
    field: str
    score: float          # 0.0 - 1.0
    details: str          # human-readable (for error analysis)


@dataclass
class DrugScore:
    farmac: str
    field_scores: list[FieldScore] = field(default_factory=list)

    @property
    def mean(self) -> float:
        if not self.field_scores:
            return 0.0
        return sum(f.score for f in self.field_scores) / len(self.field_scores)


@dataclass
class PatientScore:
    patient_id: str
    drug_scores: list[DrugScore] = field(default_factory=list)
    missed_drugs: list[str] = field(default_factory=list)         # gold only
    hallucinated_drugs: list[str] = field(default_factory=list)   # extracted only

    @property
    def drug_precision(self) -> float:
        total_extracted = len(self.drug_scores) + len(self.hallucinated_drugs)
        return (
            len(self.drug_scores) / total_extracted
            if total_extracted
            else 0.0
        )

    @property
    def drug_recall(self) -> float:
        total_gold = len(self.drug_scores) + len(self.missed_drugs)
        return len(self.drug_scores) / total_gold if total_gold else 0.0

    @property
    def drug_f1(self) -> float:
        p, r = self.drug_precision, self.drug_recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


# ---------------------------- primitive scorers ---------------------------


_NON_ALNUM = re.compile(r"[^\w\s]", flags=re.UNICODE)


def _normalize_tokens(s: str | None) -> set[str]:
    if not s:
        return set()
    s = s.lower()
    s = _NON_ALNUM.sub(" ", s)
    return {tok for tok in s.split() if tok}


def score_token_f1(gold: str | None, extracted: str | None) -> float:
    """Token-level F1 after normalization. Returns 1.0 if both are empty/None,
    0.0 if one is empty and the other isn't."""
    g, e = _normalize_tokens(gold), _normalize_tokens(extracted)
    if not g and not e:
        return 1.0
    if not g or not e:
        return 0.0
    shared = g & e
    if not shared:
        return 0.0
    p = len(shared) / len(e)
    r = len(shared) / len(g)
    return 2 * p * r / (p + r)


def score_exact(gold, extracted) -> float:
    return 1.0 if gold == extracted else 0.0


def score_numeric_tol(
    gold: float | None, extracted: float | None, tol: float
) -> float:
    """Equality within `tol`. Both None = 1.0; one None = 0.0."""
    if gold is None and extracted is None:
        return 1.0
    if gold is None or extracted is None:
        return 0.0
    return 1.0 if abs(gold - extracted) <= tol else 0.0


def score_date(gold: date | None, extracted: date | None) -> float:
    return score_exact(gold, extracted)


# ---------------------------- per-field wrappers --------------------------


def score_farmac(g: DrugEntry, e: DrugEntry) -> FieldScore:
    # By construction farmac matches (we already used it to pair). Record
    # for completeness so the per-drug average reflects it.
    return FieldScore("farmac", 1.0, "paired on exact match")


def score_categoria(g: DrugEntry, e: DrugEntry) -> FieldScore:
    s = score_token_f1(g.categoria, e.categoria)
    return FieldScore(
        "categoria", s, f"token-F1({g.categoria!r}, {e.categoria!r})"
    )


def score_dose_min(g: DrugEntry, e: DrugEntry) -> FieldScore:
    s = score_numeric_tol(g.dosi_min_mg_dia, e.dosi_min_mg_dia, tol=1.0)
    return FieldScore(
        "dosi_min_mg_dia", s,
        f"|{g.dosi_min_mg_dia} - {e.dosi_min_mg_dia}| <= 1.0",
    )


def score_dose_max(g: DrugEntry, e: DrugEntry) -> FieldScore:
    s = score_numeric_tol(g.dosi_max_mg_dia, e.dosi_max_mg_dia, tol=1.0)
    return FieldScore(
        "dosi_max_mg_dia", s,
        f"|{g.dosi_max_mg_dia} - {e.dosi_max_mg_dia}| <= 1.0",
    )


def score_dose_notes(g: DrugEntry, e: DrugEntry) -> FieldScore:
    # Special: exact on null-handling, token-F1 only when both are strings.
    if g.dosi_notes is None and e.dosi_notes is None:
        return FieldScore("dosi_notes", 1.0, "both null")
    if g.dosi_notes is None or e.dosi_notes is None:
        return FieldScore(
            "dosi_notes", 0.0,
            f"null mismatch: gold={g.dosi_notes!r}, ext={e.dosi_notes!r}",
        )
    s = score_token_f1(g.dosi_notes, e.dosi_notes)
    return FieldScore("dosi_notes", s, "token-F1 on non-null strings")


def score_data_inici(g: DrugEntry, e: DrugEntry) -> FieldScore:
    s = score_date(g.data_inici, e.data_inici)
    return FieldScore("data_inici", s, f"{g.data_inici} vs {e.data_inici}")


def score_data_fi(g: DrugEntry, e: DrugEntry) -> FieldScore:
    s = score_date(g.data_fi, e.data_fi)
    return FieldScore("data_fi", s, f"{g.data_fi} vs {e.data_fi}")


def score_is_ongoing(g: DrugEntry, e: DrugEntry) -> FieldScore:
    s = score_exact(g.is_ongoing, e.is_ongoing)
    return FieldScore("is_ongoing", s, f"{g.is_ongoing} vs {e.is_ongoing}")


def score_durada(g: DrugEntry, e: DrugEntry) -> FieldScore:
    s = score_numeric_tol(
        None if g.durada_mesos is None else float(g.durada_mesos),
        None if e.durada_mesos is None else float(e.durada_mesos),
        tol=1.0,
    )
    return FieldScore(
        "durada_mesos", s,
        f"|{g.durada_mesos} - {e.durada_mesos}| <= 1 month",
    )


def score_resposta_clinica(
    g: DrugEntry,
    e: DrugEntry,
    judge: JudgeProtocol,
    *,
    patient_id: str,
    run_id: str,
) -> FieldScore:
    # If both are empty/None, judge doesn't need to be called.
    if not g.resposta_clinica and not e.resposta_clinica:
        return FieldScore("resposta_clinica", 1.0, "both empty")
    if not g.resposta_clinica or not e.resposta_clinica:
        return FieldScore(
            "resposta_clinica", 0.0,
            f"null mismatch: gold={g.resposta_clinica!r}, "
            f"ext={e.resposta_clinica!r}",
        )
    s = judge.judge_equivalence(
        "resposta_clinica",
        g.resposta_clinica,
        e.resposta_clinica,
        patient_id=patient_id,
        run_id=run_id,
    )
    return FieldScore(
        "resposta_clinica", s,
        f"LLM-judge: {g.resposta_clinica!r} vs {e.resposta_clinica!r}",
    )


def score_motiu(
    g: DrugEntry,
    e: DrugEntry,
    judge: JudgeProtocol,
    *,
    patient_id: str,
    run_id: str,
) -> FieldScore:
    if g.motiu_discontinuacio is None and e.motiu_discontinuacio is None:
        return FieldScore("motiu_discontinuacio", 1.0, "both null")
    if g.motiu_discontinuacio is None or e.motiu_discontinuacio is None:
        return FieldScore(
            "motiu_discontinuacio", 0.0,
            f"null mismatch: gold={g.motiu_discontinuacio!r}, "
            f"ext={e.motiu_discontinuacio!r}",
        )
    s = judge.judge_equivalence(
        "motiu_discontinuacio",
        g.motiu_discontinuacio,
        e.motiu_discontinuacio,
        patient_id=patient_id,
        run_id=run_id,
    )
    return FieldScore(
        "motiu_discontinuacio", s, "LLM-judge on non-null strings"
    )


def score_efectes_adversos(g: DrugEntry, e: DrugEntry) -> FieldScore:
    """v1: combine count-match + concatenated descripcio token-F1.

    count_match = 1.0 if len(gold) == len(extracted), else 0.0
    desc_f1     = token-F1 on ' '.join(sorted(descripcio for ae in ...))
    score       = mean(count_match, desc_f1)

    This is coarse. v2 would pair AEs individually and score `persistent` +
    `severitat` per pair. Deferred because per-AE matching is a chunk of
    work and the synthetic set has small AE counts where coarse scoring
    is still informative.
    """
    g_count, e_count = len(g.efectes_adversos), len(e.efectes_adversos)
    count_match = 1.0 if g_count == e_count else 0.0
    g_desc = " ".join(sorted(ae.descripcio for ae in g.efectes_adversos))
    e_desc = " ".join(sorted(ae.descripcio for ae in e.efectes_adversos))
    desc_f1 = score_token_f1(g_desc, e_desc) if (g_desc or e_desc) else 1.0
    score = (count_match + desc_f1) / 2
    return FieldScore(
        "efectes_adversos", score,
        f"count {e_count}/{g_count} (match={count_match}); "
        f"desc token-F1={desc_f1:.2f}",
    )


# ------------------------------ drug pairing ------------------------------


def _score_drug_pair(
    g: DrugEntry,
    e: DrugEntry,
    judge: JudgeProtocol,
    *,
    patient_id: str,
    run_id: str,
) -> DrugScore:
    scorers_simple = [
        score_farmac, score_categoria,
        score_dose_min, score_dose_max, score_dose_notes,
        score_data_inici, score_data_fi,
        score_is_ongoing, score_durada,
        score_efectes_adversos,
    ]
    ds = DrugScore(farmac=g.farmac)
    for fn in scorers_simple:
        ds.field_scores.append(fn(g, e))
    ds.field_scores.append(
        score_resposta_clinica(g, e, judge, patient_id=patient_id, run_id=run_id)
    )
    ds.field_scores.append(
        score_motiu(g, e, judge, patient_id=patient_id, run_id=run_id)
    )
    return ds


def score_patient(
    gold: PatientExtraction,
    extracted: PatientExtraction,
    judge: JudgeProtocol,
    *,
    run_id: str,
) -> PatientScore:
    g_by = {d.farmac: d for d in gold.drugs}
    e_by = {d.farmac: d for d in extracted.drugs}
    shared = sorted(set(g_by) & set(e_by))
    ps = PatientScore(
        patient_id=gold.patient_id,
        missed_drugs=sorted(set(g_by) - set(e_by)),
        hallucinated_drugs=sorted(set(e_by) - set(g_by)),
    )
    for farmac in shared:
        ps.drug_scores.append(
            _score_drug_pair(
                g_by[farmac], e_by[farmac], judge,
                patient_id=gold.patient_id, run_id=run_id,
            )
        )
    return ps
