# Meditab — Session Handoff

> **Read this first at the start of every session.** It's the single source of truth for where the project stands. Update it at the end of every work session.

---

## Project summary

**Meditab** is a TFM (Trabajo Fin de Máster) project. Goal: extract structured tabular data from ~5000 free-text Catalan patient clinical histories ("cursos clínicos") using LLMs, and expose the data via MongoDB + MCP for downstream use (including a RAG assistant for doctors).

**Data:** ~5000 anonymized `.txt` files, one per patient, in Catalan. Stored at the hospital (collaborator). Not yet in hand.

**Extraction schema (per drug per patient):**
`farmac`, `categoria`, `dosi_mg_dia`, `data_inici`, `data_fi`, `durada_mesos`, `resposta_clinica` (free text), `efectes_adversos`, `motiu_discontinuacio`, plus a persistence field (`"persistent" | "no persistent"`).

**Submission:** ~2026-06-20. Implementation target: end of May 2026.

---

## Stack

- **Python 3.12** (uv-managed; pinned by `uv init`, not 3.11 as originally planned — newer but fully compatible)
- **LLM provider — dev:** Google Gemini 2.5 Flash via `google-genai` (free tier, `.env` → `GEMINI_API_KEY`)
- **LLM provider — hospital runs:** AWS Bedrock (Claude Haiku, Llama 3, Mistral, Nova) — EU region, granted from hospital machine post-install. Swap will be a one-file change thanks to the `LLMClient` adapter pattern planned for Day 5.
- MongoDB (local Docker for dev)
- Anthropic `mcp` Python SDK for the MCP server
- Pydantic for structured output schemas
- Doccano or Label Studio for annotation
- MLflow for experiment tracking
- FastAPI + Streamlit for the minimal RAG demo
- pytest, ruff, pre-commit

**Installed to date:** `google-genai`, `python-dotenv`, `pydantic` (transitive: `pydantic-core`, `google-auth`, `httpx`, etc.). See `pyproject.toml` + `uv.lock`.

---

## Scope (as of 2026-04-21)

**In scope:**
- Data ingestion pipeline (`.txt` → MongoDB)
- MCP server exposing patient retrieval tools
- Zero-shot and few-shot LLM extraction across 3–4 Bedrock models
- Gold-standard dataset (~50 patients, clinician-reviewed)
- Per-field evaluation + error analysis
- Minimal RAG demo over extracted tables

**Deferred to "Future Work":**
- Model fine-tuning / distillation
- Doctor-facing production UI
- Gold set > 50 patients
- Multi-hospital generalization

Rationale: timeline is ~8 weeks total (Apr 21 → Jun 20), which forced aggressive scoping.

---

## Weekly plan (compressed, 8 weeks)

| Week | Dates | Focus |
|------|-------|-------|
| 1 | Apr 21–27 | Scope, docs, laptop pipeline kickoff (synthetic data) |
| 2 | Apr 28–May 4 | Finish laptop pipeline (schema, extraction, Mongo, MCP, eval) |
| 3 | May 5–11 | First hospital session (assuming ticket clears); swap to Bedrock; real-data baselines |
| 4 | May 12–18 | Zero-shot + few-shot sweeps across models |
| 5 | May 19–25 | Error analysis, annotation with clinician in parallel |
| 6 | May 26–Jun 1 | Minimal RAG demo, freeze experiments |
| 7 | Jun 2–8 | Thesis writing sprint |
| 8 | Jun 9–20 | Tutor feedback, slides, defense |

## Laptop pipeline plan (Days 2–12)

Full pipeline built on synthetic Catalan data before first hospital session. After every day the pipeline still runs end-to-end.

| Day | Focus | Status |
|-----|-------|--------|
| 2 | `uv` env + smoke test (one LLM call on one fake note) | ✅ done |
| 3 | Synthetic data generator (10 notes + gold JSON) | ✅ done |
| 4 | Pydantic schema → `src/meditab/schema.py`, validators, parse all 10 golds | ✅ done |
| 5 | `LLMClient` adapter + zero-shot extraction prompt + structured output | ✅ done |
| 6 | Local Mongo (Docker) + ingestion script | ✅ done |
| 7 | MCP server v0 (`get_patient`, `list_patients`, `store_extraction`, `get_gold`) | ✅ done |
| 8 | Refactor extraction to go through MCP | ✅ done |
| 9 | Batch extraction loop + structured logging | ✅ done |
| 10 | Eval harness (per-field partial-match F1) | ✅ done |
| 11 | Error analysis v0 | pending |
| 12 | Iterate on prompt + read first paper against concrete results | pending |

---

## Status

**Current week:** 1
**Last completed day:** 10 + first sweep (2026-04-23) — eval harness live; per-field scores persisted to `eval_field_scores`; `scripts/sweep.py` drives N-cell extract+eval in one command. First real comparison: **few-shot > zero-shot > cot** on Groq/Llama-4-Scout across 10 synthetic patients (macros 0.935 / 0.888 / 0.855). Few-shot's edge is almost entirely `categoria` format-teaching (0.685 → 0.956). CoT *hurt* in structured-output mode — documented as a v2 variant to try with open output.
**Next:** Day 11 — error analysis v0 using `eval_field_scores` drilldown + `llm_judgements` verdict patterns.

### Carry-over (from Day 1, still outstanding)

- [ ] Email hospital: is the install ticket resolved (GitHub, VS Code, MongoDB), and when can I come in? **Ask also about MCP Pattern A vs B** (does the LLM itself invoke MCP tools, or is it enough that data access goes through MCP via our Python code?)
- [ ] Email tutor: confirm ethics committee requires only results/methodology (not raw data review), and schedule clinician annotation time

These are non-code blockers. Day 4+ proceed regardless, but the emails must go out before Week 2 ends.

### Day-by-day log

