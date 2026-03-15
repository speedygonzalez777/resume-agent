from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class RequirementMatch(BaseModel):
    requirement_id: str = Field(..., description="ID wymagania z oferty")
    match_status: str = Field(
        ...,
        description="Status dopasowania: matched, partial, missing"
    )
    matched_experience_ids: List[str] = Field(
        default_factory=list,
        description="ID doświadczeń potwierdzających wymaganie"
    )
    matched_project_ids: List[str] = Field(
        default_factory=list,
        description="ID projektów potwierdzających wymaganie"
    )
    matched_skill_names: List[str] = Field(
        default_factory=list,
        description="Nazwy umiejętności powiązanych z wymaganiem"
    )
    evidence_texts: List[str] = Field(
        default_factory=list,
        description="Krótkie uzasadnienie dopasowania"
    )
    explanation: str = Field(
        ...,
        description="Opis, dlaczego wymaganie uznano za matched, partial albo missing"
    )
    missing_elements: List[str] = Field(
        default_factory=list,
        description="Brakujące elementy potrzebne do pełnego spełnienia wymagania"
    )


class MatchResult(BaseModel):
    overall_score: float = Field(
        ...,
        description="Ogólny wynik dopasowania w skali 0.0-1.0"
    )
    fit_classification: str = Field(
        ...,
        description="Klasyfikacja dopasowania: high, medium, low"
    )
    recommendation: str = Field(
        ...,
        description="Rekomendacja: generate, generate_with_caution, do_not_recommend"
    )
    requirement_matches: List[RequirementMatch] = Field(
        default_factory=list,
        description="Lista dopasowań dla wszystkich wymagań"
    )
    strengths: List[str] = Field(
        default_factory=list,
        description="Mocne strony kandydata względem oferty"
    )
    gaps: List[str] = Field(
        default_factory=list,
        description="Luki względem wymagań oferty"
    )
    keyword_coverage: List[str] = Field(
        default_factory=list,
        description="Lista słów kluczowych pokrytych w profilu kandydata"
    )
    final_summary: str = Field(
        ...,
        description="Końcowe podsumowanie dopasowania"
    )