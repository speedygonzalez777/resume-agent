"""OpenAI-backed classification of one requirement into a normalized matching type."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from app.models.job import JobPosting, Requirement
from app.prompts.requirement_type_classification_prompt import (
    REQUIREMENT_TYPE_CLASSIFICATION_INSTRUCTIONS,
)
from app.services.openai_model_resolver import resolve_matching_model

_SAMPLING_CAPABLE_MODEL_PREFIXES = (
    "gpt-4.1",
    "gpt-4o",
    "gpt-4.5",
    "gpt-3.5",
)


class RequirementTypeClassificationOpenAIError(Exception):
    """Raised when requirement-type classification cannot return a safe structured result."""

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


class OpenAIRequirementTypeClassificationOutput(BaseModel):
    """Structured AI output for one requirement-type classification."""

    normalized_requirement_type: Literal[
        "technical_skill",
        "experience",
        "education",
        "language",
        "application_constraint",
        "soft_signal",
        "low_signal",
    ] = Field(
        ...,
        description="Normalized requirement type used by the matcher dispatcher.",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Model confidence in the normalized requirement type.",
    )
    reasoning_note: str = Field(
        ...,
        description="One short grounded note explaining the classification.",
    )


def evaluate_requirement_type_with_openai(
    requirement: Requirement,
    job_posting: JobPosting,
) -> OpenAIRequirementTypeClassificationOutput:
    """Classify one requirement into a normalized type using a structured OpenAI call."""

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "tu_wkleisz_swoj_klucz":
        raise RequirementTypeClassificationOpenAIError(
            "OpenAI API key is missing. Falling back to heuristic requirement classification.",
            reason="missing_api_key",
        )

    model_name = resolve_matching_model(
        legacy_env_name="OPENAI_REQUIREMENT_TYPE_MODEL",
    )
    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.parse(
            **_build_responses_parse_kwargs(
                requirement,
                job_posting,
                model_name,
            )
        )
    except OpenAIError as exc:
        raise RequirementTypeClassificationOpenAIError(
            "OpenAI requirement classification failed. Falling back to heuristic requirement classification.",
            reason="openai_error",
            details={"model": model_name, "reason": str(exc)},
        ) from exc
    except Exception as exc:
        raise RequirementTypeClassificationOpenAIError(
            "Unexpected OpenAI requirement classification failure. Falling back to heuristic requirement classification.",
            reason="openai_error",
            details={"model": model_name, "reason": str(exc)},
        ) from exc

    structured_output = response.output_parsed
    if structured_output is None:
        raise RequirementTypeClassificationOpenAIError(
            "OpenAI returned no structured requirement classification output. Falling back to heuristic requirement classification.",
            reason="invalid_ai_output",
            details={"model": model_name},
        )

    return structured_output


def _build_responses_parse_kwargs(
    requirement: Requirement,
    job_posting: JobPosting,
    model_name: str,
) -> dict[str, Any]:
    """Build the structured Responses API payload for one requirement-type classification."""

    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "instructions": REQUIREMENT_TYPE_CLASSIFICATION_INSTRUCTIONS,
        "input": _build_requirement_type_input(requirement, job_posting),
        "text_format": OpenAIRequirementTypeClassificationOutput,
    }
    request_kwargs.update(_build_optional_parse_kwargs(model_name))
    return request_kwargs


def _build_requirement_type_input(requirement: Requirement, job_posting: JobPosting) -> str:
    """Build a compact job-and-requirement pack for the classifier."""

    evidence_pack = {
        "job_context": {
            "title": job_posting.title,
            "company_name": job_posting.company_name,
            "seniority_level": job_posting.seniority_level,
            "employment_type": job_posting.employment_type,
            "work_mode": job_posting.work_mode,
            "role_summary": job_posting.role_summary,
        },
        "requirement": requirement.model_dump(mode="json"),
    }

    return (
        "Classify this single job requirement into one normalized requirement type. "
        "Do not evaluate candidate fit. Return a grounded structured result only.\n\n"
        f"{json.dumps(evidence_pack, ensure_ascii=False, indent=2)}"
    )


def _build_optional_parse_kwargs(model_name: str) -> dict[str, Any]:
    """Add optional sampling params only for supported model families."""

    optional_kwargs: dict[str, Any] = {}

    if _model_supports_sampling_params(model_name):
        temperature = _read_optional_float_env(
            "OPENAI_REQUIREMENT_TYPE_TEMPERATURE",
            min_value=0.0,
            max_value=2.0,
        )
        if temperature is not None:
            optional_kwargs["temperature"] = temperature

        top_p = _read_optional_float_env(
            "OPENAI_REQUIREMENT_TYPE_TOP_P",
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
        raise RequirementTypeClassificationOpenAIError(
            f"Invalid value for {env_name}. Falling back to heuristic requirement classification.",
            reason="openai_error",
            details={"env_name": env_name, "value": raw_value},
        ) from exc

    if parsed_value < min_value or parsed_value > max_value:
        raise RequirementTypeClassificationOpenAIError(
            f"Invalid value for {env_name}. Falling back to heuristic requirement classification.",
            reason="openai_error",
            details={"env_name": env_name, "value": raw_value},
        )

    return parsed_value
