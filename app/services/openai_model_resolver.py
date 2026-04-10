"""Resolve OpenAI model names per workflow with backward-compatible env fallbacks."""

from __future__ import annotations

import os

_DEFAULT_JOB_PARSING_MODEL = "gpt-5-mini"
_DEFAULT_MATCHING_MODEL = "gpt-5.4"
_DEFAULT_RESUME_GENERATION_MODEL = "gpt-5.4"
_DEFAULT_RESUME_REFINEMENT_MODEL = "gpt-5-mini"


def resolve_job_parsing_model() -> str:
    """Resolve the model used for job parsing."""

    return _resolve_model_name(
        "OPENAI_JOB_PARSER_MODEL",
        default=_DEFAULT_JOB_PARSING_MODEL,
    )


def resolve_matching_model(*, legacy_env_name: str) -> str:
    """Resolve the model used by all matching-side AI helpers."""

    return _resolve_model_name(
        "OPENAI_MATCHING_MODEL",
        legacy_env_name,
        default=_DEFAULT_MATCHING_MODEL,
    )


def resolve_resume_generation_model(*, legacy_env_name: str) -> str:
    """Resolve the model used for base resume generation."""

    return _resolve_model_name(
        "OPENAI_RESUME_GENERATION_MODEL",
        legacy_env_name,
        default=_DEFAULT_RESUME_GENERATION_MODEL,
    )


def resolve_resume_refinement_model() -> str:
    """Resolve the model used for draft refinement."""

    return _resolve_model_name(
        "OPENAI_RESUME_DRAFT_REFINEMENT_MODEL",
        default=_DEFAULT_RESUME_REFINEMENT_MODEL,
    )


def _resolve_model_name(*env_names: str, default: str) -> str:
    """Return the first non-empty env value, otherwise the workflow default."""

    for env_name in env_names:
        raw_value = os.getenv(env_name)
        if raw_value is None:
            continue

        normalized_value = raw_value.strip()
        if normalized_value:
            return normalized_value

    return default
