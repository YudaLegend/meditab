"""LLM adapters for structured clinical extraction.

The `LLMClient` Protocol is the swap point: add a new extractor class,
register it in `make_extractor()`, and nothing downstream (ingestion,
MCP, eval, batch) notices. Scripts pick a provider via the env var
`MEDITAB_LLM_PROVIDER` (see `make_extractor`).

Providers:
    gemini  — Google Gemini 2.5 Flash (free tier, 20 req/day daily quota).
    groq    — Groq cloud (Llama 4 Scout default; faster, much looser quota).
    bedrock — Hospital only; lands Week 3.

Prompts live in `meditab.prompts`. This module only cares about transport.
"""

from __future__ import annotations

import json
import os
import time
from typing import Protocol

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from groq import APIStatusError, Groq

from meditab.prompts import render_prompt
from meditab.schema import PatientExtraction


# Status codes worth retrying across providers. 503 is "high demand",
# 429 is rate limit, 500 is internal error. Permanent errors (400 bad
# request, 401 auth, 404 model-not-found) must NOT retry — they won't
# resolve by waiting.
_RETRYABLE_STATUS = {429, 500, 503}
_MAX_RETRIES = 3
_BASE_BACKOFF_S = 5.0


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

GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiExtractor:
    """LLMClient backed by Google Gemini. Uses native response_schema for
    server-side schema enforcement — model output is already validated
    against PatientExtraction before parse."""

    def __init__(
        self, model: str | None = None, temperature: float = 0.1
    ) -> None:
        self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.model_id = model or os.getenv("GEMINI_MODEL", GEMINI_DEFAULT_MODEL)
        self._temperature = temperature

    def extract(
        self,
        note_ca: str,
        patient_id: str,
        strategy: str,
        version: str,
    ) -> PatientExtraction:
        prompt = render_prompt(
            strategy, version, note_ca=note_ca, patient_id=patient_id
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
        result.patient_id = patient_id  # trust our id, not the LLM's
        return result


# ------------------------------ Groq adapter ------------------------------

# Llama 4 Scout on Groq's free tier — very fast, generous quota. Default
# picked because (a) strong instruction-following on multilingual inputs,
# (b) reliably produces JSON when nudged by response_format + prompt, and
# (c) no daily cap like Gemini free tier.
GROQ_DEFAULT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


class GroqExtractor:
    """LLMClient backed by Groq (OpenAI-compatible). Uses JSON-object mode
    + client-side Pydantic validation (not server-enforced schema).

    Schema is injected into the system message so the model knows the
    exact shape, then `response_format={"type": "json_object"}` forces a
    JSON string. We validate with PatientExtraction after parse — same
    contract as GeminiExtractor's output, different mechanism.
    """

    def __init__(
        self, model: str | None = None, temperature: float = 0.1
    ) -> None:
        self._client = Groq(api_key=os.environ["GROQ_API_KEY"])
        self.model_id = model or os.getenv("GROQ_MODEL", GROQ_DEFAULT_MODEL)
        self._temperature = temperature
        self._schema_json = json.dumps(
            PatientExtraction.model_json_schema(), ensure_ascii=False
        )

    def extract(
        self,
        note_ca: str,
        patient_id: str,
        strategy: str,
        version: str,
    ) -> PatientExtraction:
        prompt = render_prompt(
            strategy, version, note_ca=note_ca, patient_id=patient_id
        )
        # The system message tells Groq: respond with JSON matching this
        # schema. The user message carries the rendered Catalan prompt.
        # Schema injection compensates for Groq's json_object mode not
        # enforcing a schema server-side.
        system_msg = (
            "Ets un assistent d'extracció clínica. Respon ÚNICAMENT amb un "
            "objecte JSON vàlid que compleixi aquest esquema JSON Schema:\n\n"
            f"{self._schema_json}\n\n"
            "No afegeixis text fora del JSON."
        )

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model_id,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=self._temperature,
                )
                break
            except APIStatusError as exc:
                status = getattr(exc, "status_code", None)
                if status not in _RETRYABLE_STATUS or attempt == _MAX_RETRIES:
                    raise
                backoff = _BASE_BACKOFF_S * attempt
                print(
                    f"  groq {status} — retry {attempt}/{_MAX_RETRIES - 1} "
                    f"in {backoff:.0f}s"
                )
                time.sleep(backoff)

        raw_json = response.choices[0].message.content
        result = PatientExtraction.model_validate_json(raw_json)
        result.patient_id = patient_id  # trust our id, not the LLM's
        return result


# -------------------------------- factory ---------------------------------


def make_extractor() -> LLMClient:
    """Pick an LLMClient based on MEDITAB_LLM_PROVIDER env var.

    - "gemini"  (default, laptop dev, 20 req/day free tier): `GeminiExtractor`
    - "groq"    (laptop dev, faster + looser quota):         `GroqExtractor`
    - "bedrock" (hospital):        Week 3 will land `BedrockExtractor`.
    """
    provider = os.getenv("MEDITAB_LLM_PROVIDER", "gemini")
    if provider == "gemini":
        return GeminiExtractor()
    if provider == "groq":
        return GroqExtractor()
    if provider == "bedrock":
        raise NotImplementedError(
            "BedrockExtractor lands in Week 3 at the hospital"
        )
    raise ValueError(f"unknown MEDITAB_LLM_PROVIDER={provider!r}")
