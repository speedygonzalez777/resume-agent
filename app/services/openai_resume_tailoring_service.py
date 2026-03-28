"""OpenAI-backed truthful-first tailoring of ResumeDraft selections."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from app.models.candidate import CandidateProfile
from app.models.job import JobPosting
from app.models.match import MatchResult
from app.models.resume import ResumeFallbackReason
from app.prompts.resume_tailoring_prompt import RESUME_TAILORING_INSTRUCTIONS
from app.services.openai_candidate_profile_understanding_service import (
    CandidateProfileUnderstanding,
)

_DEFAULT_RESUME_TAILORING_MODEL = "gpt-5-mini"
_SAMPLING_CAPABLE_MODEL_PREFIXES = (
    "gpt-4.1",
    "gpt-4o",
    "gpt-4.5",
    "gpt-3.5",
)


class ResumeTailoringOpenAIError(Exception):
    """Raised when OpenAI resume tailoring cannot return a valid structured result."""

    def __init__(
        self,
        message: str,
        *,
        fallback_reason: ResumeFallbackReason,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.fallback_reason = fallback_reason
        self.details = details or {}


class OpenAIResumeExperienceSelection(BaseModel):
    """Structured AI output for one selected experience entry."""

    source_experience_id: str = Field(..., description="ID wybranego ExperienceEntry")
    tailored_bullets: list[str] = Field(
        default_factory=list,
        description="Lekko zredagowane bullet points oparte tylko na danym wpisie źródłowym",
    )
    highlighted_keywords: list[str] = Field(
        default_factory=list,
        description="Słowa kluczowe z oferty, które rzeczywiście mają pokrycie w tym wpisie",
    )
    relevance_note: str | None = Field(
        default=None,
        description="Krótka notatka, dlaczego wpis jest ważny dla tej oferty",
    )
    source_highlights: list[str] = Field(
        default_factory=list,
        description="Dosłowne krótkie fragmenty z doświadczenia źródłowego użyte jako podstawa redakcji",
    )


class OpenAIResumeProjectSelection(BaseModel):
    """Structured AI output for one selected project entry."""

    source_project_id: str = Field(..., description="ID wybranego ProjectEntry")
    tailored_bullets: list[str] = Field(
        default_factory=list,
        description="Lekko zredagowane bullet points oparte tylko na projekcie źródłowym",
    )
    highlighted_keywords: list[str] = Field(
        default_factory=list,
        description="Słowa kluczowe z oferty, które rzeczywiście mają pokrycie w tym projekcie",
    )
    relevance_note: str | None = Field(
        default=None,
        description="Krótka notatka, dlaczego projekt jest ważny dla tej oferty",
    )
    source_highlights: list[str] = Field(
        default_factory=list,
        description="Dosłowne krótkie fragmenty z projektu źródłowego użyte jako podstawa redakcji",
    )


class OpenAIResumeTailoringOutput(BaseModel):
    """Internal structured output returned by OpenAI for resume tailoring."""

    fit_summary: str | None = Field(
        default=None,
        description="Krótkie podsumowanie głównego dopasowania i tonu draftu",
    )
    professional_summary: str | None = Field(
        default=None,
        description="Podsumowanie zawodowe dopasowane do oferty, ale oparte wyłącznie na danych wejściowych",
    )
    selected_skills: list[str] = Field(
        default_factory=list,
        description="Najważniejsze umiejętności kandydata do wyeksponowania",
    )
    selected_keywords: list[str] = Field(
        default_factory=list,
        description="Słowa kluczowe z oferty, które warto wyeksponować w draftcie",
    )
    selected_experience_entries: list[OpenAIResumeExperienceSelection] = Field(default_factory=list)
    selected_project_entries: list[OpenAIResumeProjectSelection] = Field(default_factory=list)
    selected_education_entries: list[str] = Field(
        default_factory=list,
        description="Wybrane wpisy edukacyjne dokładnie odpowiadające supplied options",
    )
    selected_language_entries: list[str] = Field(
        default_factory=list,
        description="Wybrane wpisy językowe dokładnie odpowiadające supplied options",
    )
    selected_certificate_entries: list[str] = Field(
        default_factory=list,
        description="Wybrane wpisy certyfikatów dokładnie odpowiadające supplied options",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Krótkie ostrzeżenia użytkowe przy słabszym dopasowaniu lub brakach danych",
    )
    truthfulness_notes: list[str] = Field(
        default_factory=list,
        description="Krótkie notatki o ograniczeniach truthful-first i pominiętych roszczeniach",
    )
    omitted_or_deemphasized_items: list[str] = Field(
        default_factory=list,
        description="Krótkie notatki o świadomie pominiętych lub zdeemfatyzowanych elementach",
    )


def generate_resume_tailoring_with_openai(
    candidate_profile: CandidateProfile,
    job_posting: JobPosting,
    match_result: MatchResult,
    *,
    candidate_profile_understanding: CandidateProfileUnderstanding | None = None,
) -> OpenAIResumeTailoringOutput:
    """Generate structured, truthful-first resume tailoring hints with OpenAI."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "tu_wkleisz_swoj_klucz":
        raise ResumeTailoringOpenAIError(
            "OpenAI API key is missing. Falling back to deterministic resume generation.",
            fallback_reason=ResumeFallbackReason.MISSING_API_KEY,
        )

    model_name = os.getenv("OPENAI_RESUME_TAILORING_MODEL", _DEFAULT_RESUME_TAILORING_MODEL)
    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.parse(
            **_build_responses_parse_kwargs(
                candidate_profile,
                job_posting,
                match_result,
                model_name,
                candidate_profile_understanding,
            )
        )
    except ResumeTailoringOpenAIError:
        raise
    except OpenAIError as exc:
        raise ResumeTailoringOpenAIError(
            "OpenAI resume tailoring failed. Falling back to deterministic resume generation.",
            fallback_reason=ResumeFallbackReason.OPENAI_ERROR,
            details={"model": model_name, "reason": str(exc)},
        ) from exc
    except Exception as exc:
        raise ResumeTailoringOpenAIError(
            "Unexpected OpenAI resume tailoring failure. Falling back to deterministic resume generation.",
            fallback_reason=ResumeFallbackReason.OPENAI_ERROR,
            details={"model": model_name, "reason": str(exc)},
        ) from exc

    structured_output = response.output_parsed
    if structured_output is None:
        raise ResumeTailoringOpenAIError(
            "OpenAI returned no structured resume tailoring output. Falling back to deterministic resume generation.",
            fallback_reason=ResumeFallbackReason.INVALID_AI_OUTPUT,
            details={"model": model_name},
        )

    return structured_output


