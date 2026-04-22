"""LLM adapter for structured clinical extraction.

The Protocol below is the swap point for the hospital machine: replace
`GeminiExtractor` with a `BedrockExtractor` (Claude Haiku / Llama / Mistral /
Nova) and nothing downstream changes — ingestion, MCP, eval all depend on
the interface, not the vendor.

Run anything that calls this with GEMINI_API_KEY set (from .env).
"""

from __future__ import annotations

import os
from typing import Protocol

from google import genai
from google.genai import types

from meditab.schema import PatientExtraction


# ------------------------------- interface --------------------------------


class LLMClient(Protocol):
    """One method: extract a PatientExtraction from a Catalan clinical note."""

    def extract(self, note_ca: str, patient_id: str) -> PatientExtraction: ...


# --------------------------------- prompt ---------------------------------

# Zero-shot extraction prompt. Catalan to match the note language (empirically
# improves terminology accuracy). Rules mirror docs/annotation_schema.md.
EXTRACTION_PROMPT = """Ets un assistent d'extracció d'informació clínica estructurada per a recerca.

Tasca: donada una nota clínica en català (estil "curs clínic" hospitalari), produeix un objecte JSON amb `patient_id` i una llista `drugs[]` que capturi TOTS els fàrmacs esmentats.

Regles estrictes:

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

patient_id: "{patient_id}"

Nota clínica:
---
{note_ca}
---
"""


# ----------------------------- Gemini adapter -----------------------------

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiExtractor:
    """LLMClient implementation backed by Google Gemini (dev/free tier)."""

    def __init__(self, model: str = DEFAULT_MODEL, temperature: float = 0.1) -> None:
        self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self._model = model
        self._temperature = temperature

    def extract(self, note_ca: str, patient_id: str) -> PatientExtraction:
        response = self._client.models.generate_content(
            model=self._model,
            contents=EXTRACTION_PROMPT.format(note_ca=note_ca, patient_id=patient_id),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PatientExtraction,
                temperature=self._temperature,
            ),
        )
        result: PatientExtraction = response.parsed
        # Overwrite in case the LLM hallucinated a different id — we know the truth.
        result.patient_id = patient_id
        return result
