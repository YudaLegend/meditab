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
| 4 | Pydantic schema → `src/meditab/schema.py`, validators, parse all 10 golds | pending |
| 5 | `LLMClient` adapter + zero-shot extraction prompt + structured output | pending |
| 6 | Local Mongo (Docker) + ingestion script | pending |
| 7 | MCP server v0 (`get_patient`, `list_patients`, `store_extraction`, `get_gold`) | pending |
| 8 | Refactor extraction to go through MCP | pending |
| 9 | Batch extraction loop + structured logging | pending |
| 10 | Eval harness (per-field partial-match F1) | pending |
| 11 | Error analysis v0 | pending |
| 12 | Iterate on prompt + read first paper against concrete results | pending |

---

## Status

**Current week:** 1
**Last completed day:** 3 (2026-04-21) — env + smoke test + synthetic generator
**Next:** Day 4 — refine Pydantic schema, move to `src/meditab/schema.py`, validate all 10 golds

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
2. Check the **Status** section — you are resuming on **Day 4** (Pydantic schema refinement).
3. Look at **Carry-over** and **Open blockers** — have the hospital/tutor emails gone out? Has anything unblocked?
4. Tell Claude: "Resuming Meditab, Day 4. [Did I send the emails? Y/N] [Anything new to report?]"

### Day 4 at a glance (what's coming next)

Move the provisional Pydantic models from `scripts/day03_generate_synthetic.py` into `src/meditab/schema.py`, then refine against [docs/annotation_schema.md](docs/annotation_schema.md):

- Add `Field(description=...)` to every field (becomes interview-ready docstrings).
- Add validators: `dosi_min_mg_dia <= dosi_max_mg_dia`, `data_inici <= data_fi`, `motiu_discontinuacio` null iff `is_ongoing=true`, `durada_mesos` consistent with dates.
- Write a validation script that loads all 10 generated golds and reports which ones fail — those failures are the real edge cases.
- This is a **learning** day: user writes, Claude reviews.

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
