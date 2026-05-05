"""OpenAI-backed fitter that compresses a final ResumeDraft into a TypstPayload."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI, OpenAIError

from app.models.typst import TypstPayload
from app.prompts.resume_typst_fitter_prompt import RESUME_TYPST_FITTER_INSTRUCTIONS
from app.services.openai_model_resolver import resolve_typst_fitter_model

_SAMPLING_CAPABLE_MODEL_PREFIXES = (
    "gpt-4.1",
    "gpt-4o",
    "gpt-4.5",
    "gpt-3.5",
)


class ResumeTypstFitterOpenAIError(Exception):
    """Raised when the Typst fitter cannot return a valid structured payload."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


@dataclass(frozen=True)
class ResumeTypstFitterResult:
    """Structured Typst fitter result together with the resolved model name."""

    typst_payload: TypstPayload
    model_name: str


def generate_typst_payload_with_openai(
    fitter_input: dict[str, Any],
    *,
    retry_feedback: str | None = None,
) -> ResumeTypstFitterResult:
    """Generate a structured TypstPayload from a compact draft-centric evidence pack."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "tu_wkleisz_swoj_klucz":
        raise ResumeTypstFitterOpenAIError(
            "OpenAI API key is missing. Typst payload fitting is unavailable.",
            status_code=503,
        )

    model_name = resolve_typst_fitter_model()
    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.parse(
            **_build_responses_parse_kwargs(
                fitter_input,
                model_name=model_name,
                retry_feedback=retry_feedback,
            )
        )
    except OpenAIError as exc:
        raise ResumeTypstFitterOpenAIError(
            "OpenAI Typst fitter request failed.",
            status_code=502,
            details={"model": model_name, "reason": str(exc)},
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive unexpected wrapper
        raise ResumeTypstFitterOpenAIError(
            "Unexpected Typst fitter failure.",
            status_code=502,
            details={"model": model_name, "reason": str(exc)},
        ) from exc

    structured_output = response.output_parsed
    if structured_output is None:
        raise ResumeTypstFitterOpenAIError(
            "OpenAI returned no structured Typst payload.",
            status_code=502,
            details={"model": model_name},
        )

    return ResumeTypstFitterResult(
        typst_payload=TypstPayload.model_validate(structured_output),
        model_name=model_name,
    )


def _build_responses_parse_kwargs(
    fitter_input: dict[str, Any],
    *,
    model_name: str,
    retry_feedback: str | None,
) -> dict[str, Any]:
    """Build the Responses API payload for the Typst fitter."""

    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "instructions": RESUME_TYPST_FITTER_INSTRUCTIONS,
        "input": _build_fitter_input_payload(
            fitter_input,
            retry_feedback=retry_feedback,
        ),
        "text_format": TypstPayload,
    }
    request_kwargs.update(_build_optional_parse_kwargs(model_name))
    return request_kwargs


def _build_fitter_input_payload(
    fitter_input: dict[str, Any],
    *,
    retry_feedback: str | None,
) -> str:
    """Serialize the compact fitter evidence pack for the model."""

    evidence_pack: dict[str, Any] = {
        "task": "Prepare a truthful-first TypstPayload for the fixed cv_one_page template.",
        "fitter_input": fitter_input,
    }
    if retry_feedback:
        evidence_pack["validation_feedback"] = retry_feedback

    return (
        "Generate a structured TypstPayload from this JSON evidence pack.\n\n"
        f"{json.dumps(evidence_pack, ensure_ascii=False, indent=2)}"
    )


def _build_optional_parse_kwargs(model_name: str) -> dict[str, Any]:
    """Add optional sampling params only for model families that support them."""

    optional_kwargs: dict[str, Any] = {}

    if _model_supports_sampling_params(model_name):
        temperature = _read_optional_float_env(
            "OPENAI_TYPST_FITTER_TEMPERATURE",
            min_value=0.0,
            max_value=2.0,
        )
        if temperature is not None:
            optional_kwargs["temperature"] = temperature

        top_p = _read_optional_float_env(
            "OPENAI_TYPST_FITTER_TOP_P",
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
    except ValueError:
        return None

    if parsed_value < min_value or parsed_value > max_value:
        return None

    return parsed_value
