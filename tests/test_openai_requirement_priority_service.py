from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.analysis import MatchAnalysisRequest
from app.services.openai_requirement_priority_service import (
    OpenAIRequirementPriorityItem,
    OpenAIRequirementPriorityOutput,
    RequirementPriorityOpenAIError,
    evaluate_requirement_priorities_with_openai,
)

_MATCH_PAYLOAD_FIXTURE = Path("data/match_analysis_test.json")


def test_evaluate_requirement_priorities_with_openai_omits_sampling_params_by_default(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_output = _build_output()
    request = _build_request()

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.delenv("OPENAI_REQUIREMENT_PRIORITY_TEMPERATURE", raising=False)
    monkeypatch.delenv("OPENAI_REQUIREMENT_PRIORITY_TOP_P", raising=False)
    monkeypatch.setenv("OPENAI_REQUIREMENT_PRIORITY_MODEL", "gpt-5-mini")
    monkeypatch.setattr("app.services.openai_requirement_priority_service.OpenAI", FakeOpenAI)

    result = evaluate_requirement_priorities_with_openai(request.job_posting)

    assert result == expected_output
    assert captured_kwargs["model"] == "gpt-5-mini"
    assert captured_kwargs["text_format"] is OpenAIRequirementPriorityOutput
    assert "temperature" not in captured_kwargs
    assert "top_p" not in captured_kwargs


def test_evaluate_requirement_priorities_with_openai_prefers_matching_workflow_model_over_legacy_env(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_output = _build_output()
    request = _build_request()

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_MATCHING_MODEL", "gpt-5.4")
    monkeypatch.setenv("OPENAI_REQUIREMENT_PRIORITY_MODEL", "gpt-5-mini")
    monkeypatch.setattr("app.services.openai_requirement_priority_service.OpenAI", FakeOpenAI)

    result = evaluate_requirement_priorities_with_openai(request.job_posting)

    assert result == expected_output
    assert captured_kwargs["model"] == "gpt-5.4"


def test_evaluate_requirement_priorities_with_openai_includes_sampling_params_for_supported_model(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_output = _build_output()
    request = _build_request()

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_REQUIREMENT_PRIORITY_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_REQUIREMENT_PRIORITY_TEMPERATURE", "0.2")
    monkeypatch.setenv("OPENAI_REQUIREMENT_PRIORITY_TOP_P", "0.6")
    monkeypatch.setattr("app.services.openai_requirement_priority_service.OpenAI", FakeOpenAI)

    result = evaluate_requirement_priorities_with_openai(request.job_posting)

    assert result == expected_output
    assert captured_kwargs["temperature"] == 0.2
    assert captured_kwargs["top_p"] == 0.6


def test_evaluate_requirement_priorities_with_openai_fails_cleanly_when_api_key_is_missing(
    monkeypatch,
) -> None:
    request = _build_request()
    monkeypatch.setenv("OPENAI_API_KEY", "tu_wkleisz_swoj_klucz")

    with pytest.raises(RequirementPriorityOpenAIError) as exc_info:
        evaluate_requirement_priorities_with_openai(request.job_posting)

    assert exc_info.value.reason == "missing_api_key"


def test_evaluate_requirement_priorities_with_openai_fails_when_structured_output_is_missing(
    monkeypatch,
) -> None:
    request = _build_request()

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            return type("FakeResponse", (), {"output_parsed": None})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr("app.services.openai_requirement_priority_service.OpenAI", FakeOpenAI)

    with pytest.raises(RequirementPriorityOpenAIError) as exc_info:
        evaluate_requirement_priorities_with_openai(request.job_posting)

    assert exc_info.value.reason == "invalid_ai_output"


def test_evaluate_requirement_priorities_with_openai_rejects_missing_or_unknown_requirement_ids(
    monkeypatch,
) -> None:
    request = _build_request()
    invalid_output = OpenAIRequirementPriorityOutput(
        items=[
            OpenAIRequirementPriorityItem(
                requirement_id="req_001",
                priority_tier="core",
                confidence="high",
                reasoning_note="Defines the role's technical core.",
            ),
            OpenAIRequirementPriorityItem(
                requirement_id="req_unknown",
                priority_tier="supporting",
                confidence="medium",
                reasoning_note="This should be rejected because the ID is unknown.",
            ),
        ]
    )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            return type("FakeResponse", (), {"output_parsed": invalid_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr("app.services.openai_requirement_priority_service.OpenAI", FakeOpenAI)

    with pytest.raises(RequirementPriorityOpenAIError) as exc_info:
        evaluate_requirement_priorities_with_openai(request.job_posting)

    assert exc_info.value.reason == "invalid_ai_output"


def _build_request() -> MatchAnalysisRequest:
    payload = json.loads(_MATCH_PAYLOAD_FIXTURE.read_text(encoding="utf-8"))
    payload["job_posting"]["requirements"] = [
        {
            "id": "req_001",
            "text": "5 years of Azure experience",
            "category": "experience",
            "requirement_type": "must_have",
            "importance": "high",
            "extracted_keywords": ["Azure", "cloud"],
        },
        {
            "id": "req_002",
            "text": "Experience with Python",
            "category": "technology",
            "requirement_type": "must_have",
            "importance": "medium",
            "extracted_keywords": ["Python"],
        },
        {
            "id": "req_003",
            "text": "Excellent communication skills",
            "category": "soft_skill",
            "requirement_type": "nice_to_have",
            "importance": "medium",
            "extracted_keywords": ["communication"],
        },
    ]
    payload["job_posting"]["keywords"] = ["Azure", "Python", "communication"]
    return MatchAnalysisRequest.model_validate(payload)


def _build_output() -> OpenAIRequirementPriorityOutput:
    return OpenAIRequirementPriorityOutput(
        items=[
            OpenAIRequirementPriorityItem(
                requirement_id="req_001",
                priority_tier="core",
                confidence="high",
                reasoning_note="This requirement defines the role's core cloud experience bar.",
            ),
            OpenAIRequirementPriorityItem(
                requirement_id="req_002",
                priority_tier="supporting",
                confidence="high",
                reasoning_note="Python matters here, but the offer centers more strongly on Azure experience.",
            ),
            OpenAIRequirementPriorityItem(
                requirement_id="req_003",
                priority_tier="supporting",
                confidence="medium",
                reasoning_note="Communication is relevant, but it is not the role's main differentiator.",
            ),
        ]
    )
