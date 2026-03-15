from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class ResumeHeader(BaseModel):
    full_name: str = Field(..., description="Imię i nazwisko kandydata")
    professional_headline: Optional[str] = Field(
        default=None,
        description="Krótki opis zawodowy pod nazwiskiem"
    )
    email: str = Field(..., description="Adres e-mail")
    phone: str = Field(..., description="Numer telefonu")
    location: str = Field(..., description="Lokalizacja kandydata")
    links: List[str] = Field(
        default_factory=list,
        description="Linki do LinkedIn, GitHub, portfolio itp."
    )


class ResumeExperienceEntry(BaseModel):
    source_experience_id: str = Field(
        ...,
        description="ID oryginalnego wpisu ExperienceEntry"
    )
    company_name: str = Field(..., description="Nazwa firmy")
    position_title: str = Field(..., description="Stanowisko")
    date_range: str = Field(..., description="Zakres dat do wyświetlenia")
    bullet_points: List[str] = Field(
        default_factory=list,
        description="Bullet pointy dopasowane do oferty"
    )
    highlighted_keywords: List[str] = Field(
        default_factory=list,
        description="Słowa kluczowe uwypuklone w tym wpisie"
    )


class ResumeProjectEntry(BaseModel):
    source_project_id: str = Field(
        ...,
        description="ID oryginalnego wpisu ProjectEntry"
    )
    project_name: str = Field(..., description="Nazwa projektu")
    role: str = Field(..., description="Rola w projekcie")
    bullet_points: List[str] = Field(
        default_factory=list,
        description="Opis projektu dopasowany do oferty"
    )
    highlighted_keywords: List[str] = Field(
        default_factory=list,
        description="Słowa kluczowe uwypuklone w projekcie"
    )


class ChangeReport(BaseModel):
    added_elements: List[str] = Field(
        default_factory=list,
        description="Elementy dodane do finalnej wersji CV"
    )
    emphasized_elements: List[str] = Field(
        default_factory=list,
        description="Elementy mocniej uwypuklone"
    )
    omitted_elements: List[str] = Field(
        default_factory=list,
        description="Elementy pominięte w finalnym CV"
    )
    omission_reasons: List[str] = Field(
        default_factory=list,
        description="Powody pominięcia elementów"
    )
    detected_keywords: List[str] = Field(
        default_factory=list,
        description="Słowa kluczowe wykryte w ofercie"
    )
    used_keywords: List[str] = Field(
        default_factory=list,
        description="Słowa kluczowe użyte w CV"
    )
    unused_keywords: List[str] = Field(
        default_factory=list,
        description="Słowa kluczowe niewykorzystane"
    )
    blocked_items: List[str] = Field(
        default_factory=list,
        description="Elementy zablokowane jako niepotwierdzone"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Ostrzeżenia dotyczące jakości dopasowania"
    )


class ResumeDraft(BaseModel):
    header: ResumeHeader
    professional_summary: Optional[str] = Field(
        default=None,
        description="Opcjonalne podsumowanie zawodowe"
    )
    selected_skills: List[str] = Field(
        default_factory=list,
        description="Wybrane umiejętności do CV"
    )
    selected_experience_entries: List[ResumeExperienceEntry] = Field(
        default_factory=list,
        description="Doświadczenia zawodowe wybrane do CV"
    )
    selected_project_entries: List[ResumeProjectEntry] = Field(
        default_factory=list,
        description="Projekty wybrane do CV"
    )
    selected_education_entries: List[str] = Field(
        default_factory=list,
        description="Edukacja wybrana do CV"
    )
    selected_language_entries: List[str] = Field(
        default_factory=list,
        description="Języki wybrane do CV"
    )
    selected_certificate_entries: List[str] = Field(
        default_factory=list,
        description="Certyfikaty wybrane do CV"
    )
    keyword_usage: List[str] = Field(
        default_factory=list,
        description="Lista słów kluczowych użytych w CV"
    )