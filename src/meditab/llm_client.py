"""LLM adapter for structured clinical extraction.

The `LLMClient` Protocol is the swap point for the hospital machine: add a
`BedrockExtractor` alongside `GeminiExtractor` and `make_extractor()` will
pick one based on `MEDITAB_LLM_PROVIDER`. Nothing downstream (ingestion,
MCP, eval) depends on the vendor.

Prompts live in the `PROMPTS` registry keyed on (strategy, version). Week 4
adds few-shot / CoT entries by appending to the dict.

Run anything that calls this with GEMINI_API_KEY set (from .env).
"""

from __future__ import annotations

import os
import time
from typing import Protocol

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from meditab.schema import PatientExtraction


# Transient Gemini errors that are worth retrying. 503 is quota / high demand,
# 429 is rate limit, 500 is internal error. Permanent errors (400 bad request,
# 401 auth, 404 model-not-found) must not retry — they won't resolve by waiting.
_RETRYABLE_STATUS = {429, 500, 503}
_MAX_RETRIES = 3
_BASE_BACKOFF_S = 5.0


# -------------------------------- prompts ---------------------------------

# Zero-shot Catalan extraction prompt. Rules mirror docs/annotation_schema.md.
ZERO_SHOT_V1 = """Ets un assistent d'extracció d'informació clínica estructurada per a recerca.

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


# Registry keyed on (strategy, version). Week 4 adds few-shot / CoT variants
# by appending entries here — no extractor changes needed.
PROMPTS: dict[tuple[str, str], str] = {
    ("zero-shot", "v1"): ZERO_SHOT_V1,
}


def get_prompt(strategy: str, version: str) -> str:
    try:
        return PROMPTS[(strategy, version)]
    except KeyError:
        available = sorted(PROMPTS)
        raise ValueError(
            f"unknown (strategy, version) = ({strategy!r}, {version!r}); "
            f"registered: {available}"
        ) from None


# ------------------------------- interface --------------------------------


class LLMClient(Protocol):
    """One method: extract a PatientExtraction from a Catalan clinical note."""

    model_id: str

    def extract(
        self,
        note_ca: str,
        patient_id: str,
        strategy: str,
        version: str,
    ) -> PatientExtraction: ...


# ----------------------------- Gemini adapter -----------------------------

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiExtractor:
    """LLMClient implementation backed by Google Gemini (dev/free tier)."""

    def __init__(self, model: str = DEFAULT_MODEL, temperature: float = 0.1) -> None:
        self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.model_id = model
        self._temperature = temperature

    def extract(
        self,
        note_ca: str,
        patient_id: str,
        strategy: str,
        version: str,
    ) -> PatientExtraction:
        prompt = get_prompt(strategy, version).format(
            note_ca=note_ca, patient_id=patient_id
        )
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PatientExtraction,
            temperature=self._temperature,
        )

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=config,
                )
                break
            except genai_errors.APIError as exc:
                status = getattr(exc, "code", None)
                if status not in _RETRYABLE_STATUS or attempt == _MAX_RETRIES:
                    raise
                backoff = _BASE_BACKOFF_S * attempt
                print(
                    f"  gemini {status} — retry {attempt}/{_MAX_RETRIES - 1} "
                    f"in {backoff:.0f}s"
                )
                time.sleep(backoff)

        result: PatientExtraction = response.parsed
        # Overwrite in case the LLM hallucinated a different id — we know the truth.
        result.patient_id = patient_id
        return result


# -------------------------------- factory ---------------------------------


def make_extractor() -> LLMClient:
    """Pick an LLMClient based on MEDITAB_LLM_PROVIDER env var.

    - "gemini" (default, laptop dev): `GeminiExtractor`.
    - "bedrock" (hospital): Week 3 will land `BedrockExtractor`.
    """
    provider = os.getenv("MEDITAB_LLM_PROVIDER", "gemini")
    if provider == "gemini":
        return GeminiExtractor()
    if provider == "bedrock":
        raise NotImplementedError(
            "BedrockExtractor lands in Week 3 at the hospital"
        )
    raise ValueError(f"unknown MEDITAB_LLM_PROVIDER={provider!r}")
