from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class Requirement(BaseModel):
    id: str = Field(..., description="Unikalny identyfikator wymagania")
    text: str = Field(..., description="Pełna treść wymagania")
    category: str = Field(
        ...,
        description="Kategoria wymagania, np. technology, experience, language, education"
    )
    requirement_type: str = Field(
        ...,
        description="Typ wymagania: must_have albo nice_to_have"
    )
    importance: str = Field(
        ...,
        description="Ważność wymagania, np. high, medium, low"
    )
    extracted_keywords: List[str] = Field(
        default_factory=list,
        description="Słowa kluczowe wyciągnięte z wymagania"
    )


class JobPosting(BaseModel):
    source: str = Field(
        ...,
        description="Źródło oferty, np. pracuj, jooble, justjoinit, rocketjobs, manual"
    )
    title: str = Field(..., description="Tytuł stanowiska")
    company_name: str = Field(..., description="Nazwa firmy")
    location: str = Field(..., description="Lokalizacja pracy")
    work_mode: Optional[str] = Field(
        default=None,
        description="Tryb pracy, np. onsite, hybrid, remote"
    )
    employment_type: Optional[str] = Field(
        default=None,
        description="Typ zatrudnienia, np. UoP, B2B, staż, zlecenie"
    )
    seniority_level: Optional[str] = Field(
        default=None,
        description="Poziom stanowiska, np. junior, mid, senior"
    )
    role_summary: Optional[str] = Field(
        default=None,
        description="Krótki opis roli lub stanowiska"
    )
    responsibilities: List[str] = Field(
        default_factory=list,
        description="Lista obowiązków z ogłoszenia"
    )
    requirements: List[Requirement] = Field(
        default_factory=list,
        description="Lista wymagań z ogłoszenia"
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="Lista słów kluczowych wykrytych w ogłoszeniu"
    )
    language_of_offer: Optional[str] = Field(
        default=None,
        description="Język oferty pracy"
    )