# Scope — Meditab

## Problem statement

Doctors manually review patient drug histories stored as free-text clinical notes in Catalan, which is slow and makes it hard to get a quick view of longitudinal treatment. Meditab automatically extracts structured per-drug tables from these notes, so clinicians can review treatment timelines, responses, and adverse effects at a glance.

## Inputs

- **Format:** UTF-8 `.txt` files, one per patient.
- **Language:** Catalan (possibly with occasional Spanish or Latin medical terms).
- **Volume:** ~5000 files.
- **Source:** Hospital clinical records, delivered by the subdirector.
- **Anonymization:** Hospital states files are already anonymized. To be **verified on receipt** (see [data_governance.md](data_governance.md)).
- **Custody:** Local encrypted storage on the student's laptop; never committed to git; never transferred outside the EU.

## Outputs

For each patient, a JSON document loaded into MongoDB with:
- `patient_id` (anonymized linking key)
- `drugs[]` — one entry per (patient, generic drug), merged across visits
- Per-drug fields defined in [annotation_schema.md](annotation_schema.md)

Downstream consumers:
1. Doctors querying MongoDB directly via an MCP server (security requirement).
2. A minimal RAG demo that answers natural-language questions over the extracted tables.

## Success criteria

- **Per-field F1 ≥ 0.80** for categorical fields (`farmac`, `categoria`, `motiu_discontinuacio`) on held-out test set.
- **Per-field F1 ≥ 0.70** for numeric/date fields (`dosi_min_mg_dia`, `dosi_max_mg_dia`, `data_inici`, `data_fi`) with defined partial-match rules.
- **End-to-end extraction** for one patient file in **< 30 seconds** on Bedrock.
- **MCP server** exposes at least `get_patient`, `list_patients`, `store_extraction` tools and is demonstrated with a client.
- **Minimal RAG demo** answers ≥ 5 representative doctor queries with cited evidence.
- **Written thesis** submitted by **2026-06-20**.

## Non-goals (out of scope)

- Model fine-tuning or distillation — deferred to Future Work.
- Production doctor-facing UI — only a minimal demo.
- Multi-hospital generalization — single-site evaluation.
- Real-time / streaming ingestion — batch only.
- Natural-language patient search — only structured filters in MCP.
- Free-text `resposta_clinica` normalization into categorical labels.

## Assumptions & dependencies

- Files are fully anonymized at source (verified on receipt).
- AWS Bedrock access is granted in an EU region (Paris or Frankfurt) within **Week 2**.
- Subdirector (clinician) is available for ~10 hours of annotation review across the project.
- Local development laptop has ≥ 16 GB RAM, ≥ 50 GB free disk, full-disk encryption.
- Ethics committee approval is either not required or is completed by **Week 3**.

## Risks & mitigations

| Risk | Likelihood | Impact | Mitigation / Fallback |
|------|-----------|--------|-----------------------|
| AWS Bedrock access delayed past Week 2 | medium | high | Fallback: synthetic Catalan clinical text + HuggingFace models (BSC Aina) for pipeline development. |
| Delivered data has residual PHI | medium | high | Automated PII scanner + manual review of first 50 files; pause and re-anonymize if needed. |
| Inter-annotator agreement with subdirector is low (κ < 0.6) | medium | medium | Schema-revision session after first 20 shared annotations; simplify contested fields. |
| Catalan tokenization / clinical abbreviations degrade LLM performance | medium | medium | Include few-shot examples with abbreviations; evaluate Catalan-specific models. |
| Subdirector availability slips | medium | medium | User performs first-pass annotation alone; subdirector reviews a subset for agreement. |

## Evaluation approach (summary)

Per-field precision / recall / F1 on a held-out test set, aggregated as macro-F1 across fields. Model comparisons use paired bootstrap (1000 resamples) for 95% confidence intervals. See [eval_plan.md](eval_plan.md).

## Timeline

See [HANDOFF.md](../HANDOFF.md) for the 8-week plan (2026-04-21 → 2026-06-20).
