"""Prompt registry for clinical extraction.

One file, one module — the thesis methodology chapter will cite specific
(strategy, version) pairs, so every revision lives here in git.

Currently registered:
    ("zero-shot", "v1")  — baseline rules-only prompt (Days 5–9).
    ("few-shot", "v1")   — same rules + ONE inlined synthetic example
                           covering the rule edge cases the model most
                           often gets wrong (dose escalation, brand→generic,
                           AE persistence, is_ongoing invariants).
                           Inlined (not Mongo-loaded) so the example is
                           version-controlled and the thesis can cite it
                           verbatim without a DB dump.
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

from typing import Callable


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

# Single inlined synthetic example. NOT a real patient — fully fabricated.
# Designed to exercise the rules the model most frequently violates:
#   - Rule 2 (brand→generic):     "Prozac" → "fluoxetina"
#   - Rule 4 (dose escalation):   20 → 40 mg/dia captured as min/max
#   - Rule 5 (ISO dates):         all YYYY-MM-DD
#   - Rule 6 (is_ongoing=true):   data_fi/motiu/durada all null
#   - Rule 7 (durada_mesos):      computed when both dates present, null otherwise
#   - Rule 9 + AE schema:         structured AdverseEffect objects with persistent + severitat
#   - resposta_clinica:           real summary, not "bona"
#   - motiu_discontinuacio:       non-AE reason (patient preference)
#
# Inlined rather than Mongo-loaded so:
#   1. The exact prompt text is version-controlled.
#   2. The thesis methodology chapter can quote it directly.
#   3. No DB round-trip or cache-staleness class of bug.
_FEW_SHOT_V1_EXAMPLE = """### Exemple — patient_id: example_01

Nota:
---
Curs clínic — pacient dona de 47 anys. Antecedents: trastorn d'ansietat generalitzada, sense al·lèrgies medicamentoses conegudes.

Visita 12/02/2024: clínica ansiosa-depressiva moderada de 6 mesos d'evolució amb hipovitalitat, anhedonia i insomni de manteniment. S'inicia Prozac 20 mg/dia. S'adverteix la pacient sobre possibles efectes adversos gastrointestinals durant les primeres setmanes.

Visita 14/03/2024: refereix nàusees lleus durant la primera setmana, ja resoltes (no persistents). Resposta inicial parcial. Es decideix escalar Prozac a 40 mg/dia.

Visita 25/04/2024: millora clara de l'estat d'ànim i del son. Es manté Prozac 40 mg/dia. Sense nous efectes adversos.

Visita 10/06/2024: persisteix component ansiós residual amb dificultat per conciliar el son. S'afegeix Lormetazepam 1 mg/nit.

Visita 22/07/2024: bona resposta combinada. La pacient refereix sequedat de boca persistent atribuïble al Lormetazepam, lleu i tolerada. Es manté pauta.

Visita 15/09/2024: Lormetazepam suspès per voluntat de la pacient (preferia evitar tractament hipnòtic crònic) — resolució completa de la sequedat de boca als 7 dies. Es manté Prozac 40 mg/dia amb estabilitat clínica. Tractament en curs.
---

JSON esperat:
{
  "patient_id": "example_01",
  "drugs": [
    {
      "farmac": "fluoxetina",
      "categoria": "Antidepressiu (ISRS)",
      "dosi_min_mg_dia": 20.0,
      "dosi_max_mg_dia": 40.0,
      "dosi_notes": null,
      "data_inici": "2024-02-12",
      "data_fi": null,
      "is_ongoing": true,
      "durada_mesos": null,
      "resposta_clinica": "Resposta inicial parcial al març amb millora clara de l'estat d'ànim i del son a partir d'abril. Estabilitat clínica mantinguda al setembre amb 40 mg/dia.",
      "efectes_adversos": [
        {
          "descripcio": "nàusees",
          "persistent": "no persistent",
          "severitat": "lleu"
        }
      ],
      "motiu_discontinuacio": null
    },
    {
      "farmac": "lormetazepam",
      "categoria": "Hipnòtic (benzodiazepina)",
      "dosi_min_mg_dia": 1.0,
      "dosi_max_mg_dia": 1.0,
      "dosi_notes": null,
      "data_inici": "2024-06-10",
      "data_fi": "2024-09-15",
      "is_ongoing": false,
      "durada_mesos": 3,
      "resposta_clinica": "Millora del component ansiós residual i del son en associació amb fluoxetina. Tolerància general bona durant els tres mesos.",
      "efectes_adversos": [
        {
          "descripcio": "sequedat de boca",
          "persistent": "persistent",
          "severitat": "lleu"
        }
      ],
      "motiu_discontinuacio": "voluntat de la pacient (evitar tractament hipnòtic crònic)"
    }
  ]
}
"""

FEW_SHOT_V1 = f"""Ets un assistent d'extracció d'informació clínica estructurada per a recerca.

Tasca: donada una nota clínica en català (estil "curs clínic" hospitalari), produeix un objecte JSON amb `patient_id` i una llista `drugs[]` que capturi TOTS els fàrmacs esmentats.

{_BASE_RULES}
Aquí tens un exemple de referència (nota + JSON esperat). Aplica el mateix format a la nota nova.

{_FEW_SHOT_V1_EXAMPLE}

Ara aplica el mateix format a la següent nota:

{_NOTE_BLOCK}"""


# ------------------------------- registry ---------------------------------

# Every entry is a zero-arg callable returning the fully-assembled template
# (with {note_ca} / {patient_id} placeholders still unfilled). Simple
# variants are lambdas; dynamic ones are named functions with caching.
PROMPTS: dict[tuple[str, str], Callable[[], str]] = {
    ("zero-shot", "v1"): lambda: ZERO_SHOT_V1,
    ("cot", "v1"): lambda: COT_V1,
    ("few-shot", "v1"): lambda: FEW_SHOT_V1,
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