#### Day 1 — 2026-04-21 — done (except carry-over emails)
- [x] Private GitHub repo `meditab`, `.gitignore` with clinical-data exclusions, LICENSE, README stub
- [x] Folder structure + skeleton docs
- [x] `docs/scope.md` v1 (assumes 5000 files)
- [x] `docs/annotation_schema.md` v1 — JSON per patient, `drugs[]`, `dosi_min/max_mg_dia`, `is_ongoing`, structured `efectes_adversos[]` with `persistent`+`severitat`, descriptive `categoria` (ATC dropped)
- [x] `docs/eval_plan.md` v1 — 0/20/25 split + 5 held-out few-shot, per-field metrics w/ partial-match, paired bootstrap, 9-category error analysis
- [x] `docs/data_governance.md` v1 — GDPR Art.9, EU-only Bedrock, PII scanner plan, incident response table
- [x] Clarified operational constraints: data stays in hospital; compute is hospital-machine-only; ethics committee sees results only; clinician subdirector will co-annotate

**Key schema decisions (will need subdirector signoff):**
- One JSON per patient with `drugs[]`; one entry per (patient, generic drug), merged across visits.
- Drug identity = active substance (API), not brand.
- Dose ranges and escalations captured as `dosi_min_mg_dia` + `dosi_max_mg_dia`.
- Dates in ISO 8601; ongoing treatment flagged via `is_ongoing: bool` + `data_fi = null`.
- Adverse effects are a list of structured objects with `persistent` + `severitat`.
- ATC classification dropped entirely.

#### Day 2 — 2026-04-21 — done
- [x] `uv init --package --name meditab` → `pyproject.toml`, `src/meditab/__init__.py`
- [x] Dependencies: `google-genai`, `python-dotenv`, `pydantic` (via `uv add`)
- [x] `GEMINI_API_KEY` stored in `.env` (gitignored)
- [x] [scripts/archive/smoke_gemini.py](scripts/archive/smoke_gemini.py) — one fake Catalan note → Gemini 2.5 Flash → summary printed
- [x] UTF-8 stdout fix for Windows console (`sys.stdout.reconfigure`)
- [x] End-to-end plumbing verified: `uv run python scripts/archive/smoke_gemini.py` returns correct Catalan output

#### Day 3 — 2026-04-21 — done
- [x] [scripts/generate_synthetic.py](scripts/generate_synthetic.py) — synthetic data generator
- [x] **10 scenarios** for diversity (ISRS mono, dual antidepressant, antipsychotic+ansiolytic, dose escalation, liti+tremor, sparse notes, AE-driven discontinuation, 3-drug concomitant, long history, imprecise dates)
- [x] Provisional Pydantic models (`AdverseEffect`, `DrugEntry`, `PatientExtraction`, `SyntheticPatient`) inside the script — to be moved to `src/meditab/schema.py` on Day 4
- [x] Structured output via Gemini `response_schema=SyntheticPatient`
- [x] Minimal retry-with-backoff for transient 503/429 errors (3 attempts, 5s × attempt)
- [x] Generated 10 patients → `data/synthetic/notes/synthetic_{001..010}.txt` + `data/synthetic/gold/synthetic_{001..010}.json`
- [x] 16 total drug entries across 10 patients
- [ ] Cleanup: delete leftover Day-2 `data/synthetic/notes/patient_001.txt` (no matching gold; will trip Day 6 ingestion) — pending user decision
- [ ] Spot-check by user: read 2–3 notes + matching golds to sanity-check generator quality

**Observed caveat (for the thesis methodology chapter):**
Because the same LLM generates both the note and the gold for synthetic patients, extraction accuracy on this set will be inflated vs real data. This is acceptable for pipeline dev — real eval comes from the clinician-annotated gold set at the hospital.

#### Day 4 — 2026-04-22 — done
- [x] [src/meditab/schema.py](src/meditab/schema.py) — `AdverseEffect`, `DrugEntry`, `PatientExtraction` with `Field(description=...)` and validators
- [x] Switched `data_inici` / `data_fi` from `str` to `datetime.date` (free ISO-8601 validation)
- [x] Field validators: `_normalize_farmac` (lowercase + strip + non-empty), `_check_dose_positive`
- [x] Model validators: `_check_dose_order`, `_check_date_order`, `_check_ongoing_consistency`, `_check_duration_consistency` (±1 month tolerance), `_check_dose_unit_consistency`, `_check_unique_drugs`
- [x] [scripts/validate_golds.py](scripts/validate_golds.py) — loads all 10 golds and reports pass/fail
- [x] Day 3 generator refactored to import from `meditab.schema` (single source of truth)
- [x] Day 3 prompt tightened on `dosi_notes` (was misused by Gemini for "escalada gradual" narrative)
- [x] Fixed `data/synthetic/gold/synthetic_004.json` (`dosi_notes` null, since dose is in mg)
- [x] Final result: **10/10 golds pass validation**

**Finding worth noting:** The original generator prompt said `dosi_notes: null excepte si la dosi està en unitats no-mg`, but Gemini still filled it with "escalada gradual" narrative when it saw dose escalation. Root cause: prompt didn't say "SEMPRE null if mg/dia, INCLÚS if there's a range or escalation". This is a useful example for the thesis methodology chapter — schema violations aren't just about typing, they're about prompt ambiguity too.

**Known limitation (documented, not fixed):** `_check_duration_consistency` only fires when both `data_inici` and `data_fi` are set. An ongoing drug with `durada_mesos: 3` that started 3 years ago will pass silently. Decision: leave this as-is — real clinicians write approximate durations, and we don't want to reject their annotations.

#### Day 5 — 2026-04-22 — done
- [x] [src/meditab/llm_client.py](src/meditab/llm_client.py) — `LLMClient` Protocol + `GeminiExtractor` implementation
- [x] Zero-shot Catalan extraction prompt (rules mirror `docs/annotation_schema.md`)
- [x] Gemini `response_schema=PatientExtraction` — validators enforced at parse time
- [x] [scripts/archive/extract_one_local.py](scripts/archive/extract_one_local.py) — extract one note + diff vs gold
- [x] End-to-end verified on `synthetic_001`: extraction succeeds, diff runs, all validators pass

**Finding (important for the thesis):** Running the diff on `synthetic_001` flagged 4 differences. **Two were gold-quality bugs, not extraction bugs** — the gold had `dosi_min_mg_dia: 50` when the note showed dose escalation 25→50, and `durada_mesos: 1` when the schema says it must be null if `data_fi` is null. The other two were style differences (`categoria` specificity, `resposta_clinica` length).

