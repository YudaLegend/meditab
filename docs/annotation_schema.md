# Annotation Schema — Meditab

> **The source of truth for extraction. Every downstream step (eval, prompts, DB schema) depends on this.**
> Every annotated patient must conform. Every extractor must produce this shape.

## Granularity

- **One JSON document per patient.** Top-level has `patient_id` and `drugs[]`.
- **One entry per (patient, generic drug)** — merge all visits/episodes for the same drug into one row.
- **Drug identity = active substance (API)**, not brand name. E.g., "Prozac" → `"fluoxetina"`.
- If the same drug is taken in multiple distinct regimens over time, capture the full span (earliest start → last end) and capture dose variation via `dosi_min_mg_dia` / `dosi_max_mg_dia`.

## Top-level JSON shape

```json
{
  "patient_id": "string",
  "drugs": [ /* DrugEntry objects, see below */ ]
}
```

## DrugEntry fields

| Field | Type | Required | Format / values | Notes |
|-------|------|----------|-----------------|-------|
| `farmac` | string | yes | lowercase generic name (API) | e.g., `"liti"`, `"lamotrigina"` |
| `categoria` | string | yes | descriptive therapeutic class as written by clinician | e.g., `"Estabilitzador d'humor"`, `"Antidepressiu (ISRS)"` |
| `dosi_min_mg_dia` | number \| null | no | positive float, mg/day | null if no dose specified |
| `dosi_max_mg_dia` | number \| null | no | positive float, mg/day | equals `dosi_min_mg_dia` if single dose; higher if range or dose escalation |
| `dosi_notes` | string \| null | no | free text | only if dose is in non-mg units (mg/kg, IU, etc.) |
| `data_inici` | string \| null | no | ISO 8601 `YYYY-MM-DD` | null if not specified |
| `data_fi` | string \| null | no | ISO 8601 `YYYY-MM-DD` | null if ongoing OR not specified (see `is_ongoing`) |
| `is_ongoing` | boolean | yes | `true` / `false` | `true` when treatment continues at last note |
| `durada_mesos` | number \| null | no | positive integer | computed field: months between `data_inici` and `data_fi`; null if either is null |
| `resposta_clinica` | string \| null | no | free text (Catalan) | concise summary of clinical response across visits |
| `efectes_adversos` | array | yes | array of `AdverseEffect` objects (can be empty `[]`) | see below |
| `motiu_discontinuacio` | string \| null | no | free text | null if `is_ongoing = true` |

### AdverseEffect sub-object

| Field | Type | Required | Values | Notes |
|-------|------|----------|--------|-------|
| `descripcio` | string | yes | free text (Catalan) | e.g., `"tremolor fi"`, `"disfunció sexual"` |
| `persistent` | enum \| null | no | `"persistent"` \| `"no persistent"` \| null | null if not stated |
| `severitat` | enum \| null | no | `"lleu"` \| `"moderada"` \| `"greu"` \| null | null if not stated |

## Edge cases & rules

1. **Dose ranges** (e.g., "800–1000 mg/dia") → `dosi_min_mg_dia = 800`, `dosi_max_mg_dia = 1000`.
2. **Dose escalation over time** (e.g., 400 → 800 → 1000 mg over months) → `dosi_min_mg_dia = 400`, `dosi_max_mg_dia = 1000`.
3. **Single stable dose** (e.g., 200 mg/dia) → `dosi_min_mg_dia = 200`, `dosi_max_mg_dia = 200`.
4. **Dose in non-mg units** (mg/kg, IU, gotes) → leave both mg fields null, populate `dosi_notes` with the original string.
5. **Ongoing treatment** ("encara en tractament", no end date in notes) → `is_ongoing = true`, `data_fi = null`, `motiu_discontinuacio = null`.
6. **Missing end date but treatment clearly stopped** → `is_ongoing = false`, `data_fi = null`, note reason in `motiu_discontinuacio` if known.
7. **Drug name as brand** → normalize to generic (API). If uncertain, keep as-written and flag in `resposta_clinica`.
8. **Month+year dates** (e.g., "Gener 2025") → use day `01` and note imprecision in `resposta_clinica`.
9. **Ambiguous AE attribution** (adverse effect that could be from drug A or drug B) → assign to the drug the clinician attributed it to in the notes. If truly unclear, assign to the most recently introduced drug and note the ambiguity in `resposta_clinica`.
10. **Multiple distinct regimens of same drug with a gap** (stopped, restarted later) → still one entry; use earliest start and latest end; capture the gap in `resposta_clinica`.
11. **Empty AE list** → `"efectes_adversos": []`, not null.

## Open questions for subdirector (Week 1–2 review)

- Is capturing only generic/API sufficient, or does the clinician need brand-name preservation somewhere?
- Should `severitat` be required or remain optional?
- For dose escalation, is `min`/`max` clinically adequate, or should we also record the most-recent stable dose?
- Expected average number of drugs per patient? (Informs annotation time budget.)
- Is a free-text `categoria` field enough, or should we constrain to a fixed class list provided by the clinician?

## Versioning

- **v1** — 2026-04-21 — initial draft (Day 1). Pending subdirector review.
