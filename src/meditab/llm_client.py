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

from openai import OpenAI
from .schema import PatientExtraction
from .prompts import render_prompt

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


class OllamaExtractor:
    """Local Ollama extractor via OpenAI-compatible API. No data leaves the host.
    
    Default model: gemma3:4b. Override via OLLAMA_MODEL env var.
    Endpoint defaults to http://localhost:11434/v1; override via OLLAMA_BASE_URL.
    """
    def __init__(self) -> None:
        self.model_id = os.getenv("OLLAMA_MODEL", "gemma3:4b")    # ← model_id, no model
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self._client = OpenAI(base_url=base_url, api_key="ollama")

    def extract(
        self,
        note_ca: str,
        patient_id: str,
        *,
        strategy: str = "zero-shot",
        version: str = "v1",
    ) -> PatientExtraction:
        prompt = render_prompt(strategy, version, note_ca=note_ca, patient_id=patient_id)

        resp = self._client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": "You are a clinical information extractor. Reply ONLY with valid JSON matching the schema."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = resp.choices[0].message.content
        return PatientExtraction.model_validate_json(raw)


# -------------------------------- factory ---------------------------------


def make_extractor() -> LLMClient:
    """Pick an LLMClient based on MEDITAB_LLM_PROVIDER env var.

    - "gemini"  (default, laptop dev, 20 req/day free tier): `GeminiExtractor`
    - "groq"    (laptop dev, faster + looser quota):         `GroqExtractor`
    - "bedrock" (hospital):        Week 3 will land `BedrockExtractor`.
    """
    provider = os.getenv("MEDITAB_LLM_PROVIDER", "ollama").lower()
    if provider == "ollama":            # ← nueva línea
        return OllamaExtractor()
    if provider == "bedrock":
        raise NotImplementedError(
            "BedrockExtractor lands in Week 3 at the hospital"
        )
    raise ValueError(f"unknown MEDITAB_LLM_PROVIDER={provider!r}")