Decision: **do NOT fix synthetic golds.** They are scratch data for pipeline dev; real eval comes from clinician-annotated gold at the hospital. Prompt tuning against noisy synthetic golds would overfit to gold quirks rather than the real task. Filed under "Week 5 error analysis pitfalls to warn about in the thesis".

#### Day 6 — 2026-04-22 — done
- [x] [docker-compose.yml](docker-compose.yml) — single-service Mongo 7, named volume, port 27017
- [x] [src/meditab/mongo.py](src/meditab/mongo.py) — `get_db()` reads `MONGO_URI` env var (defaults to localhost); `DB_NAME = "meditab"`
- [x] [scripts/ingest.py](scripts/ingest.py) — idempotent upsert by `_id = patient_id`; validates every gold through `PatientExtraction` before insert
- [x] Added `pymongo` dependency (via `uv add`)
- [x] Collections live: `raw_notes` (10 docs), `gold_extractions` (10 docs, 16 drug entries)
- [x] Dates serialized with `mode="json"` (ISO strings, not BSON dates — simpler for MCP responses later)

**Operational notes:**
- `docker compose up -d` at repo root starts Mongo; data persists in `meditab-mongo-data` volume across restarts.
- `docker compose down -v` wipes data (use before regenerating synthetic set).
- No auth configured — local dev only. Hospital Mongo will have its own auth; our `MONGO_URI` env var will carry the credentials.

#### Day 7 — 2026-04-22 — done
- [x] `uv add mcp` (→ `mcp==1.27.0`, + `starlette`/`uvicorn`/`sse-starlette`/`pydantic-settings` transitives)
- [x] [src/meditab/mcp_server.py](src/meditab/mcp_server.py) — FastMCP server with four `@mcp.tool()` functions (`list_patients`, `get_patient`, `get_gold`, `store_extraction`)
- [x] `store_extraction` validates the incoming dict through `PatientExtraction` before inserting — fail-loud rather than corrupt the collection
- [x] Writes land in a new `llm_extractions` collection, one doc per `(patient_id, model, run_at)` — no dedup by design (Day 9 wants run history)
- [x] [scripts/smoke_mcp.py](scripts/smoke_mcp.py) — async MCP client via `stdio_client`, spawns server as `uv run python -m meditab.mcp_server`, calls each tool, asserts shape
- [x] Smoke run green end-to-end: `list_patients OK — 10 / get_patient OK — 1069 chars / get_gold OK — 1 drugs / store_extraction OK — run_at=2026-04-22T17:26:54Z`

**Finding (FastMCP content-block quirk, worth remembering for Day 8):** FastMCP splits a `list[str]` return into *one `TextContent` block per element*, not one block containing a JSON array. Tools returning `dict` or `str` still produce a single block. Day 7 client had to add `_unwrap_list()` alongside `_unwrap_text()` for this reason. Rule of thumb baked into the smoke test: `dict`/`str` returns → `_unwrap_text` (+ optional `json.loads`); `list[X]` returns → `_unwrap_list` (one `.text` per element).

#### Day 8 — 2026-04-22 — done
- [x] **Run metadata scheme** — `store_extraction` now takes `model`, `prompt_strategy`, `prompt_version`, `run_id` alongside `extraction`. `llm_extractions` docs are fully queryable for Week 4 sweeps (one model, N strategies, M versions).
- [x] **Prompt registry** — `llm_client.PROMPTS: dict[(strategy, version), str]` replaces the single `EXTRACTION_PROMPT` constant. Adding few-shot / CoT in Week 4 = adding a dict entry, no extractor changes.
- [x] **Provider factory** — `make_extractor()` reads `MEDITAB_LLM_PROVIDER` (laptop: `gemini`, hospital: `bedrock` once `BedrockExtractor` lands in Week 3). Scripts never name a vendor.
- [x] **Transient-error retry** — `GeminiExtractor.extract` retries on 429/500/503 with linear backoff (5s × attempt, 3 attempts max). Triggered for real on the first Day 8 run (Gemini was 503ing); retry handled it on attempt 2.
- [x] [scripts/extract_one.py](scripts/extract_one.py) — end-to-end via MCP: `get_patient` → `extract` → `store_extraction` → optional `get_gold` diff. No disk I/O in the data path.
- [x] **Hospital-readiness:** gold fetch is wrapped in try/except, so the same script works on real hospital data where golds don't exist yet (diff is just skipped).
- [x] [scripts/archive/extract_one_local.py](scripts/archive/extract_one_local.py) updated to pass the new `strategy`/`version` args — kept as a disk-based smoke path for comparison.
- [x] [scripts/smoke_mcp.py](scripts/smoke_mcp.py) updated to pass the new metadata args to `store_extraction`; still green.
- [x] End-to-end run on `synthetic_001` succeeded: note fetched (1069 chars), gold fetched (1 drug), extraction stored under `run_id=2e2abd45...`, 4 diffs surfaced.

**Finding (same class as Day 5, now with more evidence):** The 4 diffs on `synthetic_001` are the same gold-quality / prompt-style split: gold says `dosi_min=50` when the note shows escalation `25→50` (the extractor got it right at `25`); gold uses terse `categoria='antidepressiu'` vs extractor's more specific `'Antidepressiu (ISRS)'`; gold's `resposta_clinica='bona'` is a one-word summary vs the extractor's sentence-level paraphrase. This confirms the Day 5 decision **not** to prompt-tune against synthetic golds — we'd be overfitting to gold-generation quirks, not to the real task. The four diff lines are on the list of "error-analysis pitfalls to warn about in the thesis."

**Hospital-day diff footprint (with Day 8 design in place):**
1. `.env`: `GEMINI_API_KEY` → AWS creds; `MONGO_URI` → hospital Mongo; `MEDITAB_LLM_PROVIDER=bedrock`.
2. Add `BedrockExtractor` class in `src/meditab/llm_client.py` (~30 lines, mirrors `GeminiExtractor`).
3. Change `notes_dir` in `scripts/ingest.py` to the real data path; drop the gold-ingestion block (no golds yet).
4. Everything else (`schema.py`, `mongo.py`, `mcp_server.py`, Day 7–10 scripts) is untouched.

