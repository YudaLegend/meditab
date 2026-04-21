"""Day 2 smoke test: one fake note, one Gemini call, print the response.

Goal: confirm the environment + API key + SDK all work end-to-end.
No structure, no Pydantic, no Mongo — those come in later days.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

REPO_ROOT = Path(__file__).resolve().parent.parent
note_path = REPO_ROOT / "data" / "synthetic" / "notes" / "patient_001.txt"
note_text = note_path.read_text(encoding="utf-8")

prompt = f"""Ets un extractor d'informació clínica. Llegeix la següent nota clínica en català i resumeix, en text lliure, els fàrmacs mencionats amb dosi, dates i resposta clínica.

Nota clínica:
{note_text}
"""

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
)

print("=" * 60)
print("RESPONSE:")
print("=" * 60)
print(response.text)
