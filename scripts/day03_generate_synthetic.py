"""Day 3: generate N fake Catalan clinical notes + matching gold JSON.

Each generated patient produces two files:
  data/synthetic/notes/{pid}.txt   — the fake Catalan clinical note
  data/synthetic/gold/{pid}.json   — the corresponding gold extraction

One LLM call per patient returns both, which guarantees the gold matches
the note (no drift between two separate calls).

The Pydantic models below are PROVISIONAL. On Day 4 you'll move them to
src/meditab/schema.py and refine them against docs/annotation_schema.md
(validators, edge cases, Field docstrings).
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()


# ---------- Provisional schema (Day 4: move to src/meditab/schema.py) ----------


class AdverseEffect(BaseModel):
    descripcio: str
    persistent: Literal["persistent", "no persistent"] | None = None
    severitat: Literal["lleu", "moderada", "greu"] | None = None


class DrugEntry(BaseModel):
    farmac: str
    categoria: str
    dosi_min_mg_dia: float | None = None
    dosi_max_mg_dia: float | None = None
    dosi_notes: str | None = None
    data_inici: str | None = None
    data_fi: str | None = None
    is_ongoing: bool
    durada_mesos: int | None = None
    resposta_clinica: str | None = None
    efectes_adversos: list[AdverseEffect]
    motiu_discontinuacio: str | None = None


class PatientExtraction(BaseModel):
    patient_id: str
    drugs: list[DrugEntry]


class SyntheticPatient(BaseModel):
    """LLM output wrapper: fake note + matching gold."""

    note_ca: str
    gold: PatientExtraction


# ---------- Scenarios for diversity ----------

SCENARIOS = [
    "pacient home jove amb un sol antidepressiu ISRS, sense efectes adversos, tractament en curs",
    "pacient dona mitjana edat amb dos antidepressius successius (el primer discontinuat per manca de resposta, el segon actual)",
    "pacient gran amb un antipsicòtic i un ansiolític, el segon amb efectes adversos persistents lleus (sedació diürna)",
    "pacient amb escalada de dosi d'un antidepressiu (20→40→60 mg/dia) amb nàusees transitòries no persistents",
    "pacient amb un estabilitzador de l'ànim (liti) amb tremolor persistent lleu i controls analítics periòdics",
    "pacient amb un únic fàrmac en curs, només dues visites, pocs detalls clínics",
    "pacient amb un antidepressiu discontinuat per efectes adversos greus (rash cutani), substituït per un altre",
    "pacient amb tres fàrmacs concomitants: antidepressiu, ansiolític de rescat, hipnòtic de curta durada",
    "pacient amb història llarga: fàrmac durant 2 anys, discontinuat per remissió clínica mantinguda",
    "pacient amb dates imprecises a la nota (només mes/any, no dies), però amb resposta clínica descrita",
]


# ---------- Generator ----------

GENERATOR_PROMPT = """Ets un generador de dades sintètiques en català per a recerca en extracció d'informació clínica.

Has de produir UN pacient fictici. Escenari: {scenario}.

Requeriments:

1. `note_ca`: una nota clínica en català lliure, estil "curs clínic" hospitalari. Entre 120 i 300 paraules. Incloure dates de visita en format DD/MM/AAAA, dosi, resposta clínica, efectes adversos si escau. Imitar l'estil real (paràgrafs curts, abreviatures hospitalàries, algunes incoherències menors típiques). Cap dada identificativa real.

2. `gold`: l'extracció correcta segons l'esquema adjunt.
   - `patient_id`: "{patient_id}"
   - Un DrugEntry per fàrmac distint. Usa el nom genèric/API en minúscules (ex: "fluoxetina", "liti", "quetiapina").
   - Dates al gold en ISO 8601 (AAAA-MM-DD). A la nota usa format hospitalari.
   - `dosi_min_mg_dia` = `dosi_max_mg_dia` si dosi estable. Diferents si hi ha rang o escalada.
   - `efectes_adversos`: llista buida [] si no n'hi ha.
   - `is_ongoing`: true si el tractament continua a l'última visita.
   - `motiu_discontinuacio`: null si `is_ongoing = true`.
   - `durada_mesos`: enter si tens dates completes; null altrament.
   - `dosi_notes`: null excepte si la dosi està en unitats no-mg (mg/kg, gotes, etc.).

IMPORTANT: el gold HA de reflectir exactament el que diu la nota.
"""


MODEL = "gemini-2.5-flash"
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5


def generate_one(client: genai.Client, pid: str, scenario: str) -> SyntheticPatient:
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=GENERATOR_PROMPT.format(scenario=scenario, patient_id=pid),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SyntheticPatient,
                    temperature=0.9,
                ),
            )
            patient: SyntheticPatient = response.parsed
            patient.gold.patient_id = pid
            return patient
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            if "503" in msg or "UNAVAILABLE" in msg or "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                wait = RETRY_BACKOFF_SECONDS * attempt
                print(f"  attempt {attempt} transient error, retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"exhausted retries: {last_exc}")


def main(n: int, out_root: Path) -> None:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    notes_dir = out_root / "data" / "synthetic" / "notes"
    gold_dir = out_root / "data" / "synthetic" / "gold"
    notes_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)

    for i in range(n):
        pid = f"synthetic_{i+1:03d}"
        scenario = SCENARIOS[i % len(SCENARIOS)]
        print(f"[{i+1}/{n}] {pid} — {scenario[:70]}...")
        try:
            patient = generate_one(client, pid, scenario)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue

        (notes_dir / f"{pid}.txt").write_text(patient.note_ca, encoding="utf-8")
        (gold_dir / f"{pid}.json").write_text(
            patient.gold.model_dump_json(indent=2),
            encoding="utf-8",
        )
        print(f"  ok — {len(patient.gold.drugs)} drug(s), note {len(patient.note_ca)} chars")

        time.sleep(2)

    print(f"\nDone. Output under {notes_dir.parent}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=10)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    main(args.n, repo_root)
