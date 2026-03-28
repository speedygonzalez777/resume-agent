from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr, HttpUrl


class PersonalInfo(BaseModel):
    full_name: str = Field(..., description="Imię i nazwisko kandydata")
    email: EmailStr = Field(..., description="Adres e-mail")
    phone: str = Field(..., description="Numer telefonu")
    linkedin_url: Optional[HttpUrl] = Field(default=None, description="Link do LinkedIn")
    github_url: Optional[HttpUrl] = Field(default=None, description="Link do GitHub")
    portfolio_url: Optional[HttpUrl] = Field(default=None, description="Link do portfolio")
    location: str = Field(..., description="Lokalizacja kandydata")


class ExperienceEntry(BaseModel):
    id: str = Field(..., description="Unikalny identyfikator wpisu doświadczenia")
    company_name: str = Field(..., description="Nazwa firmy")
    position_title: str = Field(..., description="Nazwa stanowiska")
    start_date: str = Field(..., description="Data rozpoczęcia")
    end_date: Optional[str] = Field(default=None, description="Data zakończenia")
    is_current: bool = Field(default=False, description="Czy to aktualne stanowisko")
    location: str = Field(..., description="Lokalizacja pracy")
    responsibilities: List[str] = Field(default_factory=list, description="Lista obowiązków")
    achievements: List[str] = Field(default_factory=list, description="Lista osiągnięć")
    technologies_used: List[str] = Field(default_factory=list, description="Użyte technologie")
    keywords: List[str] = Field(default_factory=list, description="Dodatkowe słowa kluczowe")


class ProjectEntry(BaseModel):
    id: str = Field(..., description="Unikalny identyfikator projektu")
    project_name: str = Field(..., description="Nazwa projektu")
    role: str = Field(..., description="Rola kandydata w projekcie")
    description: str = Field(..., description="Krótki opis projektu")
    technologies_used: List[str] = Field(default_factory=list, description="Użyte technologie")
    outcomes: List[str] = Field(default_factory=list, description="Rezultaty projektu")
    keywords: List[str] = Field(default_factory=list, description="Słowa kluczowe projektu")
    link: Optional[HttpUrl] = Field(default=None, description="Link do projektu")


class SkillEntry(BaseModel):
    name: str = Field(..., description="Nazwa umiejętności")
    category: str = Field(..., description="Kategoria umiejętności")
    level: str = Field(..., description="Poziom znajomości")
    years_of_experience: Optional[float] = Field(default=None, description="Lata doświadczenia")
    evidence_sources: List[str] = Field(
        default_factory=list,
        description="ID doświadczeń lub projektów potwierdzających umiejętność"
    )
    aliases: List[str] = Field(default_factory=list, description="Alternatywne nazwy umiejętności")


class EducationEntry(BaseModel):
    institution_name: str = Field(..., description="Nazwa uczelni lub szkoły")
    degree: str = Field(..., description="Stopień wykształcenia")
    field_of_study: str = Field(..., description="Kierunek lub specjalizacja")
    start_date: str = Field(..., description="Data rozpoczęcia")
    end_date: Optional[str] = Field(default=None, description="Data zakończenia")
    is_current: bool = Field(default=False, description="Czy edukacja nadal trwa")


class LanguageEntry(BaseModel):
    language_name: str = Field(..., description="Nazwa języka")
    proficiency_level: str = Field(..., description="Poziom znajomości języka")


class CertificateEntry(BaseModel):
    certificate_name: str = Field(..., description="Nazwa certyfikatu lub kursu")
    issuer: str = Field(..., description="Organizacja wydająca")
    issue_date: Optional[str] = Field(default=None, description="Data uzyskania")
    notes: Optional[str] = Field(default=None, description="Dodatkowe informacje")


class ImmutableRules(BaseModel):
    forbidden_skills: List[str] = Field(default_factory=list, description="Zakazane umiejętności do dopisywania")
    forbidden_claims: List[str] = Field(default_factory=list, description="Zakazane stwierdzenia")
    forbidden_certificates: List[str] = Field(default_factory=list, description="Zakazane certyfikaty")
    editing_rules: List[str] = Field(default_factory=list, description="Zasady edycji treści")


class CandidateProfile(BaseModel):
    personal_info: PersonalInfo
    target_roles: List[str] = Field(default_factory=list, description="Docelowe role zawodowe")
    professional_summary_base: str = Field(..., description="Bazowe podsumowanie zawodowe")
    soft_skill_entries: List[str] = Field(default_factory=list, description="Jawnie wpisane umiejetnosci miekkie")
    interest_entries: List[str] = Field(default_factory=list, description="Jawnie wpisane obszary zainteresowan")
    experience_entries: List[ExperienceEntry] = Field(default_factory=list)
    project_entries: List[ProjectEntry] = Field(default_factory=list)
    skill_entries: List[SkillEntry] = Field(default_factory=list)
    education_entries: List[EducationEntry] = Field(default_factory=list)
    language_entries: List[LanguageEntry] = Field(default_factory=list)
    certificate_entries: List[CertificateEntry] = Field(default_factory=list)
    immutable_rules: ImmutableRules = Field(default_factory=ImmutableRules)
