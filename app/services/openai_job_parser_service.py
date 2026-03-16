"""OpenAI-backed parser that turns fetched page content into a JobPosting."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from app.models.job import JobPosting
from app.prompts.job_posting_parse_prompt import JOB_POSTING_PARSE_INSTRUCTIONS
from app.services.job_page_fetch_service import FetchedJobPage
from app.services.job_parse_errors import AIJobParsingFailedError

_DEFAULT_JOB_PARSER_MODEL = "gpt-5-mini"
_SAMPLING_CAPABLE_MODEL_PREFIXES = (
    "gpt-4.1",
    "gpt-4o",
    "gpt-4.5",
    "gpt-3.5",
)


def parse_job_posting_with_openai(fetched_page: FetchedJobPage) -> JobPosting:
    """Parse a fetched job page into a structured JobPosting via Responses API.

    Args:
        fetched_page: Page content already fetched and cleaned by the backend.

    Returns:
        Structured JobPosting parsed from the fetched page content.
    """
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "tu_wkleisz_swoj_klucz":
        raise AIJobParsingFailedError(
            "OpenAI API key is missing. Set OPENAI_API_KEY before using /job/parse-url."
        )

    model_name = os.getenv("OPENAI_JOB_PARSER_MODEL", _DEFAULT_JOB_PARSER_MODEL)
    client = OpenAI(api_key=api_key)
    request_kwargs = _build_responses_parse_kwargs(fetched_page, model_name)

    try:
        response = client.responses.parse(**request_kwargs)
    except AIJobParsingFailedError:
        raise
    except OpenAIError as exc:
        raise AIJobParsingFailedError(
            "OpenAI failed to parse the fetched job page into JobPosting.",
            details={"model": model_name, "reason": str(exc)},
        ) from exc
    except Exception as exc:
        raise AIJobParsingFailedError(
            "Unexpected error while parsing the fetched job page with OpenAI.",
            details={"model": model_name, "reason": str(exc)},
        ) from exc

    job_posting = response.output_parsed
    if job_posting is None:
        raise AIJobParsingFailedError(
            "OpenAI returned no structured JobPosting output.",
            details={"model": model_name},
        )

    return job_posting


def _build_responses_parse_kwargs(
    fetched_page: FetchedJobPage,
    model_name: str,
) -> dict[str, Any]:
    """Build the request payload for OpenAI structured parsing."""
    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "instructions": JOB_POSTING_PARSE_INSTRUCTIONS,
        "input": fetched_page.build_ai_input(),
        "text_format": JobPosting,
    }
    request_kwargs.update(_build_optional_parse_kwargs(model_name))
    return request_kwargs


def _build_optional_parse_kwargs(model_name: str) -> dict[str, Any]:
    """Add optional sampling parameters only for models that support them."""
    optional_kwargs: dict[str, Any] = {}

    if _model_supports_sampling_params(model_name):
        temperature = _read_optional_float_env(
            "OPENAI_JOB_PARSER_TEMPERATURE",
            min_value=0.0,
            max_value=2.0,
        )
        if temperature is not None:
            optional_kwargs["temperature"] = temperature

        top_p = _read_optional_float_env(
            "OPENAI_JOB_PARSER_TOP_P",
            min_value=0.0,
            max_value=1.0,
        )
        if top_p is not None:
            optional_kwargs["top_p"] = top_p

    return optional_kwargs


def _model_supports_sampling_params(model_name: str) -> bool:
    """Return whether a model family supports explicit sampling parameters."""
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
        raise AIJobParsingFailedError(
            f"Invalid value for {env_name}. Expected a float.",
            details={"env_name": env_name, "value": raw_value},
        ) from exc

    if parsed_value < min_value or parsed_value > max_value:
        raise AIJobParsingFailedError(
            f"Invalid value for {env_name}. Expected a float between {min_value} and {max_value}.",
            details={"env_name": env_name, "value": raw_value},
        )

    return parsed_value
