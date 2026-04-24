"""Prompt registry for clinical extraction.

One file, one module — the thesis methodology chapter will cite specific
(strategy, version) pairs, so every revision lives here in git.

Currently registered:
    ("zero-shot", "v1")  — baseline rules-only prompt (Days 5–9).
    ("few-shot", "v1")   — same rules + 3 in-context examples loaded from
                           raw_notes + gold_extractions.
    ("cot",       "v1")  — same rules + explicit "raona pas a pas"
                           instruction. Note: when paired with a provider
                           that enforces structured output at the model
                           level (Gemini response_schema, Groq json_schema),
                           the reasoning is NOT emitted — the instruction
                           nudges internal reasoning only. A future
                           variant could relax the output mode to let the
                           model emit reasoning before the JSON.

Placeholder syntax: templates contain the literal strings `{note_ca}` and
`{patient_id}`. Substitution uses `str.replace()` (not `str.format()`)
because few-shot examples embed JSON and JSON contains braces.

Changing a registered prompt = bumping its version. Never mutate in place
once a (strategy, version) has been used in a stored run — the Mongo row
would then claim a prompt version whose text no longer matches what was
sent. Always add ("strategy", "v2") and leave v1 intact for auditability.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Callable

from meditab.mongo import get_db


# --------------------------- shared rule body -----------------------------

# The 9 extraction rules mirror docs/annotation_schema.md. Every variant
# includes these verbatim so prompting differences are only in what comes
# around them (examples, reasoning scaffold), not in the rules themselves.
# This keeps prompt comparisons clean: a difference in extraction quality
# between zero-shot and few-shot can only come from the examples, not from
# drift in what the rules say.
_BASE_RULES = """Regles estrictes:

1. Extreu NOMÉS informació present a la nota. Si un camp no es menciona, posa `null` (o `[]` per a `efectes_adversos`). Si dubtes, prefereix `null` abans que inventar.
2. `farmac`: nom genèric/principi actiu en minúscules (ex: "fluoxetina", "liti"). Normalitza noms comercials al principi actiu.
3. `categoria`: classe terapèutica descriptiva com l'escriuria el clínic (ex: "Antidepressiu (ISRS)", "Estabilitzador d'humor").
4. Dosis SEMPRE en mg/dia:
   - Dosi estable: `dosi_min_mg_dia == dosi_max_mg_dia`.
   - Rang o escalada al llarg del temps: `dosi_min_mg_dia` = mínim, `dosi_max_mg_dia` = màxim assolit.
   - Unitats NO-mg (mg/kg, UI, gotes): deixa totes dues dosis a `null` i omple `dosi_notes` amb el text original.
   - `dosi_notes` ha de ser SEMPRE `null` si la dosi és en mg/dia, inclús si hi ha escalada (això ja es captura amb min/max).
5. Dates en ISO 8601 (YYYY-MM-DD). Si només hi ha mes/any, usa dia 01 i anota la imprecisió a `resposta_clinica`.
6. `is_ongoing`: true si el tractament continua a l'última visita. Si `is_ongoing=true`, `data_fi` i `motiu_discontinuacio` han de ser `null`.
7. `durada_mesos`: enter de mesos entre `data_inici` i `data_fi`. `null` si no tens les dues dates.
8. Un DrugEntry per fàrmac distint: agrega totes les visites del mateix fàrmac a una sola entrada.
9. `efectes_adversos`: llista buida `[]` si no n'hi ha. Mai `null`.
"""

_NOTE_BLOCK = """patient_id: "{patient_id}"

Nota clínica:
---
{note_ca}
---
"""


# ----------------------------- zero-shot v1 -------------------------------

ZERO_SHOT_V1 = f"""Ets un assistent d'extracció d'informació clínica estructurada per a recerca.

Tasca: donada una nota clínica en català (estil "curs clínic" hospitalari), produeix un objecte JSON amb `patient_id` i una llista `drugs[]` que capturi TOTS els fàrmacs esmentats.

{_BASE_RULES}
{_NOTE_BLOCK}"""


# -------------------------------- CoT v1 ----------------------------------

COT_V1 = f"""Ets un assistent d'extracció d'informació clínica estructurada per a recerca.

Tasca: donada una nota clínica en català (estil "curs clínic" hospitalari), produeix un objecte JSON amb `patient_id` i una llista `drugs[]` que capturi TOTS els fàrmacs esmentats.

{_BASE_RULES}
Abans d'emetre el JSON, raona pas a pas mentalment:
  (a) identifica tots els fàrmacs esmentats a la nota, incloent-hi noms comercials;
  (b) per a cada fàrmac, localitza les dates, dosis (i escalades), efectes adversos i motiu de discontinuació si existeix;
  (c) consolida varies visites del mateix fàrmac en una única entrada `DrugEntry`;
  (d) comprova que cada camp compleix les Regles 1-9.
Només després d'aquest raonament, emet el JSON.

{_NOTE_BLOCK}"""


# ----------------------------- few-shot v1 --------------------------------

# Which patients are used as few-shot examples. These are "held out" of any
# eval set — same IDs chosen in the eval plan's few-shot pool. Covers three
# distinct shapes: simple mono (001), multi-drug (003), AE-heavy discontin-
# uation (007). Change this tuple = new prompt version.
_FEW_SHOT_V1_EXAMPLE_IDS: tuple[str, ...] = (
    "synthetic_001",
    "synthetic_003",
    "synthetic_007",
)

_FEW_SHOT_V1_TEMPLATE = f"""Ets un assistent d'extracció d'informació clínica estructurada per a recerca.