#### Day 9 — 2026-04-23 — done
- [x] [src/meditab/mongo.py](src/meditab/mongo.py) — added `ensure_indexes(db)`. Single place to declare app-required indexes (currently just `llm_extractions.(run_id, patient_id)` unique). Idempotent — called at server boot.
- [x] [src/meditab/mcp_server.py](src/meditab/mcp_server.py) — `store_extraction` swapped from `insert_one` to `update_one({"run_id": ..., "patient_id": ...}, {"$set": doc}, upsert=True)`. Filter keys match the unique index keys, so the DB itself enforces one row per `(run_id, patient_id)` — bug-proof safety net behind the loop.
- [x] [scripts/extract_batch.py](scripts/extract_batch.py) — iterates all patients via `list_patients`, one `run_id` per invocation, per-patient try/except so one failure doesn't kill the run. `--limit N` for smoke mode. JSONL log at `logs/batch_<run_id8>.jsonl`, one line per patient with `{ts, run_id, pid, status, elapsed_ms, n_drugs|error}`. `JsonlLogger` flushes on every write so `tail -f` works and a crash mid-batch leaves valid lines on disk.
- [x] **Smoke (--limit 2):** 2/2 ok, 15.7s. Happy path verified.
- [x] **Full run (10 patients):** 5/5 ok, 5/5 fail by Gemini free-tier quota exhaustion (20 req/day for 2.5-flash) — **this is the point**: failures surfaced cleanly, logged with exception class, batch continued, no partial rows in Mongo (total stayed at 13 = 6 prior + 2 smoke + 5 new ok). Resilience proved in production conditions rather than mocked.
- [x] Two Mongo instances were running on 27017 (Docker container + pre-existing Windows native MongoDB 8.2 service). Host-side Python silently bound to the Windows service while Docker's mongo was empty and orphaned. `docker compose down -v` removed the ghost; standardized on Windows service. See decision log 2026-04-23.

**Findings worth recording for the thesis:**
1. **Gemini free-tier daily quota is the binding dev-side constraint, not the pipeline.** 20 req/day means the full 10-patient batch can only be run twice per day, minus any Day 3/5/8-style one-off calls. On hospital day this vanishes — Bedrock uses per-second rate limits, not daily quotas.
2. **Retry policy is semantically wrong for 429 quota errors.** The current linear backoff (5s, 10s) is designed for transient 503s, and those succeeded (synthetic_001/002/006 all recovered via retry). 429 quota errors return a `retryDelay` field (6s–53s in observed runs) that says "wait this long"; our fixed backoff was always shorter than that delay, wasting ~45s per failed patient. **Follow-up:** detect 429 in `GeminiExtractor._is_retryable` and either don't retry at all (simplest) or honor `retryDelay`. Deferred because hospital Bedrock has different semantics and the laptop path only has to survive, not be optimal.
3. **Error field in JSONL is bloated** (~1500 chars per 429 row, 95% of which is the same SDK link boilerplate). Log parsing still works (exception class is at the start), but future log reviewers will appreciate a shorter error shape. Deferred.

#### Day 9.5 — 2026-04-23 — done (pre-Day-10 infra: prompt registry + Groq provider)

Pulled forward from Week 4 to unblock Day 10 eval with more than one data point to score.

- [x] [src/meditab/prompts.py](src/meditab/prompts.py) — new module. Owns the `PROMPTS` registry (was in `llm_client.py`). Shared `_BASE_RULES` string so every variant's 9 extraction rules are literally identical — any quality delta between strategies is due to examples / reasoning scaffold, never rule drift. Three strategies registered:
    - `("zero-shot", "v1")` — migrated from Day 5; bit-for-bit identical output.
    - `("cot", "v1")` — same rules + an explicit 4-step reasoning instruction (a–d). With structured-output providers (Gemini response_schema, Groq json_object) the reasoning is suppressed in the output, but the nudge affects internal computation — acceptable for thesis comparison, explicitly documented in the module docstring.
    - `("few-shot", "v1")` — 3 in-context examples (`synthetic_001`, `_003`, `_007`), loaded from Mongo at first call via `@lru_cache(maxsize=1)`. Chosen for shape diversity: mono-drug ISRS, multi-drug, AE-heavy discontinuation. On hospital day this list will be replaced by clinician-curated examples (bump version to v2).
- [x] `render_prompt(strategy, version, note_ca, patient_id)` — returns the fully-assembled prompt. Uses `str.replace()` (not `.format()`) because few-shot examples contain JSON with literal braces that would break format interpolation.
- [x] [src/meditab/llm_client.py](src/meditab/llm_client.py) — prompt code removed (moved to `prompts.py`). `GroqExtractor` added alongside `GeminiExtractor`. Uses Groq's OpenAI-compatible `chat.completions.create` with `response_format={"type": "json_object"}` and schema injected into the system message; client-side Pydantic validation on the response (since json_object mode doesn't enforce schema server-side like Gemini's `response_schema` does). Same retry policy on 429/500/503. `make_extractor()` factory now handles `"gemini" | "groq" | "bedrock"` via `MEDITAB_LLM_PROVIDER`.
- [x] `uv add groq` → `groq==1.2.0`.
- [x] Default Groq model: `meta-llama/llama-4-scout-17b-16e-instruct`. Overridable via `GROQ_MODEL` env var for Week 4 sweeps (Kimi K2, Qwen 3, etc.).
- [x] Smoke tests — all green on `synthetic_004` (not in few-shot pool, avoids leakage):
    - Groq + zero-shot on `synthetic_001`: same 4 diffs as Gemini — the known gold-quality issues, not extraction bugs.
    - Groq + few-shot + `synthetic_004`: 1 drug extracted (escitalopram 20–60 mg/dia, ongoing).
    - Groq + cot + `synthetic_004`: identical output to few-shot — reassuring sanity check that structured output with a reasoning instruction doesn't destabilize the extraction.
- [x] Few-shot prompt assembly verified: 8070 chars total (3 full example notes + golds inlined), all `{note_ca}` / `{patient_id}` placeholders substituted correctly, no leftover braces.

