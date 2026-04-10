from __future__ import annotations

import pytest

from app.models.analysis import MatchAnalysisRequest
from app.models.match import RequirementMatch
from app.services.openai_education_match_service import (
    EducationRequirementMatchOpenAIError,
    OpenAIEducationRequirementMatchOutput,
    evaluate_education_requirement_with_openai,
)


def test_evaluate_education_requirement_with_openai_omits_sampling_params_by_default(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_output = _build_output()
    request = _build_request()
    requirement = request.job_posting.requirements[0]
    deterministic_match = RequirementMatch(
        requirement_id=requirement.id,
        match_status="partial",
        explanation="Deterministic baseline education match is only partial.",
        missing_elements=["exact field match"],
    )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.delenv("OPENAI_EDUCATION_MATCH_TEMPERATURE", raising=False)
    monkeypatch.delenv("OPENAI_EDUCATION_MATCH_TOP_P", raising=False)
    monkeypatch.setenv("OPENAI_EDUCATION_MATCH_MODEL", "gpt-5-mini")
    monkeypatch.setattr("app.services.openai_education_match_service.OpenAI", FakeOpenAI)

    result = evaluate_education_requirement_with_openai(
        requirement,
        request.candidate_profile,
        request.job_posting,
        deterministic_match,
    )

    assert result == expected_output
    assert captured_kwargs["model"] == "gpt-5-mini"
    assert captured_kwargs["text_format"] is OpenAIEducationRequirementMatchOutput
    assert "temperature" not in captured_kwargs
    assert "top_p" not in captured_kwargs


def test_evaluate_education_requirement_with_openai_prefers_matching_workflow_model_over_legacy_env(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_output = _build_output()
    request = _build_request()
    requirement = request.job_posting.requirements[0]
    deterministic_match = RequirementMatch(
        requirement_id=requirement.id,
        match_status="partial",
        explanation="Deterministic baseline education match is only partial.",
        missing_elements=["exact field match"],
    )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_MATCHING_MODEL", "gpt-5.4")
    monkeypatch.setenv("OPENAI_EDUCATION_MATCH_MODEL", "gpt-5-mini")
    monkeypatch.setattr("app.services.openai_education_match_service.OpenAI", FakeOpenAI)

    result = evaluate_education_requirement_with_openai(
        requirement,
        request.candidate_profile,
        request.job_posting,
        deterministic_match,
    )

    assert result == expected_output
    assert captured_kwargs["model"] == "gpt-5.4"


def test_evaluate_education_requirement_with_openai_includes_sampling_params_for_supported_model(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_output = _build_output()
    request = _build_request()
    requirement = request.job_posting.requirements[0]
    deterministic_match = RequirementMatch(
        requirement_id=requirement.id,
        match_status="partial",
        explanation="Deterministic baseline education match is only partial.",
        missing_elements=["exact field match"],
    )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_EDUCATION_MATCH_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_EDUCATION_MATCH_TEMPERATURE", "0.3")
    monkeypatch.setenv("OPENAI_EDUCATION_MATCH_TOP_P", "0.7")
    monkeypatch.setattr("app.services.openai_education_match_service.OpenAI", FakeOpenAI)

    result = evaluate_education_requirement_with_openai(
        requirement,
        request.candidate_profile,
        request.job_posting,
        deterministic_match,
    )

    assert result == expected_output
    assert captured_kwargs["temperature"] == 0.3
    assert captured_kwargs["top_p"] == 0.7


def test_evaluate_education_requirement_with_openai_fails_cleanly_when_api_key_is_missing(
    monkeypatch,
) -> None:
    request = _build_request()
    requirement = request.job_posting.requirements[0]
    deterministic_match = RequirementMatch(
        requirement_id=requirement.id,
        match_status="partial",
        explanation="Deterministic baseline education match is only partial.",
        missing_elements=["exact field match"],
    )
    monkeypatch.setenv("OPENAI_API_KEY", "tu_wkleisz_swoj_klucz")

    with pytest.raises(EducationRequirementMatchOpenAIError) as exc_info:
        evaluate_education_requirement_with_openai(
            requirement,
            request.candidate_profile,
            request.job_posting,
            deterministic_match,
        )

    assert exc_info.value.reason == "missing_api_key"


def test_evaluate_education_requirement_with_openai_rejects_unknown_source_ids(
    monkeypatch,
) -> None:
    request = _build_request()
    requirement = request.job_posting.requirements[0]
    deterministic_match = RequirementMatch(
        requirement_id=requirement.id,
        match_status="partial",
        explanation="Deterministic baseline education match is only partial.",
        missing_elements=["exact field match"],
    )
    invalid_output = OpenAIEducationRequirementMatchOutput(
        suggested_status="matched",
        grounding_strength="strong",
        match_kind="related_technical_field",
        explanation="Automation and Robotics is a closely related technical field for this requirement.",
        evidence_refs=[
            {
                "source_type": "education",
                "source_id": "education_999",
                "supporting_snippet": "Automation and Robotics",
            }
        ],
    )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            return type("FakeResponse", (), {"output_parsed": invalid_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr("app.services.openai_education_match_service.OpenAI", FakeOpenAI)

    with pytest.raises(EducationRequirementMatchOpenAIError) as exc_info:
        evaluate_education_requirement_with_openai(
            requirement,
            request.candidate_profile,
            request.job_posting,
            deterministic_match,
        )

    assert exc_info.value.reason == "invalid_ai_grounding"


def test_evaluate_education_requirement_with_openai_rejects_ungrounded_snippets(
    monkeypatch,
) -> None:
    request = _build_request()
    requirement = request.job_posting.requirements[0]
    deterministic_match = RequirementMatch(
        requirement_id=requirement.id,
        match_status="partial",
        explanation="Deterministic baseline education match is only partial.",
        missing_elements=["exact field match"],
    )
    invalid_output = OpenAIEducationRequirementMatchOutput(
        suggested_status="matched",
        grounding_strength="strong",
        match_kind="related_technical_field",
        explanation="Automation and Robotics is a closely related technical field for this requirement.",
        evidence_refs=[
            {
                "source_type": "education",
                "source_id": "education_001",
                "supporting_snippet": "Unsupported Mechanical Degree",
            }
        ],
    )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            return type("FakeResponse", (), {"output_parsed": invalid_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr("app.services.openai_education_match_service.OpenAI", FakeOpenAI)

    with pytest.raises(EducationRequirementMatchOpenAIError) as exc_info:
        evaluate_education_requirement_with_openai(
            requirement,
            request.candidate_profile,
            request.job_posting,
            deterministic_match,
        )

    assert exc_info.value.reason == "invalid_ai_grounding"


def _build_request() -> MatchAnalysisRequest:
    return MatchAnalysisRequest.model_validate(
        {
            "candidate_profile": {
                "personal_info": {
                    "full_name": "Filip Kolęda",
                    "email": "filip@example.com",
                    "phone": "+48 123 456 789",
                    "linkedin_url": "https://www.linkedin.com/in/filipkoleda",
                    "github_url": "https://github.com/filipkoleda",
                    "portfolio_url": "https://filipkoleda.dev",
                    "location": "Gdańsk, Poland",
                },
                "target_roles": ["Automation Engineer"],
                "professional_summary_base": "Automation and robotics student.",
                "experience_entries": [],
                "project_entries": [],
                "skill_entries": [],
                "education_entries": [
                    {
                        "institution_name": "Gdańsk University of Technology",
                        "degree": "Engineer",
                        "field_of_study": "Automation and Robotics",
                        "start_date": "2021-10",
                        "end_date": None,
                        "is_current": True,
                    }
                ],
                "language_entries": [],
                "certificate_entries": [],
                "immutable_rules": {
                    "forbidden_skills": [],
                    "forbidden_claims": [],
                    "forbidden_certificates": [],
                    "editing_rules": [],
                },
            },
            "job_posting": {
                "source": "manual",
                "title": "Junior Controls Engineer",
                "company_name": "Example Tech",
                "location": "Gdańsk, Poland",
                "work_mode": "onsite",
                "employment_type": "uop",
                "seniority_level": "junior",
                "role_summary": "Junior role in industrial controls.",
                "responsibilities": [],
                "requirements": [
                    {
                        "id": "req_education",
                        "text": "Bachelor's degree in Electrical Engineering",
                        "category": "education",
                        "requirement_type": "must_have",
                        "importance": "high",
                        "extracted_keywords": ["Bachelor degree", "Electrical Engineering"],
                    }
                ],
                "keywords": ["Electrical Engineering"],
                "language_of_offer": "en",
            },
        }
    )


def _build_output() -> OpenAIEducationRequirementMatchOutput:
    return OpenAIEducationRequirementMatchOutput(
        suggested_status="matched",
        grounding_strength="strong",
        match_kind="related_technical_field",
        explanation="Automation and Robotics is a closely related technical field for this requirement.",
        evidence_refs=[
            {
                "source_type": "education",
                "source_id": "education_001",
                "supporting_snippet": "Automation and Robotics",
            }
        ],
    )