Tasca: donada una nota clínica en català (estil "curs clínic" hospitalari), produeix un objecte JSON amb `patient_id` i una llista `drugs[]` que capturi TOTS els fàrmacs esmentats.

{_BASE_RULES}
Aquí tens alguns exemples de referència (nota + JSON esperat). Aplica el mateix format a la nota nova.

__EXAMPLES__

Ara aplica el mateix format a la següent nota:

{_NOTE_BLOCK}"""


def _render_example(i: int, pid: str, note_ca: str, gold: dict) -> str:
    gold_json = json.dumps(gold, ensure_ascii=False, indent=2, default=str)
    return (
        f"### Exemple {i} — patient_id: {pid}\n\n"
        f"Nota:\n---\n{note_ca}\n---\n\n"
        f"JSON esperat:\n{gold_json}\n"
    )


@lru_cache(maxsize=1)
def _few_shot_v1_prompt() -> str:
    """Load the 3 example patients from Mongo and inline them into the template.

    Cached: the examples don't change between calls within a process, and
    Mongo round-trips would otherwise happen once per extraction. Cache is
    process-local, so a new run_id always re-reads from Mongo at first use.
    """
    db = get_db()
    pieces: list[str] = []
    for i, pid in enumerate(_FEW_SHOT_V1_EXAMPLE_IDS, 1):
        note_doc = db.raw_notes.find_one({"_id": pid})
        gold_doc = db.gold_extractions.find_one({"_id": pid})
        if note_doc is None or gold_doc is None:
            raise RuntimeError(
                f"few-shot example {pid!r} not in Mongo — run Day 6 ingest first"
            )
        for f in ("_id", "source_path", "ingested_at"):
            gold_doc.pop(f, None)
        pieces.append(_render_example(i, pid, note_doc["text_ca"], gold_doc))
    examples_block = "\n".join(pieces)
    # Use replace(), not format(), because examples contain literal braces.
    return _FEW_SHOT_V1_TEMPLATE.replace("__EXAMPLES__", examples_block)


# ------------------------------- registry ---------------------------------

# Every entry is a zero-arg callable returning the fully-assembled template
# (with {note_ca} / {patient_id} placeholders still unfilled). Simple
# variants are lambdas; dynamic ones are named functions with caching.
PROMPTS: dict[tuple[str, str], Callable[[], str]] = {
    ("zero-shot", "v1"): lambda: ZERO_SHOT_V1,
    ("cot", "v1"): lambda: COT_V1,
    ("few-shot", "v1"): _few_shot_v1_prompt,
}


def get_prompt(strategy: str, version: str) -> str:
    """Return the prompt template with {note_ca} and {patient_id} placeholders.

    Callers should substitute with `str.replace()` (not `.format()`),
    because few-shot examples embed JSON that contains literal braces.
    """
    try:
        builder = PROMPTS[(strategy, version)]
    except KeyError:
        available = sorted(PROMPTS)
        raise ValueError(
            f"unknown (strategy, version) = ({strategy!r}, {version!r}); "
            f"registered: {available}"
        ) from None
    return builder()


def render_prompt(
    strategy: str, version: str, *, note_ca: str, patient_id: str
) -> str:
    """Return the fully-rendered prompt ready to send to an LLM."""
    return (
        get_prompt(strategy, version)
        .replace("{note_ca}", note_ca)
        .replace("{patient_id}", patient_id)
    )


# ----------------------------- judge prompts ------------------------------

# LLM-as-judge prompt. Used by `meditab.judge` to compare gold text to
# extracted text for free-text fields (resposta_clinica, motiu_discontinuacio).
# The judge is deliberately conservative: "partial" exists so minor
# differences in scope (gold mentions AE, extracted doesn't) register as a
# warning rather than a binary fail.
JUDGE_CLINICAL_V1 = """Ets un revisor clínic expert. La teva tasca és decidir si dos textos descriuen la mateixa informació clínica per al camp {field_name}.

Text de referència (gold, escrit per un clínic):
---
{gold_text}
---

Text extret automàticament per un LLM:
---
{extracted_text}
---

Criteris:
- "yes" — tots dos textos comuniquen la mateixa informació clínica essencial. Parafrasejar, ampliar amb detalls coherents o resumir NO compta com a error.
- "partial" — coincideixen en la idea principal però un dels dos omet o afegeix informació clínicament rellevant (ex: el gold menciona un efecte advers que l'extret no).
- "no" — descriuen situacions clíniques diferents o una de les dues no s'ajusta al camp {field_name}.

Respon ÚNICAMENT amb un JSON d'aquesta forma:
{"verdict": "yes | partial | no", "rationale": "una frase curta en català explicant per què"}"""


JUDGE_PROMPTS: dict[tuple[str, str], str] = {
    ("judge-clinical", "v1"): JUDGE_CLINICAL_V1,
}


def render_judge_prompt(
    field_name: str,
    gold_text: str,
    extracted_text: str,
    *,
    strategy: str = "judge-clinical",
    version: str = "v1",
) -> str:
    """Return the fully-rendered judge prompt."""
    try:
        template = JUDGE_PROMPTS[(strategy, version)]
    except KeyError:
        available = sorted(JUDGE_PROMPTS)
        raise ValueError(
            f"unknown judge (strategy, version) = ({strategy!r}, {version!r}); "
            f"registered: {available}"
        ) from None
    return (
        template
        .replace("{field_name}", field_name)
        .replace("{gold_text}", gold_text)
        .replace("{extracted_text}", extracted_text)
    )
