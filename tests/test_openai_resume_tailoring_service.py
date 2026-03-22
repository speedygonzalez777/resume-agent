from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.analysis import MatchAnalysisRequest
from app.models.resume import ResumeFallbackReason
from app.services.match_service import analyze_match_basic
from app.services.openai_resume_tailoring_service import (
    OpenAIResumeTailoringOutput,
    ResumeTailoringOpenAIError,
    generate_resume_tailoring_with_openai,
)

_MATCH_PAYLOAD_FIXTURE = Path("data/match_analysis_test.json")


def test_generate_resume_tailoring_with_openai_omits_sampling_params_by_default(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_output = _build_tailoring_output()
    request = _load_request()
    match_result = analyze_match_basic(request)

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.delenv("OPENAI_RESUME_TAILORING_TEMPERATURE", raising=False)
    monkeypatch.delenv("OPENAI_RESUME_TAILORING_TOP_P", raising=False)
    monkeypatch.setenv("OPENAI_RESUME_TAILORING_MODEL", "gpt-5-mini")
    monkeypatch.setattr("app.services.openai_resume_tailoring_service.OpenAI", FakeOpenAI)

    result = generate_resume_tailoring_with_openai(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )

    assert result == expected_output
    assert captured_kwargs["model"] == "gpt-5-mini"
    assert captured_kwargs["text_format"] is OpenAIResumeTailoringOutput
    assert "temperature" not in captured_kwargs
    assert "top_p" not in captured_kwargs


def test_generate_resume_tailoring_with_openai_ignores_sampling_params_for_unsupported_model(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_output = _build_tailoring_output()
    request = _load_request()
    match_result = analyze_match_basic(request)

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_RESUME_TAILORING_MODEL", "gpt-5-mini")
    monkeypatch.setenv("OPENAI_RESUME_TAILORING_TEMPERATURE", "0.3")
    monkeypatch.setenv("OPENAI_RESUME_TAILORING_TOP_P", "0.7")
    monkeypatch.setattr("app.services.openai_resume_tailoring_service.OpenAI", FakeOpenAI)

    result = generate_resume_tailoring_with_openai(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )

    assert result == expected_output
    assert "temperature" not in captured_kwargs
    assert "top_p" not in captured_kwargs


def test_generate_resume_tailoring_with_openai_includes_sampling_params_for_supported_model(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_output = _build_tailoring_output()
    request = _load_request()
    match_result = analyze_match_basic(request)

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_RESUME_TAILORING_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_RESUME_TAILORING_TEMPERATURE", "0.3")
    monkeypatch.setenv("OPENAI_RESUME_TAILORING_TOP_P", "0.7")
    monkeypatch.setattr("app.services.openai_resume_tailoring_service.OpenAI", FakeOpenAI)

    result = generate_resume_tailoring_with_openai(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )

    assert result == expected_output
    assert captured_kwargs["temperature"] == 0.3
    assert captured_kwargs["top_p"] == 0.7


def test_generate_resume_tailoring_with_openai_fails_cleanly_when_api_key_is_missing(
    monkeypatch,
) -> None:
    request = _load_request()
    match_result = analyze_match_basic(request)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ResumeTailoringOpenAIError) as exc_info:
        generate_resume_tailoring_with_openai(
            request.candidate_profile,
            request.job_posting,
            match_result,
        )

    assert exc_info.value.fallback_reason is ResumeFallbackReason.MISSING_API_KEY


def test_generate_resume_tailoring_with_openai_fails_cleanly_when_structured_output_is_missing(
    monkeypatch,
) -> None:
    request = _load_request()
    match_result = analyze_match_basic(request)

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            return type("FakeResponse", (), {"output_parsed": None})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr("app.services.openai_resume_tailoring_service.OpenAI", FakeOpenAI)

    with pytest.raises(ResumeTailoringOpenAIError) as exc_info:
        generate_resume_tailoring_with_openai(
            request.candidate_profile,
            request.job_posting,
            match_result,
        )

    assert exc_info.value.fallback_reason is ResumeFallbackReason.INVALID_AI_OUTPUT


def _load_request() -> MatchAnalysisRequest:
    payload = json.loads(_MATCH_PAYLOAD_FIXTURE.read_text(encoding="utf-8"))
    return MatchAnalysisRequest.model_validate(payload)


def _build_tailoring_output() -> OpenAIResumeTailoringOutput:
    return OpenAIResumeTailoringOutput(
        fit_summary="Strong PLC automation overlap with a conservative truthful-first framing.",
        professional_summary="Automation engineer with grounded PLC and commissioning experience.",
        selected_skills=["PLC", "TIA Portal"],
        selected_keywords=["PLC", "TIA Portal"],
        selected_experience_entries=[
            {
                "source_experience_id": "exp_001",
                "tailored_bullets": [
                    "Configured and maintained PLC logic for industrial automation systems.",
                ],
                "highlighted_keywords": ["PLC", "TIA Portal"],
                "relevance_note": "Closest experience to the target industrial automation offer.",
                "source_highlights": [
                    "Assisted in PLC-related automation tasks",
                ],
            }
        ],
        selected_project_entries=[],
        selected_education_entries=[],
        selected_language_entries=[],
        selected_certificate_entries=[],
        warnings=["The draft stays conservative because some requirements are still missing."],
        truthfulness_notes=["Missing requirements were left as warnings instead of being invented."],
        omitted_or_deemphasized_items=["Deemphasized profile areas with weaker overlap to the target role."],
    )
