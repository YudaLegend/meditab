"""LLM-as-judge for free-text field equivalence.

Used by `meditab.eval` to score `resposta_clinica` and `motiu_discontinuacio`
— fields where gold is often terse ("bona") and extractor output is often
verbose ("Millora significativa..."), so exact/token-overlap fails even when
the clinical meaning is identical.

Every verdict is persisted to the `llm_judgements` collection for audit:
thesis reviewers must be able to inspect any eval score back to the exact
prompt + model + temperature that produced it. This is the cost of using an
LLM as part of the measurement apparatus.

Provider pick mirrors extraction: `MEDITAB_JUDGE_PROVIDER` env var
(defaults to `gemini` for dev, will stay on a single canonical judge even
when extraction sweeps across multiple providers — we don't want judge drift
confused with extraction drift).
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Protocol

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from groq import APIStatusError, Groq

from meditab.mongo import get_db
from meditab.prompts import render_judge_prompt


_RETRYABLE_STATUS = {429, 500, 503}
_MAX_RETRIES = 3
_BASE_BACKOFF_S = 5.0

# Judge prompt version is pinned at the module level. Changing the prompt
# text = bumping this value. Every row in llm_judgements carries the version
# that produced the verdict, so results across prompt revisions stay
# comparable.
JUDGE_PROMPT_STRATEGY = "judge-clinical"
JUDGE_PROMPT_VERSION = "v1"


# --------------------------------- verdicts --------------------------------


_VERDICT_SCORES = {"yes": 1.0, "partial": 0.5, "no": 0.0}
_VERDICT_RE = re.compile(r'"verdict"\s*:\s*"(yes|partial|no)"', re.IGNORECASE)


def _parse_verdict(raw: str) -> tuple[str, str]:
    """Return (verdict, rationale). Tolerant parser — if JSON parse fails,
    fall back to regex for the verdict and keep the raw text as rationale.
    The judge model can flake on the structured shape; eval should still
    produce a score rather than crash."""
    try:
        obj = json.loads(raw)
        verdict = str(obj.get("verdict", "")).lower().strip()
        rationale = str(obj.get("rationale", "")).strip()
        if verdict in _VERDICT_SCORES:
            return verdict, rationale
    except (json.JSONDecodeError, AttributeError):
        pass

    m = _VERDICT_RE.search(raw)
    if m:
        return m.group(1).lower(), raw.strip()
    # Last resort — treat malformed output as "no" rather than crashing.
    return "no", f"[unparseable judge output] {raw!r}"


# --------------------------------- interface ------------------------------


class Judge(Protocol):
    judge_model: str
    judge_version: str

    def judge_equivalence(
        self,
        field_name: str,
        gold_text: str,
        extracted_text: str,
        *,
        patient_id: str,
        run_id: str,
    ) -> float: ...


# ------------------------------- base behavior ----------------------------


class _JudgeBase:
    """Shared logic: render prompt, persist the verdict to Mongo.
    Subclasses implement `_call_model(prompt) -> raw_string`."""

    judge_model: str
    judge_version: str = JUDGE_PROMPT_VERSION

    def _persist(
        self,
        *,
        field_name: str,
        gold_text: str,
        extracted_text: str,
        patient_id: str,
        run_id: str,
        verdict: str,
        rationale: str,
    ) -> None:
        db = get_db()
        db["llm_judgements"].insert_one(
            {
                "run_id": run_id,
                "patient_id": patient_id,
                "field": field_name,
                "gold_text": gold_text,
                "extracted_text": extracted_text,
                "judge_model": self.judge_model,
                "judge_strategy": JUDGE_PROMPT_STRATEGY,
                "judge_version": self.judge_version,
                "verdict": verdict,
                "rationale": rationale,
                "judged_at": datetime.now(timezone.utc),
            }
        )

    def _call_model(self, prompt: str) -> str:
        raise NotImplementedError

    def judge_equivalence(
        self,
        field_name: str,
        gold_text: str,
        extracted_text: str,
        *,
        patient_id: str,
        run_id: str,
    ) -> float:
        prompt = render_judge_prompt(
            field_name=field_name,
            gold_text=gold_text,
            extracted_text=extracted_text,
        )
        raw = self._call_model(prompt)
        verdict, rationale = _parse_verdict(raw)
        self._persist(
            field_name=field_name,
            gold_text=gold_text,
            extracted_text=extracted_text,
            patient_id=patient_id,
            run_id=run_id,
            verdict=verdict,
            rationale=rationale,
        )
        return _VERDICT_SCORES[verdict]


# ------------------------------ Gemini judge ------------------------------

GEMINI_DEFAULT_JUDGE_MODEL = "gemini-2.5-flash"


class GeminiJudge(_JudgeBase):
    def __init__(self, model: str = GEMINI_DEFAULT_JUDGE_MODEL) -> None:
        self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.judge_model = model
        # Temperature 0 — judge must be deterministic for reproducibility.
        self._config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        )

    def _call_model(self, prompt: str) -> str:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.judge_model, contents=prompt, config=self._config,
                )
                return response.text or ""
            except genai_errors.APIError as exc:
                status = getattr(exc, "code", None)
                if status not in _RETRYABLE_STATUS or attempt == _MAX_RETRIES:
                    raise
                time.sleep(_BASE_BACKOFF_S * attempt)
        return ""  # unreachable


# -------------------------------- Groq judge ------------------------------

GROQ_DEFAULT_JUDGE_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


class GroqJudge(_JudgeBase):
    def __init__(self, model: str | None = None) -> None:
        self._client = Groq(api_key=os.environ["GROQ_API_KEY"])
        self.judge_model = (
            model or os.getenv("GROQ_JUDGE_MODEL", GROQ_DEFAULT_JUDGE_MODEL)
        )

    def _call_model(self, prompt: str) -> str:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.judge_model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                )
                return response.choices[0].message.content or ""
            except APIStatusError as exc:
                status = getattr(exc, "status_code", None)
                if status not in _RETRYABLE_STATUS or attempt == _MAX_RETRIES:
                    raise
                time.sleep(_BASE_BACKOFF_S * attempt)
        return ""  # unreachable


# --------------------------------- factory --------------------------------


def make_judge() -> Judge:
    """Pick a Judge based on MEDITAB_JUDGE_PROVIDER env var.

    Defaults to "gemini" even when MEDITAB_LLM_PROVIDER=groq — we pin the
    judge so extraction sweeps across models don't conflate extraction
    differences with judge drift.
    """
    provider = os.getenv("MEDITAB_JUDGE_PROVIDER", "gemini")
    if provider == "gemini":
        return GeminiJudge()
    if provider == "groq":
        return GroqJudge()
    raise ValueError(f"unknown MEDITAB_JUDGE_PROVIDER={provider!r}")
