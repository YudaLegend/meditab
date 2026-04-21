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

## Stack (planned)

- Python 3.11 (uv or poetry)
- MongoDB (local Docker for dev)
- Anthropic `mcp` Python SDK for the MCP server
- AWS Bedrock for LLM experimentation (Claude Haiku, Llama 3, Mistral, Nova) — EU region
- Pydantic for structured output schemas
- Doccano or Label Studio for annotation
- MLflow for experiment tracking
- FastAPI + Streamlit for the minimal RAG demo
- pytest, ruff, pre-commit

*(Stack is not installed yet — only committed to on paper.)*

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
| 1 | Apr 21–27 | Scope, lit review, AWS request, annotation schema |
| 2 | Apr 28–May 4 | MongoDB + ingestion, start annotating |
| 3 | May 5–11 | MCP server, 20 more patients annotated |
| 4 | May 12–18 | Baselines: zero-shot across models |
| 5 | May 19–25 | Few-shot + structured output + error analysis |
| 6 | May 26–Jun 1 | Minimal RAG demo, freeze experiments |
| 7 | Jun 2–8 | Thesis writing sprint |
| 8 | Jun 9–20 | Tutor feedback, slides, defense |

---

## Status

**Current week:** 1
**Current day:** 1 (2026-04-21)

### Day-by-day log

#### Day 1 — 2026-04-21 — in progress
- [x] Created private GitHub repo `meditab`
- [x] Added Python `.gitignore` + clinical-data exclusions (data/, raw/, anonymized/, *.txt, *.jsonl, *.csv, extractions/, .env)
- [x] Added LICENSE, README stub
- [x] Scaffolded folder structure + skeleton docs
- [x] Filled `docs/scope.md` v1 (assumes 5000 files; all sections populated)
- [x] Filled `docs/annotation_schema.md` v1 — JSON per patient, `drugs[]`, `dosi_min/max_mg_dia`, `is_ongoing`, structured `efectes_adversos[]` with `persistent`+`severitat`, descriptive `categoria` (ATC dropped per 2026-04-21 decision)
- [x] Filled `docs/eval_plan.md` v1 — 0/20/25 split + 5 held-out few-shot pool, stratified by drugs-per-patient, per-field metrics w/ partial-match rules, paired bootstrap, 9-category error analysis
- [x] Filled `docs/data_governance.md` v1 — GDPR Art.9, EU-only Bedrock, PII scanner plan, incident response table
- [ ] Send 3 unblock emails (AWS access, data delivery, ethics committee)
- [ ] Read ~1 paper on LLM clinical IE

**Key schema decisions recorded today (will need subdirector signoff):**
- One JSON per patient with `drugs[]`; one entry per (patient, generic drug), merged across visits.
- Drug identity = active substance (API), not brand.
- Dose ranges and escalations captured as `dosi_min_mg_dia` + `dosi_max_mg_dia` (not a single number or a string).
- Dates in ISO 8601; ongoing treatment flagged via `is_ongoing: bool` + `data_fi = null` (no magic "Actual" string).
- Adverse effects are a list of structured objects, not a single inlined string.
- ATC categorization is **post-hoc via lookup table**, not extracted by the LLM (keeps extraction tractable).

---

## Open blockers

These MUST unblock before the project can progress past Week 2:

1. **AWS access** — no account yet, no Bedrock approval, no region confirmed. Hospital has mentioned an AWS collaboration but no specifics. Email owed.
2. **Data delivery** — 5000 `.txt` files not yet in hand. Hospital says anonymized; to be verified on arrival.
3. **Ethics committee** — status unknown. Tutor to confirm whether approval is needed / exists.
4. **Annotation pipeline** — clinician (subdirector) will review annotations; user annotates first pass. No annotations done yet.

## Fallback if blockers slip past end of Week 2

Pivot temporarily to **synthetic Catalan clinical text** (generated with Bedrock on non-PHI prompts) to build + test the pipeline. Not ideal for the thesis, but keeps momentum. Do not let blockers cause dead weeks.

---

## Collaboration protocol (from TaskFlow, still applies)

- User builds it himself; Claude guides and unblocks, does not hand over full solutions.
- Concepts first; skeleton+TODO for learning tasks; direct write only for scaffolding.
- User shares progress → Claude reviews, explains, catches issues.

---

## Next session starter

Whenever you start a new session:

1. Read this HANDOFF.
2. Check the **Status** section — which day are you on?
3. Look at **Open blockers** — has anything unblocked since last session?
4. Tell Claude: "Resuming Meditab, Day N. Here's what I did / where I'm stuck."

---

## Decision log

*(Record non-obvious choices here so you can defend them in the TFM.)*

- **2026-04-21** — Scoped out fine-tuning / distillation due to 8-week timeline. Rationale: defendable thesis > over-ambitious unfinished thesis.
- **2026-04-21** — Chose MongoDB over Postgres despite structured final output. Rationale: raw patient `.txt` varies wildly; schemaless storage for raw layer; structured schema only at extraction layer. MongoDB also already in planned stack for TaskFlow — familiarity.
- **2026-04-21** — Dose fields modeled as `dosi_min_mg_dia` + `dosi_max_mg_dia`, not a single number or string range. Rationale: real psychiatry notes frequently show dose escalation and ranges; numeric pair is queryable and preserves information without parsing string ranges later.
- **2026-04-21** — Adverse effects modeled as structured array (`descripcio`, `persistent`, `severitat`), not a single string with inlined parentheticals. Rationale: matches the schema's `persistencia` requirement cleanly and is more clinically queryable.
- **2026-04-21** — Dropped ATC classification entirely from schema (initially planned as a post-hoc lookup). Rationale: not needed for the thesis's clinical questions; adds complexity (maintaining a lookup table, additional eval field) for no downstream user of the data. Descriptive `categoria` alone is sufficient.
- **2026-04-21** — Test set frozen at 25 patients; dev at 20; few-shot pool at 5 (held out). Rationale: with only ~50 gold patients, splits must be small; paired bootstrap compensates for small sample size when comparing models.
