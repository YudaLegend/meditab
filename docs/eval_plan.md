# Evaluation Plan — Meditab

> How we measure whether the extraction system works. Every model/prompt comparison uses this.

## Dataset splits

- **Total gold-annotated patients (target):** 50, produced in Weeks 2–3.
- **Train:** 0 — we are using zero/few-shot with Bedrock models, not fine-tuning. If a few-shot prompt uses gold examples, they come from a **fixed pool of 5 dev examples** that is excluded from all evaluation.
- **Dev:** 20 patients — used for prompt engineering, error analysis, and model selection.
- **Test:** 25 patients — locked; used only for final results in the thesis.
- **Held-out control:** 5 examples kept separately as the few-shot prompt pool; never evaluated against.
- **Stratification:** balance by number of drugs per patient (light: ≤2 drugs, medium: 3–5, heavy: ≥6), so each split has a similar distribution of case complexity.
- **Test lockdown:** test files live in `eval/test/`, hashed at creation, and the hash is committed to git. Any access before final evaluation is logged.

## Metrics per field

| Field | Metric | Partial match rule |
|-------|--------|--------------------|
| `farmac` | precision / recall / F1 | exact string match after lowercase + strip accents |
| `categoria` | accuracy + per-class F1 | exact match after lowercase + strip accents; against subdirector-curated class list |
| `dosi_min_mg_dia` | MAE + "within ±10%" accuracy | a value is "correct" if within 10% of gold or within 50 mg absolute (whichever is larger) |
| `dosi_max_mg_dia` | MAE + "within ±10%" accuracy | same rule |
| `data_inici` | exact + "within ±30 days" accuracy | a date is "correct" if within 30 days of gold |
| `data_fi` | exact + "within ±30 days" accuracy | same rule |
| `is_ongoing` | accuracy | exact |
| `durada_mesos` | MAE | computed field; errors propagate from dates |
| `resposta_clinica` | LLM-as-judge (faithfulness vs source) + ROUGE-L vs gold | judge run ≥ 3 times, average; mark unstable items where variance > 0.2 |
| `efectes_adversos[*].descripcio` | set-level precision / recall / F1 | match if normalized Levenshtein similarity ≥ 0.8 |
| `efectes_adversos[*].persistent` | accuracy (on matched AEs only) | exact |
| `efectes_adversos[*].severitat` | accuracy (on matched AEs only) | exact |
| `motiu_discontinuacio` | LLM-as-judge semantic match | 3-run average |

## Aggregate metrics

- **Primary:** macro-average F1 across categorical/text fields + accuracy on numeric/date fields normalized to [0,1].
- **Secondary:** **perfect-drug-entry accuracy** — fraction of `DrugEntry` objects with every required field correct. Interpretable "end-to-end" score.
- **Tertiary:** **perfect-patient accuracy** — fraction of patient JSONs with all drugs correct. Harsh, expected to be low; useful as a ceiling-comparison.

## Statistical significance

- When comparing Model A vs Model B on the same test set, use **paired bootstrap** at the patient level:
  - 1000 resamples of the 25 test patients.
  - For each resample, compute both models' scores and the difference.
  - Report **mean difference + 95% CI**.
  - Declare Model A > Model B only if the 95% CI does not include zero.
- Never compare on the dev set for final claims; dev informs selection, test confirms.

## Error analysis protocol

After every experiment run, categorize each failed field into one of:

1. **Hallucinated drug** — drug not in source text
2. **Missed drug** — drug in source but not extracted
3. **Wrong category** — drug correct, class wrong
4. **Dose unit confusion** — e.g., mg vs mg/kg
5. **Date parse error** — wrong format, wrong century, month/day swap
6. **AE attribution error** — AE assigned to wrong drug
7. **AE persistence/severity error** — wrong enum value
8. **Ongoing/discontinued confusion**
9. **Other / multiple**

Tally per category per model. Dominant category drives next iteration's prompt changes.

## What NOT to measure (and why)

- **Latency:** batch job, not real-time; noted as a single end-to-end number in success criteria but not an optimization target.
- **Cost per 1000 tokens:** Bedrock pricing is documented in the thesis appendix, not a primary metric.
- **Training-data memorization:** no fine-tuning, so not applicable.

## Eval harness (implementation plan)

- Single CLI: `python eval/run.py --model <model> --prompt <prompt_name> --split dev|test`
- Outputs: a per-field metrics table (CSV), a per-patient JSON of predictions vs gold, a confusion table for categorical fields.
- Every run logs: git commit, model, prompt hash, dataset hash, timestamp. Stored in `eval/runs/<timestamp>/`.
