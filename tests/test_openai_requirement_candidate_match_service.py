from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.analysis import MatchAnalysisRequest
from app.models.match import RequirementMatch
from app.services.openai_candidate_profile_understanding_service import (
    CandidateProfileUnderstanding,
)
from app.services.openai_requirement_candidate_match_service import (
    OpenAIRequirementCandidateMatchRawItem,
    OpenAIRequirementCandidateMatchRawOutput,
    RequirementCandidateMatchOpenAIError,
    evaluate_requirement_candidate_block_with_openai,
)

_MATCH_PAYLOAD_FIXTURE = Path("data/match_analysis_test.json")


def _build_deterministic_lookup(requirement_ids: list[str]) -> dict[str, RequirementMatch]:
    return {
        requirement_id: RequirementMatch(
            requirement_id=requirement_id,
            match_status="missing",
            explanation="Deterministic baseline did not find a safe grounded match.",
        )
        for requirement_id in requirement_ids
    }


def test_evaluate_requirement_candidate_block_with_openai_fails_cleanly_when_api_key_is_missing(
    monkeypatch,
) -> None:
    request = _load_request()
    monkeypatch.setenv("OPENAI_API_KEY", "tu_wkleisz_swoj_klucz")

    with pytest.raises(RequirementCandidateMatchOpenAIError) as exc_info:
        evaluate_requirement_candidate_block_with_openai(
            request,
            target_requirements=request.job_posting.requirements[:1],
            requirement_groups={request.job_posting.requirements[0].id: "technical_skill"},
            deterministic_match_lookup=_build_deterministic_lookup(
                [request.job_posting.requirements[0].id]
            ),
            requirement_priority_lookup={},
            candidate_profile_understanding=CandidateProfileUnderstanding(),
        )

    assert exc_info.value.reason == "missing_api_key"


def test_evaluate_requirement_candidate_block_with_openai_builds_validated_semantic_items(
    monkeypatch,
) -> None:
    request = _load_request()
    request.job_posting.requirements = request.job_posting.requirements[:1]
    request.job_posting.requirements[0].id = "req_openai"
    request.job_posting.requirements[0].text = "Hands-on OpenAI integration experience"
    request.job_posting.requirements[0].extracted_keywords = ["OpenAI"]
    request.candidate_profile.project_entries[0].description = (
        "Built an OpenAI API integration for an internal robotics assistant."
    )

    expected_output = OpenAIRequirementCandidateMatchRawOutput(
        items=[
            OpenAIRequirementCandidateMatchRawItem(
                requirement_id="req_openai",
                suggested_status="matched",
                grounding_strength="strong",
                reasoning_note="The project explicitly describes an OpenAI API integration.",
                evidence_refs=[
                    {
                        "source_type": "project",
                        "source_id": "proj_001",
                        "supporting_snippet": "OpenAI API integration",
                    }
                ],
                supporting_signal_labels=["technology", "OpenAI"],
                missing_elements=[],
            )
        ]
    )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr(
        "app.services.openai_requirement_candidate_match_service.OpenAI",
        FakeOpenAI,
    )

    output = evaluate_requirement_candidate_block_with_openai(
        request,
        target_requirements=request.job_posting.requirements,
        requirement_groups={"req_openai": "technical_skill"},
        deterministic_match_lookup=_build_deterministic_lookup(["req_openai"]),
        requirement_priority_lookup={},
        candidate_profile_understanding=CandidateProfileUnderstanding(),
    )

    assert len(output.items) == 1
    assert output.items[0].requirement_id == "req_openai"
    assert output.items[0].evidence_basis == "hard_evidence"
    assert output.items[0].supporting_signal_labels == ["OpenAI"]


def test_evaluate_requirement_candidate_block_with_openai_rejects_ungrounded_snippets(
    monkeypatch,
) -> None:
    request = _load_request()
    request.job_posting.requirements = request.job_posting.requirements[:1]
    request.job_posting.requirements[0].id = "req_openai"
    request.job_posting.requirements[0].text = "Hands-on OpenAI integration experience"
    request.job_posting.requirements[0].extracted_keywords = ["OpenAI"]

    invalid_output = OpenAIRequirementCandidateMatchRawOutput(
        items=[
            OpenAIRequirementCandidateMatchRawItem(
                requirement_id="req_openai",
                suggested_status="matched",
                grounding_strength="strong",
                reasoning_note="This should fail because the snippet is not grounded.",
                evidence_refs=[
                    {
                        "source_type": "project",
                        "source_id": "proj_001",
                        "supporting_snippet": "Invented snippet",
                    }
                ],
                supporting_signal_labels=["OpenAI"],
                missing_elements=[],
            )
        ]
    )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            return type("FakeResponse", (), {"output_parsed": invalid_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr(
        "app.services.openai_requirement_candidate_match_service.OpenAI",
        FakeOpenAI,
    )

    with pytest.raises(RequirementCandidateMatchOpenAIError) as exc_info:
        evaluate_requirement_candidate_block_with_openai(
            request,
            target_requirements=request.job_posting.requirements,
            requirement_groups={"req_openai": "technical_skill"},
            deterministic_match_lookup=_build_deterministic_lookup(["req_openai"]),
            requirement_priority_lookup={},
            candidate_profile_understanding=CandidateProfileUnderstanding(),
        )

    assert exc_info.value.reason == "invalid_ai_output"


def _load_request() -> MatchAnalysisRequest:
    payload = json.loads(_MATCH_PAYLOAD_FIXTURE.read_text(encoding="utf-8"))
    return MatchAnalysisRequest.model_validate(payload)
