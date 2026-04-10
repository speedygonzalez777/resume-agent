from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ResumeGenerationMode(str, Enum):
    OPENAI_STRUCTURED = "openai_structured"
    RULE_BASED_FALLBACK = "rule_based_fallback"


class ResumeMatchResultSource(str, Enum):
    PROVIDED = "provided"
    COMPUTED = "computed"


class ResumeFallbackReason(str, Enum):
    MISSING_API_KEY = "missing_api_key"
    OPENAI_ERROR = "openai_error"
    INVALID_AI_OUTPUT = "invalid_ai_output"


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
    relevance_note: Optional[str] = Field(
        default=None,
        description="Krótka notatka wyjaśniająca, dlaczego wpis został wybrany"
    )
    source_highlights: List[str] = Field(
        default_factory=list,
        description="Krótkie fragmenty źródłowe z profilu, na których oparto redakcję wpisu"
    )


class ResumeProjectEntry(BaseModel):
    source_project_id: str = Field(
        ...,
        description="ID oryginalnego wpisu ProjectEntry"
    )
    project_name: str = Field(..., description="Nazwa projektu")
    role: str = Field(..., description="Rola w projekcie")
    link: Optional[str] = Field(
        default=None,
        description="Opcjonalny link do projektu"
    )
    bullet_points: List[str] = Field(
        default_factory=list,
        description="Opis projektu dopasowany do oferty"
    )
    highlighted_keywords: List[str] = Field(
        default_factory=list,
        description="Słowa kluczowe uwypuklone w projekcie"
    )
    relevance_note: Optional[str] = Field(
        default=None,
        description="Krótka notatka wyjaśniająca, dlaczego projekt został wybrany"
    )
    source_highlights: List[str] = Field(
        default_factory=list,
        description="Krótkie fragmenty źródłowe z profilu, na których oparto redakcję projektu"
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
    target_job_title: Optional[str] = Field(
        default=None,
        description="Tytuł stanowiska, pod które przygotowano draft CV"
    )
    target_company_name: Optional[str] = Field(
        default=None,
        description="Nazwa firmy, pod którą przygotowano draft CV"
    )
    fit_summary: Optional[str] = Field(
        default=None,
        description="Krótkie podsumowanie dopasowania i akcentów draftu"
    )
    professional_summary: Optional[str] = Field(
        default=None,
        description="Opcjonalne podsumowanie zawodowe"
    )
    selected_skills: List[str] = Field(
        default_factory=list,
        description="Wybrane umiejętności do CV"
    )
    selected_soft_skill_entries: List[str] = Field(
        default_factory=list,
        description="Jawnie wpisane soft skills przeniesione do draftu CV"
    )
    selected_interest_entries: List[str] = Field(
        default_factory=list,
        description="Jawnie wpisane obszary zainteresowań przeniesione do draftu CV"
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
    selected_keywords: List[str] = Field(
        default_factory=list,
        description="Wybrane słowa kluczowe z oferty, które warto eksponować w draftcie"
    )
    keyword_usage: List[str] = Field(
        default_factory=list,
        description="Lista słów kluczowych użytych w CV"
    )


class ResumeDraftRefinementGuidance(BaseModel):
    must_include_terms: List[str] = Field(
        default_factory=list,
        description="Terminy, ktore model powinien wyeksponowac w poprawionym drafcie, jesli sa juz uczciwie pokryte w bazowym resume_draft"
    )
    avoid_or_deemphasize_terms: List[str] = Field(
        default_factory=list,
        description="Terminy, ktorych nie nalezy promowac w poprawionym drafcie CV"
    )
    forbidden_claims_or_phrases: List[str] = Field(
        default_factory=list,
        description="Frazy i twierdzenia, ktore nie moga pojawic sie w poprawionym drafcie CV"
    )
    skills_allowlist: List[str] = Field(
        default_factory=list,
        description="Allowlista dla selected_skills; pusta lista oznacza brak ograniczenia"
    )
    additional_instructions: Optional[str] = Field(
        default=None,
        description="Opcjonalne dodatkowe wskazowki redakcyjne dla etapu AI refinement"
    )


class ResumeHeaderRefinementPatch(BaseModel):
    professional_headline: Optional[str] = Field(
        default=None,
        description="Nowa wartosc header.professional_headline; null oznacza brak zmiany"
    )


class ResumeExperienceEntryRefinementPatch(BaseModel):
    source_experience_id: str = Field(
        ...,
        description="ID wpisu ResumeExperienceEntry, ktorego pola maja zostac nadpisane"
    )
    bullet_points: Optional[List[str]] = Field(
        default=None,
        description="Nowe bullet_points dla wskazanego wpisu; null oznacza brak zmiany"
    )
    highlighted_keywords: Optional[List[str]] = Field(
        default=None,
        description="Nowe highlighted_keywords dla wskazanego wpisu; null oznacza brak zmiany"
    )


class ResumeProjectEntryRefinementPatch(BaseModel):
    source_project_id: str = Field(
        ...,
        description="ID wpisu ResumeProjectEntry, ktorego pola maja zostac nadpisane"
    )
    bullet_points: Optional[List[str]] = Field(
        default=None,
        description="Nowe bullet_points dla wskazanego projektu; null oznacza brak zmiany"
    )
    highlighted_keywords: Optional[List[str]] = Field(
        default=None,
        description="Nowe highlighted_keywords dla wskazanego projektu; null oznacza brak zmiany"
    )


class ResumeDraftRefinementPatch(BaseModel):
    header: Optional[ResumeHeaderRefinementPatch] = Field(
        default=None,
        description="Patch dla wybranych pol header; null oznacza brak zmian w header"
    )
    professional_summary: Optional[str] = Field(
        default=None,
        description="Nowa wartosc professional_summary; null oznacza brak zmiany"
    )
    selected_skills: Optional[List[str]] = Field(
        default=None,
        description="Nowa wartosc selected_skills; null oznacza brak zmiany"
    )
    selected_keywords: Optional[List[str]] = Field(
        default=None,
        description="Nowa wartosc selected_keywords; null oznacza brak zmiany"
    )
    keyword_usage: Optional[List[str]] = Field(
        default=None,
        description="Nowa wartosc keyword_usage; null oznacza brak zmiany"
    )
    selected_experience_entries: List[ResumeExperienceEntryRefinementPatch] = Field(
        default_factory=list,
        description="Lista patchy dla juz wybranych ResumeExperienceEntry"
    )
    selected_project_entries: List[ResumeProjectEntryRefinementPatch] = Field(
        default_factory=list,
        description="Lista patchy dla juz wybranych ResumeProjectEntry"
    )
