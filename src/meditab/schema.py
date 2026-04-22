"""Meditab extraction schema.

This is the single source of truth for what a patient extraction looks like.
Both the LLM (via `response_schema`) and the local validator (via
`model_validate`) consume these models. Every downstream step — prompts,
Mongo documents, evaluation — depends on this shape.

Reference: docs/annotation_schema.md (v1, 2026-04-21).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self


# ------------------------------ AdverseEffect ------------------------------


class AdverseEffect(BaseModel):
    """One adverse effect attributed to a drug."""

    descripcio: str = Field(
        description="Free-text Catalan description of the adverse effect, "
        "e.g. 'tremolor fi', 'disfunció sexual', 'sedació diürna'.",
    )
    persistent: Literal["persistent", "no persistent"] | None = Field(
        default=None,
        description="Whether the effect persisted through follow-up. "
        "null if the notes do not state it.",
    )
    severitat: Literal["lleu", "moderada", "greu"] | None = Field(
        default=None,
        description="Severity as stated by the clinician. null if not stated.",
    )

    # TODO (optional): @field_validator("descripcio") to strip whitespace and
    # reject empty strings. Think about whether the LLM could ever legitimately
    # return "" here — if not, it's worth failing fast.


# -------------------------------- DrugEntry --------------------------------


class DrugEntry(BaseModel):
    """One (patient, generic drug) row. All visits for the same drug merge here."""

    farmac: str = Field(
        description="Lowercase generic name / active principle (API). "
        "Brand names must be normalized, e.g. 'Prozac' → 'fluoxetina'.",
    )
    categoria: str = Field(
        description="Descriptive therapeutic class as written by the clinician, "
        "e.g. 'Antidepressiu (ISRS)', 'Estabilitzador d''humor'.",
    )
    dosi_min_mg_dia: float | None = Field(
        default=None,
        description="Lower bound of daily dose in mg. Equal to dosi_max_mg_dia "
        "if the dose is stable. null if dose is absent or in non-mg units "
        "(see dosi_notes).",
    )
    dosi_max_mg_dia: float | None = Field(
        default=None,
        description="Upper bound of daily dose in mg. For dose escalation over "
        "time, this is the highest dose reached.",
    )
    dosi_notes: str | None = Field(
        default=None,
        description="Original dose string ONLY when the dose is in non-mg units "
        "(mg/kg, IU, gotes). null otherwise.",
    )
    data_inici: date | None = Field(
        default=None,
        description="Start date, ISO 8601 (YYYY-MM-DD). If only month/year are "
        "known, use day 01 and note the imprecision in resposta_clinica.",
    )
    data_fi: date | None = Field(
        default=None,
        description="End date, ISO 8601. null if treatment is ongoing OR if the "
        "end date is unknown (see is_ongoing).",
    )
    is_ongoing: bool = Field(
        description="true if the drug is still being taken at the last note.",
    )
    durada_mesos: int | None = Field(
        default=None,
        description="Months between data_inici and data_fi. null if either "
        "boundary date is null.",
    )
    resposta_clinica: str | None = Field(
        default=None,
        description="Concise Catalan summary of the clinical response across "
        "visits. Also used to flag imprecise dates or ambiguous AE attribution.",
    )
    efectes_adversos: list[AdverseEffect] = Field(
        default_factory=list,
        description="List of adverse effects. Empty list [] if none — never null.",
    )
    motiu_discontinuacio: str | None = Field(
        default=None,
        description="Free-text reason treatment was stopped. null when "
        "is_ongoing=true. May still be null when is_ongoing=false if the "
        "reason is not stated in the notes.",
    )

    # --- field-level validators ---

    @field_validator("farmac")
    @classmethod
    def _normalize_farmac(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("farmac must be non-empty")
        return v

    @field_validator("dosi_min_mg_dia", "dosi_max_mg_dia")
    @classmethod
    def _check_dose_positive(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError(f"dose must be positive, got {v}")
        return v


    # --- cross-field validators ---

    @model_validator(mode="after")
    def _check_dose_order(self) -> Self:
        if self.dosi_min_mg_dia is not None and self.dosi_max_mg_dia is not None:
            if self.dosi_min_mg_dia > self.dosi_max_mg_dia:
                raise ValueError(
                    f"dosi_min_mg_dia ({self.dosi_min_mg_dia}) must be <= "
                    f"dosi_max_mg_dia ({self.dosi_max_mg_dia})"
                )
        return self

    @model_validator(mode="after")
    def _check_date_order(self) -> Self:
        if self.data_inici is not None and self.data_fi is not None:
            if self.data_inici > self.data_fi:
                raise ValueError(
                    f"data_inici ({self.data_inici}) must be <= "
                    f"data_fi ({self.data_fi})"
                )
        return self

    @model_validator(mode="after")
    def _check_ongoing_consistency(self) -> Self:
        if self.is_ongoing:
            if self.motiu_discontinuacio is not None:
                raise ValueError(
                    "motiu_discontinuacio must be null when is_ongoing=True "
                    f"(got {self.motiu_discontinuacio!r})"
                )
            if self.data_fi is not None:
                raise ValueError(
                    f"data_fi must be null when is_ongoing=True (got {self.data_fi})"
                )
        return self

    @model_validator(mode="after")
    def _check_duration_consistency(self) -> Self:
        if (
            self.data_inici is not None
            and self.data_fi is not None
            and self.durada_mesos is not None
        ):
            computed = (
                (self.data_fi.year - self.data_inici.year) * 12
                + (self.data_fi.month - self.data_inici.month)
            )
            if abs(self.durada_mesos - computed) > 1:
                raise ValueError(
                    f"durada_mesos ({self.durada_mesos}) inconsistent with "
                    f"{self.data_inici} → {self.data_fi} (computed {computed})"
                )
        return self

    @model_validator(mode="after")
    def _check_dose_unit_consistency(self) -> Self:
        if self.dosi_notes is not None:
            if self.dosi_min_mg_dia is not None or self.dosi_max_mg_dia is not None:
                raise ValueError(
                    "dosi_notes is set (non-mg units) — both dosi_min_mg_dia "
                    "and dosi_max_mg_dia must be null"
                )
        return self


# ----------------------------- PatientExtraction ---------------------------


class PatientExtraction(BaseModel):
    """Top-level gold/extraction document for one patient."""

    patient_id: str = Field(
        description="Stable identifier matching the source note filename stem.",
    )
    drugs: list[DrugEntry] = Field(
        description="One entry per distinct (patient, generic drug). Empty if "
        "the patient has no pharmacological treatment recorded.",
    )

    @model_validator(mode="after")
    def _check_unique_drugs(self) -> Self:
        seen: set[str] = set()
        dups: list[str] = []
        for d in self.drugs:
            if d.farmac in seen:
                dups.append(d.farmac)
            else:
                seen.add(d.farmac)
        if dups:
            raise ValueError(
                f"duplicate farmac entries (one row per drug required): {dups}"
            )
        return self