def _build_responses_parse_kwargs(
    candidate_profile: CandidateProfile,
    job_posting: JobPosting,
    match_result: MatchResult,
    model_name: str,
    candidate_profile_understanding: CandidateProfileUnderstanding | None = None,
) -> dict[str, Any]:
    """Build the OpenAI Responses API payload for structured resume tailoring."""

    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "instructions": RESUME_TAILORING_INSTRUCTIONS,
        "input": _build_resume_tailoring_input(
            candidate_profile,
            job_posting,
            match_result,
            candidate_profile_understanding,
        ),
        "text_format": OpenAIResumeTailoringOutput,
    }
    request_kwargs.update(_build_optional_parse_kwargs(model_name))
    return request_kwargs


def _build_resume_tailoring_input(
    candidate_profile: CandidateProfile,
    job_posting: JobPosting,
    match_result: MatchResult,
    candidate_profile_understanding: CandidateProfileUnderstanding | None = None,
) -> str:
    """Build a compact but traceable evidence pack sent to the model."""

    experience_options = [
        {
            "id": entry.id,
            "company_name": entry.company_name,
            "position_title": entry.position_title,
            "start_date": entry.start_date,
            "end_date": entry.end_date,
            "is_current": entry.is_current,
            "location": entry.location,
            "responsibilities": entry.responsibilities,
            "achievements": entry.achievements,
            "technologies_used": entry.technologies_used,
            "keywords": entry.keywords,
        }
        for entry in candidate_profile.experience_entries
    ]
    project_options = [
        {
            "id": entry.id,
            "project_name": entry.project_name,
            "role": entry.role,
            "description": entry.description,
            "technologies_used": entry.technologies_used,
            "outcomes": entry.outcomes,
            "keywords": entry.keywords,
            "link": str(entry.link) if entry.link else None,
        }
        for entry in candidate_profile.project_entries
    ]
    education_options = [
        {
            "institution_name": entry.institution_name,
            "degree": entry.degree,
            "field_of_study": entry.field_of_study,
            "start_date": entry.start_date,
            "end_date": entry.end_date,
            "is_current": entry.is_current,
        }
        for entry in candidate_profile.education_entries
    ]
    language_options = [
        {
            "language_name": entry.language_name,
            "proficiency_level": entry.proficiency_level,
        }
        for entry in candidate_profile.language_entries
    ]
    certificate_options = [
        {
            "certificate_name": entry.certificate_name,
            "issuer": entry.issuer,
            "issue_date": entry.issue_date,
            "notes": entry.notes,
        }
        for entry in candidate_profile.certificate_entries
    ]

    evidence_pack = {
        "candidate_profile": {
            "personal_info": candidate_profile.personal_info.model_dump(mode="json"),
            "target_roles": candidate_profile.target_roles,
            "professional_summary_base": candidate_profile.professional_summary_base,
            "experience_entries": experience_options,
            "project_entries": project_options,
            "skill_entries": [entry.model_dump(mode="json") for entry in candidate_profile.skill_entries],
            "education_entries": education_options,
            "language_entries": language_options,
            "certificate_entries": certificate_options,
            "immutable_rules": candidate_profile.immutable_rules.model_dump(mode="json"),
        },
        "job_posting": job_posting.model_dump(mode="json"),
        "match_result": match_result.model_dump(mode="json"),
        "candidate_profile_understanding": (
            candidate_profile_understanding.model_dump(mode="json")
            if candidate_profile_understanding is not None
            else None
        ),
        "selection_options": {
            "education_entries": education_options,
            "language_entries": language_options,
            "certificate_entries": certificate_options,
        },
    }

    return (
        "Generate a truthful-first tailored resume draft from this JSON evidence pack.\n\n"
        f"{json.dumps(evidence_pack, ensure_ascii=False, indent=2)}"
    )