**Why this matters for Day 10:** without this, the eval harness would have exactly one data point to score — zero-shot / Gemini / v1. Now Day 10 can compare a 3 × 2 matrix (zero-shot, few-shot, cot) × (Gemini, Groq), enough for a real "which knob helps" table in the thesis. Hospital day extends the same matrix with Bedrock providers (Claude Haiku, Llama 3, Mistral, Nova).

**Deferred to when it's actually needed:**
- `--strategy` / `--version` CLI flags on `extract_one.py` and `extract_batch.py`. Currently strategy/version are module-level constants. Day 10 eval may want to drive batches via flags rather than editing constants; trivial to add.
- `day08` and `day09` scripts still use the old `EXTRACTION_PROMPT` import-free code path — they call `extractor.extract(..., strategy="zero-shot", version="v1")` which routes through the new prompt registry. Nothing to change in those scripts.

#### Day 10 — 2026-04-23 — done

The measurement apparatus. Turns "pipeline produces JSON" into "pipeline produces JSON and we know how right it is, per field, with an audit trail."

- [x] [scripts/extract_one.py](scripts/extract_one.py) + [scripts/extract_batch.py](scripts/extract_batch.py) — added `--strategy` / `--version` CLI flags. Defaults preserve prior behavior (`zero-shot` / `v1`). Same script drives Week 4's 3 × 2 prompt-strategy × provider matrix without edits.
- [x] [src/meditab/eval.py](src/meditab/eval.py) — pure-function scoring module. No network calls (judge passed in as a dependency so eval is unit-testable with a fake). Drug-level pairing by `farmac` exact match; per-field comparators with the policy locked above; `FieldScore` / `DrugScore` / `PatientScore` dataclasses; precision/recall/F1 properties at the patient level.
- [x] [src/meditab/judge.py](src/meditab/judge.py) — `Judge` Protocol + `GeminiJudge` + `GroqJudge` + `make_judge()` factory driven by `MEDITAB_JUDGE_PROVIDER` (default: gemini). Temperature pinned at 0 for determinism. Tolerant verdict parser (`_parse_verdict`) handles JSON, JSON-fragment, and fully malformed judge output — malformed falls back to "no" rather than crashing the eval. Every verdict lands in `llm_judgements` with `(run_id, patient_id, field, judge_model, judge_version, verdict, rationale, judged_at)`.
- [x] [src/meditab/prompts.py](src/meditab/prompts.py) — added `JUDGE_CLINICAL_V1` prompt + `JUDGE_PROMPTS` registry + `render_judge_prompt()`. 3-verdict scheme (`yes` / `partial` / `no`) mapped to scores (1.0 / 0.5 / 0.0).
- [x] [src/meditab/mongo.py](src/meditab/mongo.py) `ensure_indexes` — added unique index on `eval_results.run_id` and compound `(run_id, patient_id)` on `llm_judgements` (non-unique, for drilldown speed).
- [x] [scripts/evaluate.py](scripts/evaluate.py) — CLI: `--run-id` (default: latest) + `--limit`. Loads rows, scores, prints per-patient + per-field summary, upserts one row into `eval_results`.

**Smoke results:**
- Groq zero-shot, 1 patient (`synthetic_001`): drug-F1=1.0, field-mean=0.76, 1 judge call, 0.5s.
- Gemini zero-shot, 5 patients (Day 9 batch `69713142...`): drug-F1=1.0 across all, **field macro-mean 0.879**, 1.7s end-to-end.

**The bottom three fields are exactly the known issues:**

| Field | Score | Cause |
|---|---|---|
| `durada_mesos` | 0.50 | Gold has `durada_mesos: 1` when `data_fi: null` (schema says null is required for ongoing). Extractor correctly emits `null`. Gold-quality bug surfaced as partial match. |
| `categoria` | 0.60 | Style mismatch: gold `"antidepressiu"`, extracted `"Antidepressiu (ISRS)"`. Token-F1 0.67 per pair. |
| `resposta_clinica` | 0.67 | Judge "partial" on terse-gold vs verbose-extraction cases. Rationale from the judge: *"El text extret ofereix més detalls que el text de referència, però no hi ha contradicció"*. |

Everything else at 1.0. This is the **best sanity check we could hope for**: the harness is punishing exactly what the earlier Day 5/8 diff surfaced by hand, and isn't flagging fields where we already knew the extractor was correct. If the harness had reported 0.0 on these, the comparators would be too strict; if 1.0, too loose. 0.5–0.67 is right.

**Architectural notes worth keeping:**
1. **Judge provider is pinned independently of extraction provider.** `MEDITAB_LLM_PROVIDER=groq` for the sweep + `MEDITAB_JUDGE_PROVIDER=gemini` for the judge prevents conflating "extraction got better" with "judge got more lenient". On hospital day we'll pin one canonical judge (likely Bedrock Claude) across every cell of the sweep.
2. **Judgements are persisted independently of eval_results.** `eval_results` is the summary; `llm_judgements` is the audit. If a thesis reviewer asks "how did you score patient X's resposta_clinica in run Y?", the query is `db.llm_judgements.find({"run_id": Y, "patient_id": X})` and you get the gold text, extracted text, verdict, and rationale that produced the 0.5.
3. **Every judge prompt change bumps the version.** Judge prompt is `("judge-clinical", "v1")`. If error analysis suggests the judge is too strict on "bona" vs verbose paraphrase, we add `("judge-clinical", "v2")` with looser criteria and re-evaluate — old `v1` verdicts stay in the collection for comparability.

**What this unlocks for Week 4 sweeps:** `evaluate.py --run-id X` produces one row in `eval_results` per extraction run. A sweep across (3 strategies × 2 providers × N model-sizes) produces N eval_results rows, all joinable in a single query for comparison tables.

#### Day 10.5 — 2026-04-23 — done (sweep driver + per-field persistence + first real comparison)

Two small but load-bearing additions pulled in before Day 11 error analysis, because Day 11 needs (a) *multiple* runs to compare and (b) per-field drilldown data persisted.

