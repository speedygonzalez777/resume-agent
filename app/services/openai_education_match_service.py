"""OpenAI-backed truthful-first evaluation of one education requirement."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from app.models.candidate import CandidateProfile
from app.models.job import JobPosting, Requirement
from app.models.match import RequirementMatch
from app.prompts.education_requirement_match_prompt import (
    EDUCATION_REQUIREMENT_MATCH_INSTRUCTIONS,
)
from app.services.openai_model_resolver import resolve_matching_model

_SAMPLING_CAPABLE_MODEL_PREFIXES = (
    "gpt-4.1",
    "gpt-4o",
    "gpt-4.5",
    "gpt-3.5",
)
_WHITESPACE_RE = re.compile(r"\s+")


class EducationRequirementMatchOpenAIError(Exception):
    """Raised when OpenAI education matching cannot return a safe structured result."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.details = details or {}


class OpenAIEducationEvidenceRef(BaseModel):
    """One grounded education reference returned by the model."""

    source_type: Literal["education"] = Field(
        ...,
        description="Typ źródła dowodu. Dla tego etapu zawsze education.",
    )
    source_id: str = Field(..., description="ID education option wybrane z dostarczonej listy")
    supporting_snippet: str = Field(
        ...,
        description="Krótki fragment skopiowany z dostarczonego education option",
    )


class OpenAIEducationRequirementMatchOutput(BaseModel):
    """Structured AI output for one education requirement."""

    suggested_status: Literal["matched", "partial", "missing", "not_verifiable"] = Field(
        ...,
        description="Sugerowany status dopasowania requirementu edukacyjnego.",
    )
    grounding_strength: Literal["strong", "moderate", "weak"] = Field(
        ...,
        description="Siła ugruntowania werdyktu w dostarczonych education entries.",
    )
    match_kind: Literal[
        "exact_degree_match",
        "related_technical_field",
        "broad_stem_match",
        "generic_degree_match",
        "no_supported_match",
        "insufficient_information",
    ] = Field(
        ...,
        description="Rodzaj dopasowania edukacyjnego albo brak wsparcia dowodowego.",
    )
    explanation: str = Field(
        ...,
        description="Krótki, user-facing opis oceny oparty wyłącznie na danych wejściowych.",
    )
    missing_elements: list[str] = Field(
        default_factory=list,
        description="Konkretne brakujące elementy potrzebne do lepszego dopasowania.",
    )
    evidence_refs: list[OpenAIEducationEvidenceRef] = Field(
        default_factory=list,
        description="Lista ugruntowanych refs do dostarczonych education entries.",
    )


def evaluate_education_requirement_with_openai(
    requirement: Requirement,
    candidate_profile: CandidateProfile,
    job_posting: JobPosting,
    deterministic_match: RequirementMatch,
) -> OpenAIEducationRequirementMatchOutput:
    """Evaluate one education requirement with a structured, grounded OpenAI call."""

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "tu_wkleisz_swoj_klucz":
        raise EducationRequirementMatchOpenAIError(
            "OpenAI API key is missing. Falling back to deterministic education matching.",
            reason="missing_api_key",
        )

    model_name = resolve_matching_model(
        legacy_env_name="OPENAI_EDUCATION_MATCH_MODEL",
    )
    client = OpenAI(api_key=api_key)
    education_options = _build_education_options(candidate_profile)

    try:
        response = client.responses.parse(
            **_build_responses_parse_kwargs(
                requirement,
                candidate_profile,
                job_posting,
                deterministic_match,
                education_options,
                model_name,
            )
        )
    except OpenAIError as exc:
        raise EducationRequirementMatchOpenAIError(
            "OpenAI education matching failed. Falling back to deterministic education matching.",
            reason="openai_error",
            details={"model": model_name, "reason": str(exc)},
        ) from exc
    except Exception as exc:
        raise EducationRequirementMatchOpenAIError(
            "Unexpected OpenAI education matching failure. Falling back to deterministic education matching.",
            reason="openai_error",
            details={"model": model_name, "reason": str(exc)},
        ) from exc

    structured_output = response.output_parsed
    if structured_output is None:
        raise EducationRequirementMatchOpenAIError(
            "OpenAI returned no structured education-matching output. Falling back to deterministic education matching.",
            reason="invalid_ai_output",
            details={"model": model_name},
        )

    _validate_grounding(structured_output, education_options)
    return structured_output


def _build_responses_parse_kwargs(
    requirement: Requirement,
    candidate_profile: CandidateProfile,
    job_posting: JobPosting,
    deterministic_match: RequirementMatch,
    education_options: list[dict[str, Any]],
    model_name: str,
) -> dict[str, Any]:
    """Build the structured Responses API payload for one education requirement."""

    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "instructions": EDUCATION_REQUIREMENT_MATCH_INSTRUCTIONS,
        "input": _build_education_match_input(
            requirement,
            candidate_profile,
            job_posting,
            deterministic_match,
            education_options,
        ),
        "text_format": OpenAIEducationRequirementMatchOutput,
    }
    request_kwargs.update(_build_optional_parse_kwargs(model_name))
    return request_kwargs


