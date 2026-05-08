"""OpenAI-backed prioritization of the full requirement list into core/supporting/low-signal tiers."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from app.models.job import JobPosting, Requirement
from app.prompts.requirement_priority_prompt import REQUIREMENT_PRIORITY_INSTRUCTIONS
from app.services.openai_model_resolver import resolve_matching_model

_SAMPLING_CAPABLE_MODEL_PREFIXES = (
    "gpt-4.1",
    "gpt-4o",
    "gpt-4.5",
    "gpt-3.5",
)
_PRIORITY_TIER_ORDER = {
    "core": 0,
    "supporting": 1,
    "low_signal": 2,
}
_REQUIREMENT_TYPE_ORDER = {
    "must_have": 0,
    "nice_to_have": 1,
}
_IMPORTANCE_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
}
_CONFIDENCE_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
}
_PRIORITY_TIERS = ("core", "supporting", "low_signal")


class RequirementPriorityOpenAIError(Exception):
    """Raised when requirement prioritization cannot return a safe structured result."""

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


class OpenAIRequirementPriorityItem(BaseModel):
    """Structured priority metadata for one requirement."""

    requirement_id: str = Field(..., description="Requirement ID taken from the parsed offer.")
    priority_tier: Literal["core", "supporting", "low_signal"] = Field(
        ...,
        description="Relative importance of the requirement within the whole offer.",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Model confidence in this relative-priority judgment.",
    )
    reasoning_note: str = Field(
        ...,
        description="One short grounded sentence explaining the assigned priority tier.",
    )


class OpenAIRequirementPriorityOutput(BaseModel):
    """Structured output for job-level requirement prioritization."""

    items: list[OpenAIRequirementPriorityItem] = Field(
        default_factory=list,
        description="One priority item per supplied requirement.",
    )


def evaluate_requirement_priorities_with_openai(
    job_posting: JobPosting,
) -> OpenAIRequirementPriorityOutput:
    """Prioritize the whole requirement list using a structured OpenAI call."""

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "tu_wkleisz_swoj_klucz":
        raise RequirementPriorityOpenAIError(
            "OpenAI API key is missing. Skipping requirement prioritization.",
            reason="missing_api_key",
        )

    model_name = resolve_matching_model(
        legacy_env_name="OPENAI_REQUIREMENT_PRIORITY_MODEL",
    )
    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.parse(
            **_build_responses_parse_kwargs(job_posting, model_name)
        )
    except OpenAIError as exc:
        raise RequirementPriorityOpenAIError(
            "OpenAI requirement prioritization failed. Skipping priority layer.",
            reason="openai_error",
            details={"model": model_name, "reason": str(exc)},
        ) from exc
    except Exception as exc:
        raise RequirementPriorityOpenAIError(
            "Unexpected OpenAI requirement prioritization failure. Skipping priority layer.",
            reason="openai_error",
            details={"model": model_name, "reason": str(exc)},
        ) from exc

    structured_output = response.output_parsed
    if structured_output is None:
        raise RequirementPriorityOpenAIError(
            "OpenAI returned no structured requirement prioritization output. Skipping priority layer.",
            reason="invalid_ai_output",
            details={"model": model_name},
        )

    _validate_requirement_priority_output(job_posting, structured_output)
    return structured_output


def get_requirement_priority_lookup(
    job_posting: JobPosting,
) -> dict[str, OpenAIRequirementPriorityItem]:
    """Return a safe priority lookup or an empty map when AI prioritization is unavailable."""

    try:
        output = evaluate_requirement_priorities_with_openai(job_posting)
    except RequirementPriorityOpenAIError:
        return {}

    return {item.requirement_id: item for item in output.items}


def count_requirement_priority_tiers(
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> dict[str, int]:
    """Count how many requirements landed in each AI priority tier."""

    tier_counts = {tier: 0 for tier in _PRIORITY_TIERS}
    for item in priority_lookup.values():
        if item.priority_tier in tier_counts:
            tier_counts[item.priority_tier] += 1
    return tier_counts


def build_requirement_priority_sort_key(
    requirement: Requirement,
    original_index: int,
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> tuple[int, int, int, int, int]:
    """Build a stable ordering key that prefers core then supporting then low-signal requirements."""

    item = priority_lookup.get(requirement.id)
    if item is None:
        return (3, 1, 1, 1, original_index)

    return (
        _PRIORITY_TIER_ORDER.get(item.priority_tier, 1),
        _REQUIREMENT_TYPE_ORDER.get((requirement.requirement_type or "").strip().lower(), 1),
        _IMPORTANCE_ORDER.get((requirement.importance or "").strip().lower(), 1),
        _CONFIDENCE_ORDER.get(item.confidence, 1),
        original_index,
    )


def _build_responses_parse_kwargs(
    job_posting: JobPosting,
    model_name: str,
) -> dict[str, Any]:
    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "instructions": REQUIREMENT_PRIORITY_INSTRUCTIONS,
        "input": _build_requirement_priority_input(job_posting),
        "text_format": OpenAIRequirementPriorityOutput,
    }
    request_kwargs.update(_build_optional_parse_kwargs(model_name))
    return request_kwargs


def _build_requirement_priority_input(job_posting: JobPosting) -> str:
    evidence_pack = {
        "job_context": {
            "title": job_posting.title,
            "company_name": job_posting.company_name,
            "seniority_level": job_posting.seniority_level,
            "employment_type": job_posting.employment_type,
            "work_mode": job_posting.work_mode,
            "role_summary": job_posting.role_summary,
            "responsibilities": job_posting.responsibilities,
        },
        "requirements": [
            {
                "id": requirement.id,
                "text": requirement.text,
                "category": requirement.category,
                "requirement_type": requirement.requirement_type,
                "importance": requirement.importance,
                "extracted_keywords": requirement.extracted_keywords,
            }
            for requirement in job_posting.requirements
        ],
    }

    return (
        "Prioritize the full requirement list of this job posting into relative importance tiers. "
        "Do not evaluate the candidate. Return one structured priority item per requirement ID.\n\n"
        f"{json.dumps(evidence_pack, ensure_ascii=False, indent=2)}"
    )


def _validate_requirement_priority_output(
    job_posting: JobPosting,
    output: OpenAIRequirementPriorityOutput,
) -> None:
    expected_ids = [requirement.id for requirement in job_posting.requirements]
    returned_ids = [item.requirement_id for item in output.items]

    if len(returned_ids) != len(expected_ids):
        raise RequirementPriorityOpenAIError(
            "OpenAI returned an incomplete requirement prioritization output. Skipping priority layer.",
            reason="invalid_ai_output",
            details={"expected_ids": expected_ids, "returned_ids": returned_ids},
        )

    duplicate_ids = [requirement_id for requirement_id in returned_ids if returned_ids.count(requirement_id) > 1]
    unknown_ids = [requirement_id for requirement_id in returned_ids if requirement_id not in expected_ids]
    missing_ids = [requirement_id for requirement_id in expected_ids if requirement_id not in returned_ids]
    if duplicate_ids or unknown_ids or missing_ids:
        raise RequirementPriorityOpenAIError(
            "OpenAI returned invalid requirement IDs in the prioritization output. Skipping priority layer.",
            reason="invalid_ai_output",
            details={
                "duplicate_ids": sorted(set(duplicate_ids)),
                "unknown_ids": sorted(set(unknown_ids)),
                "missing_ids": sorted(set(missing_ids)),
            },
        )


def _build_optional_parse_kwargs(model_name: str) -> dict[str, Any]:
    optional_kwargs: dict[str, Any] = {}

    if _model_supports_sampling_params(model_name):
        temperature = _read_optional_float_env(
            "OPENAI_REQUIREMENT_PRIORITY_TEMPERATURE",
            min_value=0.0,
            max_value=2.0,
        )
        if temperature is not None:
            optional_kwargs["temperature"] = temperature

        top_p = _read_optional_float_env(
            "OPENAI_REQUIREMENT_PRIORITY_TOP_P",
            min_value=0.0,
            max_value=1.0,
        )
        if top_p is not None:
            optional_kwargs["top_p"] = top_p

    return optional_kwargs


def _model_supports_sampling_params(model_name: str) -> bool:
    normalized_model_name = model_name.strip().lower()
    return normalized_model_name.startswith(_SAMPLING_CAPABLE_MODEL_PREFIXES)


def _read_optional_float_env(
    env_name: str,
    *,
    min_value: float,
    max_value: float,
) -> float | None:
    raw_value = os.getenv(env_name)
    if raw_value is None or raw_value.strip() == "":
        return None

    try:
        parsed_value = float(raw_value)
    except ValueError as exc:
        raise RequirementPriorityOpenAIError(
            f"Invalid value for {env_name}. Skipping priority layer.",
            reason="openai_error",
            details={"env_name": env_name, "value": raw_value},
        ) from exc

    if parsed_value < min_value or parsed_value > max_value:
        raise RequirementPriorityOpenAIError(
            f"Invalid value for {env_name}. Skipping priority layer.",
            reason="openai_error",
            details={"env_name": env_name, "value": raw_value},
        )

    return parsed_value
