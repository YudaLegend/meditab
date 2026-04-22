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
| 9 | Batch extraction loop + structured logging | pending |
| 10 | Eval harness (per-field partial-match F1) | pending |
| 11 | Error analysis v0 | pending |
| 12 | Iterate on prompt + read first paper against concrete results | pending |

---

## Status

**Current week:** 1
**Last completed day:** 8 (2026-04-22) — end-to-end extraction through MCP, run metadata + prompt registry + provider factory in place, retry on transient Gemini errors
**Next:** Day 9 — batch extraction loop across all 10 patients + structured logging + unique `(run_id, patient_id)` index on `llm_extractions`

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
- [x] [scripts/day02_smoke_test.py](scripts/day02_smoke_test.py) — one fake Catalan note → Gemini 2.5 Flash → summary printed
- [x] UTF-8 stdout fix for Windows console (`sys.stdout.reconfigure`)
- [x] End-to-end plumbing verified: `uv run python scripts/day02_smoke_test.py` returns correct Catalan output

#### Day 3 — 2026-04-21 — done
- [x] [scripts/day03_generate_synthetic.py](scripts/day03_generate_synthetic.py) — synthetic data generator
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
- [x] [scripts/day04_validate_golds.py](scripts/day04_validate_golds.py) — loads all 10 golds and reports pass/fail
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
- [x] [scripts/day05_zero_shot_extract.py](scripts/day05_zero_shot_extract.py) — extract one note + diff vs gold
- [x] End-to-end verified on `synthetic_001`: extraction succeeds, diff runs, all validators pass

**Finding (important for the thesis):** Running the diff on `synthetic_001` flagged 4 differences. **Two were gold-quality bugs, not extraction bugs** — the gold had `dosi_min_mg_dia: 50` when the note showed dose escalation 25→50, and `durada_mesos: 1` when the schema says it must be null if `data_fi` is null. The other two were style differences (`categoria` specificity, `resposta_clinica` length).

Decision: **do NOT fix synthetic golds.** They are scratch data for pipeline dev; real eval comes from clinician-annotated gold at the hospital. Prompt tuning against noisy synthetic golds would overfit to gold quirks rather than the real task. Filed under "Week 5 error analysis pitfalls to warn about in the thesis".

#### Day 6 — 2026-04-22 — done
- [x] [docker-compose.yml](docker-compose.yml) — single-service Mongo 7, named volume, port 27017
- [x] [src/meditab/mongo.py](src/meditab/mongo.py) — `get_db()` reads `MONGO_URI` env var (defaults to localhost); `DB_NAME = "meditab"`
- [x] [scripts/day06_ingest.py](scripts/day06_ingest.py) — idempotent upsert by `_id = patient_id`; validates every gold through `PatientExtraction` before insert
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
- [x] [scripts/day07_mcp_smoke.py](scripts/day07_mcp_smoke.py) — async MCP client via `stdio_client`, spawns server as `uv run python -m meditab.mcp_server`, calls each tool, asserts shape
- [x] Smoke run green end-to-end: `list_patients OK — 10 / get_patient OK — 1069 chars / get_gold OK — 1 drugs / store_extraction OK — run_at=2026-04-22T17:26:54Z`

**Finding (FastMCP content-block quirk, worth remembering for Day 8):** FastMCP splits a `list[str]` return into *one `TextContent` block per element*, not one block containing a JSON array. Tools returning `dict` or `str` still produce a single block. Day 7 client had to add `_unwrap_list()` alongside `_unwrap_text()` for this reason. Rule of thumb baked into the smoke test: `dict`/`str` returns → `_unwrap_text` (+ optional `json.loads`); `list[X]` returns → `_unwrap_list` (one `.text` per element).