- [x] [src/meditab/mongo.py](src/meditab/mongo.py) `ensure_indexes` — added unique compound index on `eval_field_scores.(run_id, patient_id, farmac, field)`.
- [x] [scripts/evaluate.py](scripts/evaluate.py) — added `_persist_field_scores()` that writes one doc per `(run_id, patient_id, farmac, field)` to `eval_field_scores`. Also writes pseudo-field rows `"_missed_drug"` and `"_hallucinated_drug"` (score=0.0) so a single query `db.eval_field_scores.find({"run_id": X, "score": {"$lt": 1.0}})` surfaces every error in a run, drug-level or field-level alike.
- [x] [scripts/sweep.py](scripts/sweep.py) — new. Takes `--pair strategy:version` (repeatable) or defaults to `[("zero-shot","v1"), ("few-shot","v1"), ("cot","v1")]`. For each cell spawns `extract_batch.py` (capturing run_id from stdout), then `evaluate.py --run-id <...>`. Tolerates per-patient extraction failures (rc=1) as partial signal — only rc>1 aborts the sweep. Prints a comparison table from `eval_results` at the end.
- [x] **Full sweep Groq × 3 strategies × 10 synthetic patients**:

| Strategy | n_ok | Macro | Drug-F1 | categoria | resposta_clinica | motiu_disc | data_inici | dosi_min | durada |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| zero-shot/v1 | 10 | 0.888 | 1.000 | 0.685 | 0.688 | 0.875 | 0.875 | 0.812 | 0.750 |
| **few-shot/v1** | 9 | **0.935** | 1.000 | **0.956** | **0.867** | 0.933 | 0.933 | 0.800 | 0.800 |
| cot/v1 | 10 | 0.855 | 1.000 | 0.685 | 0.594 | 0.906 | 0.875 | 0.688 | 0.750 |

run_ids: zero-shot=`7b2b1427...`, few-shot=`b7e9671a...`, cot=`d862cda5...`

**Findings for the thesis:**
1. **Few-shot's +4.7% macro win is almost entirely `categoria` format-alignment.** Zero-shot/cot both produced `"Antidepressiu (ISRS)"` while gold is `"antidepressiu"`; few-shot saw examples with the terse style and matched it. Evidence that the format of `resposta_clinica` summaries also drafts closer to gold under few-shot (judge verdict shifts from "partial" to "yes" more often — reflected in the 0.688 → 0.867 lift).
2. **CoT underperformed zero-shot by ~3.3%.** Plausible mechanism: Gemini/Groq structured-output mode suppresses free-form reasoning, so the extra reasoning instruction costs attention without producing visible chain-of-thought. Pure overhead. Filed as decision log 2026-04-23 — follow-up would be `("cot-open", "v1")` with relaxed output mode, client-side JSON parsing. Not doing it now because it changes the comparison shape.
3. **Few-shot is slower and more error-prone.** Per-patient latency ~9s (vs ~1s zero-shot) because the prompt is ~8 KB. And Llama 4 Scout produced an invalid date `"2022-12"` (YYYY-MM) on one patient — rejected by Pydantic validator, batch continued. So few-shot buys quality at ~10× latency cost and ~10% rejection risk at this model size. Hospital day with Bedrock Claude Haiku should flip these trade-offs.
4. **Drug-level recall/precision is 1.000 for every cell.** All 3 strategies find every drug. Differences are purely in field-level extraction quality, not drug identification. The drug pipeline is solved; prompt work is now about fidelity.

**Architectural note:** `eval_field_scores` is the Day 11 drilldown substrate. Each row has `(run_id, patient_id, farmac, field, score, details, model, prompt_strategy, prompt_version)`. Sample query: "show me every `categoria` row scoring < 1.0 across every cot run" → `db.eval_field_scores.find({"prompt_strategy": "cot", "field": "categoria", "score": {"$lt": 1.0}})`. The `details` string (e.g. `token-F1('antidepressiu', 'Antidepressiu (ISRS)')`) is already enough to understand the score without re-running eval — that's what you asked about.

---

## Operational model (clarified 2026-04-21)

- **Data never leaves the hospital.** User works on a hospital-provided computer that will have GitHub, VS Code, MongoDB installed (ticket in progress). AWS Bedrock access granted from that machine *after* install completes.
- **Ethics committee sees results, not data.** Formal approval likely unnecessary since the hospital's existing agreement covers data handling — tutor to confirm.
- **Clinician subdirector will co-annotate gold set** with user (~50 patients).
- **Dev environment is synthetic Catalan text on user's laptop.** Hospital-machine time is reserved for real experiments, not plumbing. The full extraction pipeline must work end-to-end on synthetic data *before* first hospital session.

## Open blockers

These MUST unblock before the project can progress past Week 2:

1. **Hospital-machine install ticket** — GitHub, VS Code, MongoDB being installed; AWS Bedrock access granted afterwards. Status email being sent Day 1.
2. **Data delivery** — 5000 `.txt` files not yet accessible. Hospital says anonymized; to be verified on first hospital session.
3. **Ethics clarification** — tutor to confirm whether existing hospital agreement is sufficient (likely) or formal committee approval is needed (would take 4–6 weeks and threaten the timeline).
4. **Annotation scheduling** — clinician subdirector available to co-annotate; need to schedule sessions.

## Fallback if blockers slip past end of Week 2

Pipeline is already being built on **synthetic Catalan clinical text** (primary dev environment, not a fallback). If real data access slips, synthetic runs give publishable engineering results; only the real-data evaluation chapter is at risk.

---

## Collaboration protocol (from TaskFlow, still applies)

- User builds it himself; Claude guides and unblocks, does not hand over full solutions.
- Concepts first; skeleton+TODO for learning tasks; direct write only for scaffolding.
- User shares progress → Claude reviews, explains, catches issues.

---

## Next session starter

Whenever you start a new session:

1. Read this HANDOFF.
2. Check the **Status** section — you are resuming on **Day 11** (error analysis v0).
3. Look at **Carry-over** and **Open blockers** — have the hospital/tutor emails gone out? Has anything unblocked?
4. Tell Claude: "Resuming Meditab, Day 11. [Did I send the emails? Y/N] [Anything new to report?]"

### Day 11 at a glance (what's coming next)