def _build_education_match_input(
    requirement: Requirement,
    candidate_profile: CandidateProfile,
    job_posting: JobPosting,
    deterministic_match: RequirementMatch,
    education_options: list[dict[str, Any]],
) -> str:
    """Build a compact evidence pack for one education requirement."""

    evidence_pack = {
        "job_context": {
            "title": job_posting.title,
            "company_name": job_posting.company_name,
            "role_summary": job_posting.role_summary,
            "seniority_level": job_posting.seniority_level,
        },
        "requirement": requirement.model_dump(mode="json"),
        "deterministic_baseline": {
            "status": deterministic_match.match_status,
            "explanation": deterministic_match.explanation,
            "missing_elements": deterministic_match.missing_elements,
        },
        "candidate_context": {
            "target_roles": candidate_profile.target_roles,
            "professional_summary_base": candidate_profile.professional_summary_base,
        },
        "education_options": education_options,
    }

    return (
        "Assess this single education requirement from the supplied JSON evidence pack. "
        "Return a grounded structured result only.\n\n"
        f"{json.dumps(evidence_pack, ensure_ascii=False, indent=2)}"
    )


def _build_education_options(candidate_profile: CandidateProfile) -> list[dict[str, Any]]:
    """Build deterministic education options with stable source IDs for grounding."""

    options: list[dict[str, Any]] = []
    for index, entry in enumerate(candidate_profile.education_entries, start=1):
        source_excerpt = _build_source_excerpt(
            entry.degree,
            entry.field_of_study,
            entry.institution_name,
        )
        options.append(
            {
                "source_id": _build_education_source_id(index),
                "source_type": "education",
                "institution_name": entry.institution_name,
                "degree": entry.degree,
                "field_of_study": entry.field_of_study,
                "start_date": entry.start_date,
                "end_date": entry.end_date,
                "is_current": entry.is_current,
                "source_excerpt": source_excerpt,
            }
        )
    return options


def _build_education_source_id(index: int) -> str:
    """Build a stable source ID for one education option."""

    return f"education_{index:03d}"


def _build_source_excerpt(degree: str, field_of_study: str, institution_name: str) -> str:
    """Build the canonical short text that AI snippets must point back to."""

    parts = [part.strip() for part in [degree, field_of_study, institution_name] if part and part.strip()]
    return " | ".join(parts)


def _validate_grounding(
    structured_output: OpenAIEducationRequirementMatchOutput,
    education_options: list[dict[str, Any]],
) -> None:
    """Validate that the AI output points only to allowed education evidence."""

    option_index = {option["source_id"]: option for option in education_options}

    if structured_output.suggested_status in {"matched", "partial"} and not structured_output.evidence_refs:
        raise EducationRequirementMatchOpenAIError(
            "OpenAI returned an education match without grounded evidence refs.",
            reason="invalid_ai_grounding",
        )

    for evidence_ref in structured_output.evidence_refs:
        if evidence_ref.source_type != "education":
            raise EducationRequirementMatchOpenAIError(
                "OpenAI returned an unsupported evidence source type for education matching.",
                reason="invalid_ai_grounding",
                details={"source_type": evidence_ref.source_type},
            )

        option = option_index.get(evidence_ref.source_id)
        if option is None:
            raise EducationRequirementMatchOpenAIError(
                "OpenAI returned an unknown education source ID.",
                reason="invalid_ai_grounding",
                details={"source_id": evidence_ref.source_id},
            )

        if _normalize_grounding_text(evidence_ref.supporting_snippet) not in _normalize_grounding_text(option["source_excerpt"]):
            raise EducationRequirementMatchOpenAIError(
                "OpenAI returned an ungrounded education snippet.",
                reason="invalid_ai_grounding",
                details={
                    "source_id": evidence_ref.source_id,
                    "supporting_snippet": evidence_ref.supporting_snippet,
                },
            )


def _normalize_grounding_text(value: str) -> str:
    """Normalize text for snippet-in-source validation."""

    return _WHITESPACE_RE.sub(" ", value.strip().lower())


def _build_optional_parse_kwargs(model_name: str) -> dict[str, Any]:
    """Add optional sampling params only for supported model families."""

    optional_kwargs: dict[str, Any] = {}

    if _model_supports_sampling_params(model_name):
        temperature = _read_optional_float_env(
            "OPENAI_EDUCATION_MATCH_TEMPERATURE",
            min_value=0.0,
            max_value=2.0,
        )
        if temperature is not None:
            optional_kwargs["temperature"] = temperature

        top_p = _read_optional_float_env(
            "OPENAI_EDUCATION_MATCH_TOP_P",
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
        raise EducationRequirementMatchOpenAIError(
            f"Invalid value for {env_name}. Falling back to deterministic education matching.",
            reason="openai_error",
            details={"env_name": env_name, "value": raw_value},
        ) from exc

    if parsed_value < min_value or parsed_value > max_value:
        raise EducationRequirementMatchOpenAIError(
            f"Invalid value for {env_name}. Falling back to deterministic education matching.",
            reason="openai_error",
            details={"env_name": env_name, "value": raw_value},
        )

    return parsed_value
