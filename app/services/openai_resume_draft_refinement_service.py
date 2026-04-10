"""OpenAI-backed refinement patch generation for an existing ResumeDraft."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI, OpenAIError

from app.models.resume import (
    ResumeDraft,
    ResumeDraftRefinementGuidance,
    ResumeDraftRefinementPatch,
)
from app.prompts.resume_draft_refinement_prompt import (
    RESUME_DRAFT_REFINEMENT_INSTRUCTIONS,
)
from app.services.openai_model_resolver import resolve_resume_refinement_model

_SAMPLING_CAPABLE_MODEL_PREFIXES = (
    "gpt-4.1",
    "gpt-4o",
    "gpt-4.5",
    "gpt-3.5",
)


class ResumeDraftRefinementOpenAIError(Exception):
    """Raised when OpenAI draft refinement cannot return a valid structured patch."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def generate_resume_draft_refinement_patch_with_openai(
    resume_draft: ResumeDraft,
    guidance: ResumeDraftRefinementGuidance,
) -> ResumeDraftRefinementPatch:
    """Generate a structured refinement patch for an existing ResumeDraft."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "tu_wkleisz_swoj_klucz":
        raise ResumeDraftRefinementOpenAIError(
            "OpenAI API key is missing. AI CV refinement is unavailable.",
            status_code=503,
        )

    model_name = resolve_resume_refinement_model()
    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.parse(
            **_build_responses_parse_kwargs(resume_draft, guidance, model_name)
        )
    except ResumeDraftRefinementOpenAIError:
        raise
    except OpenAIError as exc:
        raise ResumeDraftRefinementOpenAIError(
            "OpenAI draft refinement failed.",
            status_code=502,
            details={"model": model_name, "reason": str(exc)},
        ) from exc
    except Exception as exc:
        raise ResumeDraftRefinementOpenAIError(
            "Unexpected OpenAI draft refinement failure.",
            status_code=502,
            details={"model": model_name, "reason": str(exc)},
        ) from exc

    structured_output = response.output_parsed
    if structured_output is None:
        raise ResumeDraftRefinementOpenAIError(
            "OpenAI returned no structured draft refinement patch.",
            status_code=502,
            details={"model": model_name},
        )

    return structured_output


def _build_responses_parse_kwargs(
    resume_draft: ResumeDraft,
    guidance: ResumeDraftRefinementGuidance,
    model_name: str,
) -> dict[str, Any]:
    """Build the OpenAI Responses API payload for structured draft refinement."""

    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "instructions": RESUME_DRAFT_REFINEMENT_INSTRUCTIONS,
        "input": _build_resume_draft_refinement_input(resume_draft, guidance),
        "text_format": ResumeDraftRefinementPatch,
    }
    request_kwargs.update(_build_optional_parse_kwargs(model_name))
    return request_kwargs


def _build_resume_draft_refinement_input(
    resume_draft: ResumeDraft,
    guidance: ResumeDraftRefinementGuidance,
) -> str:
    """Build a compact JSON evidence pack for patch-only draft refinement."""

    refinement_input = {
        "base_resume_draft": {
            "target_job_title": resume_draft.target_job_title,
            "target_company_name": resume_draft.target_company_name,
            "fit_summary": resume_draft.fit_summary,
            "editable_fields": {
                "header": {
                    "professional_headline": resume_draft.header.professional_headline,
                },
                "professional_summary": resume_draft.professional_summary,
                "selected_skills": resume_draft.selected_skills,
                "selected_keywords": resume_draft.selected_keywords,
                "keyword_usage": resume_draft.keyword_usage,
                "selected_experience_entries": [
                    {
                        "source_experience_id": entry.source_experience_id,
                        "bullet_points": entry.bullet_points,
                        "highlighted_keywords": entry.highlighted_keywords,
                    }
                    for entry in resume_draft.selected_experience_entries
                ],
                "selected_project_entries": [
                    {
                        "source_project_id": entry.source_project_id,
                        "bullet_points": entry.bullet_points,
                        "highlighted_keywords": entry.highlighted_keywords,
                    }
                    for entry in resume_draft.selected_project_entries
                ],
            },
            "read_only_context": {
                "experience_entries": [
                    {
                        "source_experience_id": entry.source_experience_id,
                        "company_name": entry.company_name,
                        "position_title": entry.position_title,
                        "date_range": entry.date_range,
                        "relevance_note": entry.relevance_note,
                        "source_highlights": entry.source_highlights,
                    }
                    for entry in resume_draft.selected_experience_entries
                ],
                "project_entries": [
                    {
                        "source_project_id": entry.source_project_id,
                        "project_name": entry.project_name,
                        "role": entry.role,
                        "relevance_note": entry.relevance_note,
                        "source_highlights": entry.source_highlights,
                    }
                    for entry in resume_draft.selected_project_entries
                ],
                "selected_education_entries": resume_draft.selected_education_entries,
                "selected_language_entries": resume_draft.selected_language_entries,
                "selected_certificate_entries": resume_draft.selected_certificate_entries,
            },
        },
        "guidance": guidance.model_dump(mode="json"),
        "immutable_fields": {
            "header": [
                "full_name",
                "email",
                "phone",
                "location",
                "links",
            ],
            "top_level": [
                "target_job_title",
                "target_company_name",
                "fit_summary",
                "selected_education_entries",
                "selected_language_entries",
                "selected_certificate_entries",
            ],
            "experience_entry": [
                "source_experience_id",
                "company_name",
                "position_title",
                "date_range",
                "relevance_note",
                "source_highlights",
            ],
            "project_entry": [
                "source_project_id",
                "project_name",
                "role",
                "relevance_note",
                "source_highlights",
            ],
        },
    }

    return (
        "Return only a structured refinement patch for this already generated resume draft.\n\n"
        f"{json.dumps(refinement_input, ensure_ascii=False, indent=2)}"
    )


def _build_optional_parse_kwargs(model_name: str) -> dict[str, Any]:
    """Add optional sampling params only for model families that support them."""

    optional_kwargs: dict[str, Any] = {}

    if _model_supports_sampling_params(model_name):
        temperature = _read_optional_float_env(
            "OPENAI_RESUME_DRAFT_REFINEMENT_TEMPERATURE",
            min_value=0.0,
            max_value=2.0,
        )
        if temperature is not None:
            optional_kwargs["temperature"] = temperature

        top_p = _read_optional_float_env(
            "OPENAI_RESUME_DRAFT_REFINEMENT_TOP_P",
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
        raise ResumeDraftRefinementOpenAIError(
            f"Invalid value for {env_name}.",
            status_code=500,
            details={"env_name": env_name, "value": raw_value},
        ) from exc

    if parsed_value < min_value or parsed_value > max_value:
        raise ResumeDraftRefinementOpenAIError(
            f"Invalid value for {env_name}.",
            status_code=500,
            details={"env_name": env_name, "value": raw_value},
        )

    return parsed_value