The eval harness gives per-field scores; Day 11 turns those into *why*. Key question: which prompt-strategy × provider cells are dropping which fields, and is the pattern structural (eval policy too strict) or model-dependent (one prompt type consistently worse)?

What to build:
- A query/report layer over `eval_results` + `llm_judgements` that, given a run_id (or a set of run_ids), surfaces the patient + drug + field combinations scoring below a threshold. Think: `"which 5 rows dragged the resposta_clinica score down"`.
- Confusion-style breakdown for judge verdicts: how often does the judge say "partial" (extractor paraphrases gold) vs "no" (extractor is actually wrong)? The former is a gold-quality / prompt-style issue; the latter is a real extraction bug.
- A first pass at the 9-category error taxonomy from `docs/eval_plan.md` — can we auto-classify judge "no" verdicts into those categories using a second (cheap) LLM call, or do we need to hand-code a first pass?

**Before writing code, decide:** does error analysis produce a Mongo-stored artifact (queryable later, part of the audit trail), or a one-off markdown report per run_id? Probably both — Mongo for machine-readable, markdown for thesis figures.

### Operational constraint worth flagging

Gemini free-tier gives **20 req/day** for 2.5-flash. The full 10-patient batch burns half; Day 10 eval adds 2 judge calls per patient per run (up to 10 judgements for a 5-patient run). Plan Day 11+ runs accordingly, or pin `MEDITAB_JUDGE_PROVIDER=groq` to keep Gemini budget for extraction.

---

## Decision log

*(Record non-obvious choices here so you can defend them in the TFM.)*

