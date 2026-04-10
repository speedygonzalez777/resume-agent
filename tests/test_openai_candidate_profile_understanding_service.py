from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.analysis import MatchAnalysisRequest
from app.services.openai_candidate_profile_understanding_service import (
    CandidateProfileUnderstandingOpenAIError,
    OpenAICandidateLanguageNormalization,
    OpenAICandidateProfileUnderstandingRawOutput,
    OpenAICandidateSourceSignal,
    OpenAICandidateThematicAlignment,
    OpenAICandidateThematicRef,
    evaluate_candidate_profile_understanding_with_openai,
)

_MATCH_PAYLOAD_FIXTURE = Path("data/match_analysis_test.json")


def test_evaluate_candidate_profile_understanding_with_openai_fails_cleanly_when_api_key_is_missing(
    monkeypatch,
) -> None:
    request = _load_request()
    monkeypatch.setenv("OPENAI_API_KEY", "tu_wkleisz_swoj_klucz")

    with pytest.raises(CandidateProfileUnderstandingOpenAIError) as exc_info:
        evaluate_candidate_profile_understanding_with_openai(request.candidate_profile)

    assert exc_info.value.reason == "missing_api_key"


def test_evaluate_candidate_profile_understanding_with_openai_uses_matching_workflow_model(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    request = _load_request()
    expected_output = OpenAICandidateProfileUnderstandingRawOutput(
        source_signals=[],
        language_normalizations=[
            OpenAICandidateLanguageNormalization(
                source_id="language_001",
                normalized_cefr=None,
                semantic_descriptors=["fluent", "written", "spoken"],
                confidence="high",
                reasoning_note="Grounded normalization for Polish.",
            ),
            OpenAICandidateLanguageNormalization(
                source_id="language_002",
                normalized_cefr="b2",
                semantic_descriptors=["written", "spoken", "business_working"],
                confidence="high",
                reasoning_note="Grounded normalization for English.",
            ),
        ],
        thematic_alignments=[],
        warnings=[],
    )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_MATCHING_MODEL", "gpt-5.4")
    monkeypatch.setenv("OPENAI_CANDIDATE_PROFILE_UNDERSTANDING_MODEL", "gpt-5-mini")
    monkeypatch.setattr(
        "app.services.openai_candidate_profile_understanding_service.OpenAI",
        FakeOpenAI,
    )

    result = evaluate_candidate_profile_understanding_with_openai(request.candidate_profile)

    assert captured_kwargs["model"] == "gpt-5.4"
    assert len(result.language_normalizations) == 2


def test_evaluate_candidate_profile_understanding_with_openai_builds_canonical_profile_signals(
    monkeypatch,
) -> None:
    request = _load_request()
    expected_output = OpenAICandidateProfileUnderstandingRawOutput(
        source_signals=[
            OpenAICandidateSourceSignal(
                source_type="experience",
                source_id="exp_001",
                signal_label="technical documentation",
                signal_kind="technical_competency",
                evidence_class="hard_evidence",
                normalized_terms=["technical documentation"],
                supporting_snippets=["Prepared technical documentation"],
                confidence="high",
                reasoning_note="The internship directly includes technical documentation work.",
            ),
            OpenAICandidateSourceSignal(
                source_type="project",
                source_id="proj_001",
                signal_label="technical documentation",
                signal_kind="technical_competency",
                evidence_class="hard_evidence",
                normalized_terms=["technical documentation"],
                supporting_snippets=["Prepared technical documentation and testing materials"],
                confidence="medium",
                reasoning_note="The project also includes documentation output.",
            ),
            OpenAICandidateSourceSignal(
                source_type="project",
                source_id="proj_001",
                signal_label="control systems",
                signal_kind="domain_exposure",
                evidence_class="hard_evidence",
                normalized_terms=["control systems"],
                supporting_snippets=["control systems"],
                confidence="high",
                reasoning_note="The project keywords explicitly mention control systems.",
            ),
            OpenAICandidateSourceSignal(
                source_type="skill",
                source_id="skill_001",
                signal_label="technology",
                signal_kind="technical_competency",
                evidence_class="hard_evidence",
                normalized_terms=["technology"],
                supporting_snippets=["Python"],
                confidence="low",
                reasoning_note="This overly generic signal should be dropped.",
            ),
        ],
        language_normalizations=[
            OpenAICandidateLanguageNormalization(
                source_id="language_001",
                normalized_cefr=None,
                semantic_descriptors=["fluent", "written", "spoken"],
                confidence="high",
                reasoning_note="Native Polish supports fluent written and spoken communication.",
            ),
            OpenAICandidateLanguageNormalization(
                source_id="language_002",
                normalized_cefr="b2",
                semantic_descriptors=["written", "spoken", "business_working"],
                confidence="high",
                reasoning_note="B2 English supports written and spoken business communication.",
            ),
        ],
        thematic_alignments=[
            OpenAICandidateThematicAlignment(
                theme_label="technical documentation",
                normalized_terms=["technical documentation"],
                source_refs=[
                    OpenAICandidateThematicRef(
                        source_type="experience",
                        source_id="exp_001",
                        supporting_snippet="Prepared technical documentation",
                    ),
                    OpenAICandidateThematicRef(
                        source_type="project",
                        source_id="proj_001",
                        supporting_snippet="Prepared technical documentation and testing materials",
                    ),
                ],
                confidence="high",
                reasoning_note="Documentation appears across both work and project evidence.",
            )
        ],
        warnings=[],
    )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            return type("FakeResponse", (), {"output_parsed": expected_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr(
        "app.services.openai_candidate_profile_understanding_service.OpenAI",
        FakeOpenAI,
    )

    result = evaluate_candidate_profile_understanding_with_openai(request.candidate_profile)

    assert [signal.signal_label for signal in result.source_signals] == [
        "technical documentation",
        "technical documentation",
        "control systems",
    ]
    assert [signal.signal_label for signal in result.profile_signals] == [
        "control systems",
        "technical documentation",
    ]
    technical_documentation_signal = next(
        signal
        for signal in result.profile_signals
        if signal.signal_label == "technical documentation"
    )
    assert len(technical_documentation_signal.source_refs) == 2
    assert all("technology" not in signal.normalized_terms for signal in result.source_signals)
    assert any("dropped during post-processing" in warning for warning in result.warnings)


def test_evaluate_candidate_profile_understanding_with_openai_rejects_ungrounded_snippets(
    monkeypatch,
) -> None:
    request = _load_request()
    invalid_output = OpenAICandidateProfileUnderstandingRawOutput(
        source_signals=[
            OpenAICandidateSourceSignal(
                source_type="project",
                source_id="proj_001",
                signal_label="OpenAI",
                signal_kind="technical_competency",
                evidence_class="hard_evidence",
                normalized_terms=["OpenAI"],
                supporting_snippets=["Invented OpenAI snippet"],
                confidence="high",
                reasoning_note="This should be rejected because the snippet is not grounded.",
            )
        ],
        language_normalizations=[
            OpenAICandidateLanguageNormalization(
                source_id="language_001",
                normalized_cefr=None,
                semantic_descriptors=["fluent", "written", "spoken"],
                confidence="high",
                reasoning_note="Native Polish supports fluent written and spoken communication.",
            ),
            OpenAICandidateLanguageNormalization(
                source_id="language_002",
                normalized_cefr="b2",
                semantic_descriptors=["written", "spoken", "business_working"],
                confidence="high",
                reasoning_note="B2 English supports written and spoken business communication.",
            ),
        ],
        thematic_alignments=[],
        warnings=[],
    )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            return type("FakeResponse", (), {"output_parsed": invalid_output})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr(
        "app.services.openai_candidate_profile_understanding_service.OpenAI",
        FakeOpenAI,
    )

    with pytest.raises(CandidateProfileUnderstandingOpenAIError) as exc_info:
        evaluate_candidate_profile_understanding_with_openai(request.candidate_profile)

    assert exc_info.value.reason == "invalid_ai_output"


def _load_request() -> MatchAnalysisRequest:
    payload = json.loads(_MATCH_PAYLOAD_FIXTURE.read_text(encoding="utf-8"))
    return MatchAnalysisRequest.model_validate(payload)
