# Until day 10

##  PatientExtraction, schema
For this project, the most difficult part is to design what data should we store once the information of the history (curs clinic) is extracted. Because those data are we interested and is how after we will use to annotate the gold-dataset and is what restriction we will set to be loaded in the Mongo DB.

So we created the PatientExtraction class, and there it validades the condition that shoulbe stated for each field. We got three kind of checks in schema.py

1. Type chechs (free, from type hints): dosi_min_mg_dia: float | None - a string here fails.
2. Field Validators(@field_validator): normalize "farmac" to lowercase, reject non-positve doses.
3. Cross-field validator (@model_validator): eg: _check_ongoing_consistency - if is_ongoing=True then data_fi and motiu_discontinuació must be null. _check_dose_order -- dosi_min <= dosi_max. _check_unique_drugs - no duplicates "farma" in the drugs[] list.

So here , if the LLM hallucinates an "ongoing" treatenebt wut a data_fi set, the extraction is rejected at parse time, so this kind of check prevents one more step the hallucinations of the LLM.


## Eval score
PatientScore               ← one per patient
├── drug_scores[]          ← one per paired gold↔extracted drug
│   └── field_scores[]     ← one per field (farmac, categoria, dosi_min, ...)
│       ├── field: str
│       ├── score: float ∈ [0, 1]
│       └── details: str   ← human-readable "why this score"
├── missed_drugs[]         ← farmacs present in gold, missing from extraction
└── hallucinated_drugs[]   ← farmacs present in extraction, not in gold


This is the archicteture that how we evaluate how "good" is the data extracted. So a patiend could have multiple drugs, and each drugs has many field (farmac,categoria,dosi_min...). 
PatientScore also exposes derived properties:

drug_precision = len(drug_scores) / (len(drug_scores) + len(hallucinated_drugs)) — "of the drugs I extracted, how many were right?"
drug_recall = len(drug_scores) / (len(drug_scores) + len(missed_drugs)) — "of the drugs that were there, how many did I catch?"
drug_f1 = harmonic mean of the two.

These are at the drug level, not field level — they tell you "did you get the drug set right", independent of per-field quality on matched drugs. A drug_f1=1.0 with field-mean=0.5 means "you found every drug but got a lot of the fields wrong". That's a different diagnosis than drug_f1=0.5 with field-mean=1.0 ("you got half the drugs, but the ones you got are perfect").



farmac — exact (always 1.0 for matched pairs)
Uses farmac as the drug-pairing key. By the time a DrugScore exists, the farmac already matched exactly — otherwise the drug would be in missed_drugs or hallucinated_drugs. So this always scores 1.0 in a DrugScore. Included for completeness so the field list is uniform.

categoria — token-F1
Aggressive normalization (lowercase + strip non-alphanumeric + split on whitespace) → two token sets → token-level F1.


gold:      "antidepressiu"           → {"antidepressiu"}
extracted: "Antidepressiu (ISRS)"    → {"antidepressiu", "isrs"}

shared = {"antidepressiu"}  (1 token)
precision = 1/2 = 0.5   (half of extracted tokens are shared)
recall    = 1/1 = 1.0   (all gold tokens are shared)
F1 = 2·0.5·1.0 / (0.5+1.0) = 0.667
dosi_min_mg_dia, dosi_max_mg_dia — numeric tolerance (± 1 mg)

score_numeric_tol(25.0, 50.0, tol=1.0) → 0.0   # |25-50| > 1
score_numeric_tol(50.0, 50.0, tol=1.0) → 1.0   # exact
score_numeric_tol(50.5, 50.0, tol=1.0) → 1.0   # within tolerance
Both null → 1.0. One null and one not → 0.0.



resposta_clinica — LLM-as-judge
Judge sees the gold text + extracted text + field name → emits "yes" | "partial" | "no" → mapped to 1.0 | 0.5 | 0.0.


gold:      "bona"
extracted: "Millora significativa de l'estat d'ànim i ansietat. Sense efectes adversos."

judge verdict: "partial"
judge rationale: "El text extret ofereix més detalls que el text de referència, però no hi ha contradicció"
score: 0.5