- **2026-04-21** — Scoped out fine-tuning / distillation due to 8-week timeline. Rationale: defendable thesis > over-ambitious unfinished thesis.
- **2026-04-21** — Chose MongoDB over Postgres despite structured final output. Rationale: raw patient `.txt` varies wildly; schemaless storage for raw layer; structured schema only at extraction layer. MongoDB also already in planned stack for TaskFlow — familiarity.
- **2026-04-21** — Dose fields modeled as `dosi_min_mg_dia` + `dosi_max_mg_dia`, not a single number or string range. Rationale: real psychiatry notes frequently show dose escalation and ranges; numeric pair is queryable and preserves information without parsing string ranges later.
- **2026-04-21** — Adverse effects modeled as structured array (`descripcio`, `persistent`, `severitat`), not a single string with inlined parentheticals. Rationale: matches the schema's `persistencia` requirement cleanly and is more clinically queryable.
- **2026-04-21** — Dropped ATC classification entirely from schema (initially planned as a post-hoc lookup). Rationale: not needed for the thesis's clinical questions; adds complexity (maintaining a lookup table, additional eval field) for no downstream user of the data. Descriptive `categoria` alone is sufficient.
- **2026-04-21** — Test set frozen at 25 patients; dev at 20; few-shot pool at 5 (held out). Rationale: with only ~50 gold patients, splits must be small; paired bootstrap compensates for small sample size when comparing models.
- **2026-04-21** — Compute model: hospital-machine-only for real data; user's laptop for synthetic-data development. Rationale: hospital data cannot leave their network; user only gets the machine after the install ticket clears. Building the pipeline on synthetic data in parallel means no dead weeks while waiting.
- **2026-04-21** — Ethics committee will not review raw data, only study results and methodology. Rationale: hospital's existing data-protection agreement covers handling; committee's role reduces to standard thesis review. Pending tutor confirmation; if wrong, this becomes the critical-path blocker.
- **2026-04-21** — Running experiments + annotating gold set will happen *in parallel* at the hospital, not sequentially. Rationale: 8-week timeline doesn't afford waiting for full gold set before starting experiments; early model runs also inform annotation edge cases.
- **2026-04-21** — Dev LLM provider = Google Gemini 2.5 Flash (free tier). Rationale: zero billing, native Pydantic `response_schema` support mirrors Bedrock+Claude structured-output behavior, so the hospital swap is a one-file change. Anthropic API not used to avoid $5+ setup cost just for dev.
- **2026-04-21** — Synthetic dev set = 10 patients, 10 diverse scenarios, one LLM call produces note + gold together. Rationale: consistency guaranteed (no drift between note and gold); small enough to iterate fast; caveat is that extraction accuracy on this set will be inflated vs real clinician-annotated data.
- **2026-04-21** — MCP integration will be **Pattern B** (Python acts as MCP client, LLM does not see MCP tools). Pattern A (LLM-as-agent invoking tools) can be layered on top later if the hospital requires it. Rationale: Pattern B lets us measure extraction quality in isolation and is faster to build; Pattern A is strictly additive. Confirmation pending in hospital email.
- **2026-04-21** — Python 3.12 (not the originally planned 3.11). Rationale: uv selected it based on system availability; no incompatibilities; fighting the default is churn for no benefit.
- **2026-04-22** — Run-level metadata scheme: every `llm_extractions` row carries `(model, prompt_strategy, prompt_version, run_id, run_at)` in addition to the extraction payload. Rationale: Week 4 sweeps will cross N models × M prompting strategies × K prompt revisions; without these four keys there's no way to group or compare runs after the fact. `run_id` is regenerated per batch invocation; `prompt_version` is bumped manually whenever prompt text changes (cheap and explicit — no hashing of Catalan strings).
- **2026-04-22** — Prompt registry over prompt string. Rationale: prompts are looked up by `(strategy, version)` from a module-level `PROMPTS` dict, not passed in by callers. This keeps prompts as a first-class artifact of the codebase (versioned in git, one source of truth), and makes Week 4's "add few-shot variant" a one-line change rather than a refactor.
- **2026-04-22** — Extractor picked via `MEDITAB_LLM_PROVIDER` env var (default `gemini`). Rationale: keeps every script vendor-neutral; the hospital-day diff becomes an env-var flip plus adding a `BedrockExtractor` class, not a rewrite of the extraction scripts.
- **2026-04-22** — Retry transient LLM errors in the extractor, not in the caller. Rationale: Day 8's very first live run hit a Gemini 503; Day 9 batch across 10 patients would trip this nearly every run. Retrying at the extractor boundary means batch loops, future eval scripts, and any downstream user of `LLMClient.extract` inherit resilience for free. Retry-on set is narrow (429/500/503) to avoid hiding real bugs behind silent retries.
- **2026-04-23** — Local dev stack standardized on the pre-existing Windows-native MongoDB 8.2 service, not the Docker container. Rationale: the Docker container bound port 27017 *after* the Windows service had already taken it, so Docker's "bind succeeded" (per `docker compose ps`) was misleading — all host traffic went to the Windows service while the Docker container sat empty. Discovered during Day 9 verification (mongosh-in-container saw no data; Python saw 6 rows). Fix: `docker compose down -v`. Hospital day uses `MONGO_URI` env var, so dev laptop choice is orthogonal. `docker-compose.yml` left in the repo as optional — if someone reproduces this on a laptop without the Windows service, it'll Just Work™.
- **2026-04-23** — Day 9 batch policy: a single-patient failure logs and continues, it does not halt the run. Rationale: one LLM timeout or validator error across 5000 patients would waste hours of upstream work. JSONL log + structured `status` field per patient means Day 10's eval reads success/fail as data, not as script exit codes. Confirmed on Day 9 full run: 5 failures, 5 ok, batch still ran to completion and wrote a parseable log.
- **2026-04-23** — Known follow-up deferred: `GeminiExtractor` currently retries 429 with the same linear backoff as 503, but Gemini's 429s are quota-based (daily limit on the free tier) and include a `retryDelay` field (6–53s in observed runs) that's always larger than our fixed backoff. Retries are therefore wasted on 429. Simplest fix: treat 429 as non-retryable. Deferred because (a) hospital-day Bedrock has different rate-limit semantics and (b) the current code still correctly logs the failure rather than crashing — it's wasteful, not broken.
- **2026-04-23** — Prompts moved from `llm_client.py` to a dedicated `src/meditab/prompts.py` module. Rationale: `llm_client.py` is about transport (HTTP, retries, auth, structured output); prompts are about *what you say*. These change for unrelated reasons — a retry-policy tweak should not live in the same file as a prompt iteration. Also, the few-shot variant alone adds ~8 KB of Catalan text to the module; keeping that in `llm_client.py` would bury the 30 lines of interesting transport code. Staying at a single file (`prompts.py`) rather than a `prompts/` package: we don't yet have enough prompt variants to justify per-file separation.
- **2026-04-23** — Few-shot examples are loaded from Mongo at first use (cached in-process), not inlined as Python string constants. Rationale: keeping `prompts.py` small (template only), and the examples are already in Mongo as part of the synthetic gold set. Trade-off: if someone regenerates synthetic data without bumping `("few-shot", "v1")` to `v2`, the prompt silently changes — violating the "prompt version is the hash of what was sent" invariant. Mitigation: synthetic data is frozen for this phase, and the HANDOFF explicitly flags this as a rule to not break. On hospital day the clinician-curated few-shot pool is similarly stable.
- **2026-04-23** — Added Groq (Llama 4 Scout, `meta-llama/llama-4-scout-17b-16e-instruct`) as a second dev-side provider. Rationale: Gemini free-tier's 20 req/day daily quota (Day 9 finding) makes experimental iteration painful; Groq's free tier is per-minute/per-day orders of magnitude looser. Same `LLMClient` Protocol, new class, one `elif` in the factory — no script changes required. Hospital day is unaffected; Bedrock still lands as `"bedrock"` provider in Week 3. Groq uses `response_format={"type": "json_object"}` (not native schema enforcement like Gemini), so validation happens client-side via `PatientExtraction.model_validate_json` — same end contract, different mechanism.
- **2026-04-23** — `("cot", "v1")` prompt uses prompt-level reasoning instructions (a–d steps) paired with structured output mode, knowing the reasoning text is suppressed by Gemini's `response_schema` / Groq's `json_object`. Rationale: fair prompt-only comparison against zero-shot/few-shot at the same output contract. If later experiments show CoT hurting (because the model "wastes tokens" preparing reasoning that's then discarded), we'll add a `("cot-open", "v1")` variant that relaxes output mode to plain text and parses JSON from the response — but that's a separate design decision and a different fair comparison.
- **2026-04-23** — Eval v1 policy (locked, see `docs/eval_plan.md` for the high-level rationale): exact for `farmac` / `is_ongoing` / dates; token-F1 for `categoria` and `dosi_notes`; numeric tolerance (1 mg) for dose fields; numeric tolerance (1 month) for `durada_mesos`; **LLM-as-judge** for `resposta_clinica` and `motiu_discontinuacio`; coarse `count + concatenated descripcio token-F1` for `efectes_adversos`. Rationale: deterministic comparators wherever the schema supports them; LLM-as-judge *only* for fields where verbose-vs-terse is the dominant mismatch mode. `efectes_adversos` per-AE matching deferred to eval v2 — simpler coarse scoring gives a usable signal on the synthetic set where AE counts are small.
- **2026-04-23** — Judge provider is pinned independently of extraction provider via `MEDITAB_JUDGE_PROVIDER` (default: `gemini`). Rationale: Week 4 sweeps vary the extraction model and strategy while the judge stays constant — otherwise we can't tell whether a score change is the extraction improving or the judge getting more lenient. On hospital day we'll pin one canonical Bedrock judge (probably Claude Haiku for speed) across every sweep cell.
- **2026-04-23** — Every judge verdict persists to `llm_judgements` with gold text, extracted text, verdict, rationale, and judge (model + prompt version). Rationale: LLM-in-the-loop measurement requires an audit trail — a thesis reviewer must be able to inspect any score back to the exact prompt + model that produced it. Cost: ~1 KB per verdict × 2 free-text fields × N patients × M runs. Negligible for scale we care about.
- **2026-04-23** — Judge verdict parsing is tolerant (JSON → JSON-regex → "no" fallback). Rationale: LLMs in JSON mode can still flake (empty response, truncation, drift). An eval that crashes on the first malformed verdict is useless for sweeps; one that silently scores malformed → "no" is debuggable from `llm_judgements` rows with a `[unparseable judge output]` rationale. Trade-off: a genuine judge failure may be misread as an extraction miss. Flagged for Day 11 — if the rationale string starts with `[unparseable...]`, exclude from aggregate.
