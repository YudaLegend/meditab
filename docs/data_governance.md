# Data Governance — Meditab

> This document is required reading for anyone working on the project.
> It must be signed off by the tutor before real patient data is touched.

## Data classification

- **Type:** Personal health data, anonymized at source.
- **GDPR category:** Article 9 special category. Even anonymized, treated with elevated care.
- **Legal basis for processing:** Research for a Master's thesis under an institutional agreement between the university and the hospital.
- **Retention:** All local copies deleted no later than **2026-07-31** (thesis defense + buffer).
- **No data leaves EU jurisdiction:** AWS region must be EU (Paris `eu-west-3` or Frankfurt `eu-central-1`).

## Anonymization contract

Fields the hospital confirms have been removed or replaced in the delivered files:

- [ ] Patient names (first and last)
- [ ] Patient identifiers (NHC, CIP, DNI, passport, SS number)
- [ ] Dates of birth (replaced with year only, or age at first visit)
- [ ] Addresses, postal codes, phone numbers, emails
- [ ] Doctor names, signatures, handwritten initials
- [ ] Hospital-internal unit IDs, room numbers, bed numbers
- [ ] Any free-text mentions of the above within clinical notes

**Confirm the exact list with the hospital data owner before ingestion. Amend this section with their written response.**

## Verification on receipt

Before any file is ingested into MongoDB, run:

1. **Manual random-sample review** of 20 files — read end-to-end, flag anything that looks identifying.
2. **Automated PII scan** (`src/scripts/pii_scan.py` to be written in Week 2):
   - Regex patterns for Spanish DNI/NIE, NHC-like strings, phone numbers, email, postal codes
   - Name-like token detector via spaCy `ca`/`es` models, filtered against a Catalan first-name list
3. **Date-of-birth heuristics:** flag any full `DD/MM/YYYY` date before 2010 as a potential DOB.

If any file contains residual PHI:
- **STOP** ingestion immediately.
- Quarantine the file in `data/quarantine/` (gitignored).
- Report to the data owner in writing.
- Do NOT proceed until re-anonymized files are delivered.

## Data flow

```
┌──────────┐  secure transfer  ┌───────────────────────┐
│ Hospital │  (USB / SFTP)     │ Student laptop        │
│          ├──────────────────>│ BitLocker-encrypted   │
└──────────┘                   │ disk                  │
                               │                       │
                               │  ┌─────────────────┐  │
                               │  │ Local MongoDB   │  │
                               │  │ (localhost+auth)│  │
                               │  └────────┬────────┘  │
                               │           │           │
                               │  ┌────────▼────────┐  │
                               │  │ Python pipeline │──┼──── AWS Bedrock
                               │  │                 │  │     (EU region,
                               │  │                 │<─┼─── inference only,
                               │  └─────────────────┘  │     no training)
                               └───────────────────────┘
```

**Confirm with AWS account settings that Bedrock requests for this account do not opt into AWS model improvement / training.**

## Access control

- **Student (user):** full access, work laptop only.
- **Subdirector (clinician):** access to anonymized files via the agreed annotation interface (Doccano / Label Studio on the student's local network). No raw MongoDB access, no AWS.
- **Tutor:** read-only reports and aggregated metrics. No individual patient access unless needed for supervision.
- **GitHub:** NEVER. The repository is private and `.gitignore` excludes all data paths.

## Audit

- Every Bedrock API call logged with: timestamp, patient_id, model, input/output token counts. **No raw content** is logged (to avoid a second copy of PHI).
- Every MongoDB write logged with: timestamp, collection, document count, operation type.
- Logs stored locally in `logs/`, gitignored, deletable on project close.

## Incident response

| Incident | Action |
|----------|--------|
| PHI accidentally committed to git | Immediate `git filter-repo` to purge + force push + rotate repo + notify tutor |
| Laptop lost / stolen | Report within 24 h; remote wipe via Windows Find My Device or equivalent |
| PHI detected in delivered files | Stop ingestion; quarantine; report to data owner in writing |
| Unauthorized access to MongoDB | Rotate MongoDB credentials; audit logs; notify tutor |
| Accidental AWS request to non-EU region | Delete logs containing output; notify tutor; reconfigure region lock |

## Signoff

- [ ] Tutor reviewed: ____________  Date: ____________
- [ ] Subdirector reviewed: ____________  Date: ____________
- [ ] Hospital data owner confirmed anonymization list: ____________  Date: ____________