def _build_optional_parse_kwargs(model_name: str) -> dict[str, Any]:
    """Add optional sampling params only for model families that support them."""

    optional_kwargs: dict[str, Any] = {}

    if _model_supports_sampling_params(model_name):
        temperature = _read_optional_float_env(
            "OPENAI_RESUME_TAILORING_TEMPERATURE",
            min_value=0.0,
            max_value=2.0,
        )
        if temperature is not None:
            optional_kwargs["temperature"] = temperature

        top_p = _read_optional_float_env(
            "OPENAI_RESUME_TAILORING_TOP_P",
            min_value=0.0,
            max_value=1.0,
        )
        if top_p is not None:
            optional_kwargs["top_p"] = top_p

    return optional_kwargs


def _model_supports_sampling_params(model_name: str) -> bool:
    """Return whether the selected model family supports explicit sampling params."""

    normalized_model_name = model_name.strip().lower()
    return normalized_model_name.startswith(_SAMPLING_CAPABLE_MODEL_PREFIXES)


def _read_optional_float_env(
    env_name: str,
    *,
    min_value: float,
    max_value: float,
) -> float | None:
    """Read an optional float env var and validate its allowed range."""

    raw_value = os.getenv(env_name)
    if raw_value is None or raw_value.strip() == "":
        return None

    try:
        parsed_value = float(raw_value)
    except ValueError as exc:
        raise ResumeTailoringOpenAIError(
            f"Invalid value for {env_name}. Falling back to deterministic resume generation.",
            fallback_reason=ResumeFallbackReason.OPENAI_ERROR,
            details={"env_name": env_name, "value": raw_value},
        ) from exc

    if parsed_value < min_value or parsed_value > max_value:
        raise ResumeTailoringOpenAIError(
            f"Invalid value for {env_name}. Falling back to deterministic resume generation.",
            fallback_reason=ResumeFallbackReason.OPENAI_ERROR,
            details={"env_name": env_name, "value": raw_value},
        )

    return parsed_value