#### Day 8 — 2026-04-22 — done
- [x] **Run metadata scheme** — `store_extraction` now takes `model`, `prompt_strategy`, `prompt_version`, `run_id` alongside `extraction`. `llm_extractions` docs are fully queryable for Week 4 sweeps (one model, N strategies, M versions).
- [x] **Prompt registry** — `llm_client.PROMPTS: dict[(strategy, version), str]` replaces the single `EXTRACTION_PROMPT` constant. Adding few-shot / CoT in Week 4 = adding a dict entry, no extractor changes.
- [x] **Provider factory** — `make_extractor()` reads `MEDITAB_LLM_PROVIDER` (laptop: `gemini`, hospital: `bedrock` once `BedrockExtractor` lands in Week 3). Scripts never name a vendor.
- [x] **Transient-error retry** — `GeminiExtractor.extract` retries on 429/500/503 with linear backoff (5s × attempt, 3 attempts max). Triggered for real on the first Day 8 run (Gemini was 503ing); retry handled it on attempt 2.
- [x] [scripts/day08_mcp_extract.py](scripts/day08_mcp_extract.py) — end-to-end via MCP: `get_patient` → `extract` → `store_extraction` → optional `get_gold` diff. No disk I/O in the data path.
- [x] **Hospital-readiness:** gold fetch is wrapped in try/except, so the same script works on real hospital data where golds don't exist yet (diff is just skipped).
- [x] [scripts/day05_zero_shot_extract.py](scripts/day05_zero_shot_extract.py) updated to pass the new `strategy`/`version` args — kept as a disk-based smoke path for comparison.
- [x] [scripts/day07_mcp_smoke.py](scripts/day07_mcp_smoke.py) updated to pass the new metadata args to `store_extraction`; still green.
- [x] End-to-end run on `synthetic_001` succeeded: note fetched (1069 chars), gold fetched (1 drug), extraction stored under `run_id=2e2abd45...`, 4 diffs surfaced.

**Finding (same class as Day 5, now with more evidence):** The 4 diffs on `synthetic_001` are the same gold-quality / prompt-style split: gold says `dosi_min=50` when the note shows escalation `25→50` (the extractor got it right at `25`); gold uses terse `categoria='antidepressiu'` vs extractor's more specific `'Antidepressiu (ISRS)'`; gold's `resposta_clinica='bona'` is a one-word summary vs the extractor's sentence-level paraphrase. This confirms the Day 5 decision **not** to prompt-tune against synthetic golds — we'd be overfitting to gold-generation quirks, not to the real task. The four diff lines are on the list of "error-analysis pitfalls to warn about in the thesis."

**Hospital-day diff footprint (with Day 8 design in place):**
1. `.env`: `GEMINI_API_KEY` → AWS creds; `MONGO_URI` → hospital Mongo; `MEDITAB_LLM_PROVIDER=bedrock`.
2. Add `BedrockExtractor` class in `src/meditab/llm_client.py` (~30 lines, mirrors `GeminiExtractor`).
3. Change `notes_dir` in `scripts/day06_ingest.py` to the real data path; drop the gold-ingestion block (no golds yet).
4. Everything else (`schema.py`, `mongo.py`, `mcp_server.py`, Day 7–10 scripts) is untouched.

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
2. Check the **Status** section — you are resuming on **Day 9** (batch extraction loop + structured logging).
3. Look at **Carry-over** and **Open blockers** — have the hospital/tutor emails gone out? Has anything unblocked?
4. Tell Claude: "Resuming Meditab, Day 9. [Did I send the emails? Y/N] [Anything new to report?]"

### Day 9 at a glance (what's coming next)

Scale the Day 8 one-patient loop to all 10 synthetic patients. The whole point of the Day 8 metadata scheme is to make this trivial — a `for pid in await list_patients(...)` around the same extract-and-store block.

New file:
- `scripts/day09_batch_extract.py` — iterates all patients, one `run_id` per invocation, structured JSONL log per patient (pid, status, elapsed_ms, n_drugs, error_msg).

Mongo change:
- Add a **unique** index on `llm_extractions.(run_id, patient_id)` so retries within a batch *upsert* instead of accumulate. Switch `store_extraction` from `insert_one` to `update_one({...}, {"$set": doc}, upsert=True)`. This is the one-line toggle we deferred from Day 7.

Resilience:
- If a single patient's extraction raises (LLM final-failure after all retries, or validator error), the batch should log, mark that patient failed, and continue. One bad apple must not kill the run.

**Learning angle:** Day 9 is where "pipeline" stops being a diagram and starts being a loop with per-item success/failure accounting. The JSONL log is the first input to Day 10's eval harness.

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
