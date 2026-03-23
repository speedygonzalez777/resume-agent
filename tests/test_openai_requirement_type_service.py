from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.analysis import MatchAnalysisRequest
from app.services.openai_requirement_type_service import (
    OpenAIRequirementTypeClassificationOutput,
    RequirementTypeClassificationOpenAIError,
    evaluate_requirement_type_with_openai,
)

_MATCH_PAYLOAD_FIXTURE = Path("data/match_analysis_test.json")


def test_evaluate_requirement_type_with_openai_omits_sampling_params_by_default(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_output = _build_output()
    request = _build_request()
    requirement = request.job_posting.requirements[0]

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.delenv("OPENAI_REQUIREMENT_TYPE_TEMPERATURE", raising=False)
    monkeypatch.delenv("OPENAI_REQUIREMENT_TYPE_TOP_P", raising=False)
    monkeypatch.setenv("OPENAI_REQUIREMENT_TYPE_MODEL", "gpt-5-mini")
    monkeypatch.setattr("app.services.openai_requirement_type_service.OpenAI", FakeOpenAI)

    result = evaluate_requirement_type_with_openai(requirement, request.job_posting)

    assert result == expected_output
    assert captured_kwargs["model"] == "gpt-5-mini"
    assert captured_kwargs["text_format"] is OpenAIRequirementTypeClassificationOutput
    assert "temperature" not in captured_kwargs
    assert "top_p" not in captured_kwargs


def test_evaluate_requirement_type_with_openai_includes_sampling_params_for_supported_model(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_output = _build_output()
    request = _build_request()
    requirement = request.job_posting.requirements[0]

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_REQUIREMENT_TYPE_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_REQUIREMENT_TYPE_TEMPERATURE", "0.2")
    monkeypatch.setenv("OPENAI_REQUIREMENT_TYPE_TOP_P", "0.6")
    monkeypatch.setattr("app.services.openai_requirement_type_service.OpenAI", FakeOpenAI)

    result = evaluate_requirement_type_with_openai(requirement, request.job_posting)

    assert result == expected_output
    assert captured_kwargs["temperature"] == 0.2
    assert captured_kwargs["top_p"] == 0.6


def test_evaluate_requirement_type_with_openai_fails_cleanly_when_api_key_is_missing(
    monkeypatch,
) -> None:
    request = _build_request()
    requirement = request.job_posting.requirements[0]
    monkeypatch.setenv("OPENAI_API_KEY", "tu_wkleisz_swoj_klucz")

    with pytest.raises(RequirementTypeClassificationOpenAIError) as exc_info:
        evaluate_requirement_type_with_openai(requirement, request.job_posting)

    assert exc_info.value.reason == "missing_api_key"


def test_evaluate_requirement_type_with_openai_fails_when_structured_output_is_missing(
    monkeypatch,
) -> None:
    request = _build_request()
    requirement = request.job_posting.requirements[0]

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            return type("FakeResponse", (), {"output_parsed": None})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr("app.services.openai_requirement_type_service.OpenAI", FakeOpenAI)

    with pytest.raises(RequirementTypeClassificationOpenAIError) as exc_info:
        evaluate_requirement_type_with_openai(requirement, request.job_posting)

    assert exc_info.value.reason == "invalid_ai_output"


def _build_request() -> MatchAnalysisRequest:
    payload = json.loads(_MATCH_PAYLOAD_FIXTURE.read_text(encoding="utf-8"))
    payload["job_posting"]["requirements"] = [
        {
            "id": "req_availability",
            "text": "Available 30h/week for 6 months",
            "category": "other",
            "requirement_type": "must_have",
            "importance": "high",
            "extracted_keywords": ["30h/week", "6 months"],
        }
    ]
    payload["job_posting"]["keywords"] = ["30h/week", "6 months"]
    return MatchAnalysisRequest.model_validate(payload)


def _build_output() -> OpenAIRequirementTypeClassificationOutput:
    return OpenAIRequirementTypeClassificationOutput(
        normalized_requirement_type="application_constraint",
        confidence="high",
        reasoning_note="This requirement is about candidate availability and commitment rather than a skill.",
    )
