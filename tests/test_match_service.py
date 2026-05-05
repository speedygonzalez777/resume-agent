import json
from pathlib import Path
from typing import Any

from app.models.analysis import MatchAnalysisRequest
from app.services.match_service import analyze_match_artifacts, analyze_match_basic
from app.services.openai_candidate_profile_understanding_service import (
    CandidateLanguageNormalization,
    CandidateProfileSignal,
    CandidateProfileSourceRef,
    CandidateProfileUnderstanding,
    CandidateSourceSignal,
    CandidateThematicAlignment,
)
from app.services.openai_education_match_service import (
    EducationRequirementMatchOpenAIError,
    OpenAIEducationRequirementMatchOutput,
)
from app.services.openai_requirement_candidate_match_service import (
    RequirementCandidateEvidenceRef,
    RequirementCandidateMatchItem,
    RequirementCandidateMatchOutput,
)
from app.services.openai_requirement_priority_service import OpenAIRequirementPriorityItem
from app.services.openai_requirement_type_service import (
    OpenAIRequirementTypeClassificationOutput,
    RequirementTypeClassificationOpenAIError,
)

_MATCH_PAYLOAD_FIXTURE = Path("data/match_analysis_test.json")


def _load_base_payload() -> dict[str, Any]:
    """Load the reusable match-analysis fixture payload from disk."""
    return json.loads(_MATCH_PAYLOAD_FIXTURE.read_text(encoding="utf-8"))


def _build_requirement(
    requirement_id: str,
    text: str,
    *,
    extracted_keywords: list[str],
    category: str = "technology",
    requirement_type: str = "nice_to_have",
    importance: str = "medium",
) -> dict[str, Any]:
    """Build a lightweight requirement payload for service-level scoring tests."""
    return {
        "id": requirement_id,
        "text": text,
        "category": category,
        "requirement_type": requirement_type,
        "importance": importance,
        "extracted_keywords": extracted_keywords,
    }


def _build_request(
    requirements: list[dict[str, Any]],
    *,
    candidate_overrides: dict[str, Any] | None = None,
) -> MatchAnalysisRequest:
    """Create a MatchAnalysisRequest with custom job requirements and optional profile overrides."""
    payload = _load_base_payload()
    payload["job_posting"]["requirements"] = requirements

    job_keywords: list[str] = []
    for requirement in requirements:
        for keyword in requirement["extracted_keywords"]:
            if keyword not in job_keywords:
                job_keywords.append(keyword)
    payload["job_posting"]["keywords"] = job_keywords

    if candidate_overrides:
        payload["candidate_profile"].update(candidate_overrides)

    return MatchAnalysisRequest.model_validate(payload)


def _get_requirement_match(result, requirement_id: str):
    """Fetch one requirement match by its ID from a MatchResult."""
    return next(item for item in result.requirement_matches if item.requirement_id == requirement_id)


def _build_requirement_type_output(
    normalized_requirement_type: str,
    *,
    confidence: str = "high",
    reasoning_note: str | None = None,
) -> OpenAIRequirementTypeClassificationOutput:
    """Build a compact AI classifier output used in matching tests."""
    return OpenAIRequirementTypeClassificationOutput(
        normalized_requirement_type=normalized_requirement_type,
        confidence=confidence,
        reasoning_note=reasoning_note or f"Classified as {normalized_requirement_type}.",
    )


def _build_requirement_priority_item(
    requirement_id: str,
    priority_tier: str,
    *,
    confidence: str = "high",
    reasoning_note: str | None = None,
) -> OpenAIRequirementPriorityItem:
    """Build a compact AI requirement-priority item used in tests."""

    return OpenAIRequirementPriorityItem(
        requirement_id=requirement_id,
        priority_tier=priority_tier,
        confidence=confidence,
        reasoning_note=reasoning_note or f"{requirement_id} is {priority_tier}.",
    )


def _disable_requirement_prioritization(monkeypatch) -> None:
    """Prevent tests with a fake API key from triggering real priority-service calls."""

    monkeypatch.setattr(
        "app.services.match_service.get_requirement_priority_lookup",
        lambda *_args, **_kwargs: {},
    )


def _disable_candidate_profile_understanding(monkeypatch) -> None:
    """Prevent tests with a fake API key from triggering real profile-understanding calls."""

    monkeypatch.setattr(
        "app.services.match_service.get_candidate_profile_understanding",
        lambda *_args, **_kwargs: CandidateProfileUnderstanding(),
    )


def _disable_ai_requirement_candidate_matching(monkeypatch) -> None:
    """Prevent tests with a fake API key from triggering real semantic requirement matching calls."""

    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_candidate_block_with_openai",
        lambda *_args, **_kwargs: RequirementCandidateMatchOutput(),
    )


def test_weighted_score_uses_importance_requirement_type_and_match_status() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_weighted_matched",
                "PLC basics",
                extracted_keywords=["PLC"],
                requirement_type="must_have",
                importance="high",
            ),
            _build_requirement(
                "req_weighted_partial",
                "English at advanced level",
                category="language",
                extracted_keywords=["English", "advanced"],
                requirement_type="nice_to_have",
                importance="low",
            ),
        ]
    )

    result = analyze_match_basic(request)

    assert result.requirement_matches[0].match_status == "matched"
    assert result.requirement_matches[1].match_status == "partial"
    assert result.overall_score == 0.94
    assert result.fit_classification == "high"


def test_importance_weight_changes_overall_score() -> None:
    low_importance_request = _build_request(
        [
            _build_requirement(
                "req_importance_match",
                "PLC basics",
                extracted_keywords=["PLC"],
                importance="medium",
            ),
            _build_requirement(
                "req_importance_missing_low",
                "Rust experience",
                extracted_keywords=["Rust"],
                importance="low",
            ),
        ]
    )
    high_importance_request = _build_request(
        [
            _build_requirement(
                "req_importance_match",
                "PLC basics",
                extracted_keywords=["PLC"],
                importance="medium",
            ),
            _build_requirement(
                "req_importance_missing_high",
                "Rust experience",
                extracted_keywords=["Rust"],
                importance="high",
            ),
        ]
    )

    low_importance_result = analyze_match_basic(low_importance_request)
    high_importance_result = analyze_match_basic(high_importance_request)

    assert low_importance_result.overall_score > high_importance_result.overall_score
    assert low_importance_result.fit_classification in {"medium", "high"}
    assert high_importance_result.recommendation == "do_not_recommend"


def test_requirement_type_multiplier_changes_overall_score() -> None:
    nice_to_have_request = _build_request(
        [
            _build_requirement(
                "req_type_match",
                "PLC basics",
                extracted_keywords=["PLC"],
                importance="medium",
                requirement_type="nice_to_have",
            ),
            _build_requirement(
                "req_type_missing_nice",
                "Rust experience",
                extracted_keywords=["Rust"],
                importance="medium",
                requirement_type="nice_to_have",
            ),
        ]
    )
    must_have_request = _build_request(
        [
            _build_requirement(
                "req_type_match",
                "PLC basics",
                extracted_keywords=["PLC"],
                importance="medium",
                requirement_type="nice_to_have",
            ),
            _build_requirement(
                "req_type_missing_must",
                "Rust experience",
                extracted_keywords=["Rust"],
                importance="medium",
                requirement_type="must_have",
            ),
        ]
    )

    nice_to_have_result = analyze_match_basic(nice_to_have_request)
    must_have_result = analyze_match_basic(must_have_request)

    assert nice_to_have_result.overall_score == 0.5
    assert must_have_result.overall_score == 0.43
    assert nice_to_have_result.overall_score > must_have_result.overall_score
    assert must_have_result.recommendation == "do_not_recommend"


def test_contextual_requirement_has_small_but_nonzero_effect_on_overall_score() -> None:
    baseline_request = _build_request(
        [
            _build_requirement(
                "req_plc",
                "PLC basics",
                extracted_keywords=["PLC"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )
    contextual_request = _build_request(
        [
            _build_requirement(
                "req_plc",
                "PLC basics",
                extracted_keywords=["PLC"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            ),
            _build_requirement(
                "req_fieldbus_context",
                "Exposure to industrial fieldbus protocols",
                extracted_keywords=["fieldbus protocols"],
                category="domain",
                requirement_type="nice_to_have",
                importance="low",
            ),
        ]
    )

    baseline_result = analyze_match_basic(baseline_request)
    contextual_result = analyze_match_basic(contextual_request)

    assert baseline_result.overall_score == 1.0
    assert contextual_result.overall_score < baseline_result.overall_score
    assert contextual_result.overall_score == 0.9


def test_partial_core_scores_higher_than_partial_supporting_requirement() -> None:
    partial_core_request = _build_request(
        [
            _build_requirement(
                "req_experience_years",
                "3+ years of PLC experience",
                extracted_keywords=["PLC", "experience"],
                category="experience",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )
    partial_supporting_request = _build_request(
        [
            _build_requirement(
                "req_english",
                "English at advanced level",
                category="language",
                extracted_keywords=["English", "advanced"],
                requirement_type="nice_to_have",
                importance="medium",
            )
        ]
    )

    partial_core_result = analyze_match_basic(partial_core_request)
    partial_supporting_result = analyze_match_basic(partial_supporting_request)

    assert partial_core_result.requirement_matches[0].match_status == "partial"
    assert partial_supporting_result.requirement_matches[0].match_status == "partial"
    assert partial_core_result.overall_score > partial_supporting_result.overall_score


def test_missing_must_have_blocks_generate_recommendation() -> None:
    request = _build_request(
        [
            *[
                _build_requirement(
                    f"req_match_{index}",
                    "PLC basics",
                    extracted_keywords=["PLC"],
                    importance="high",
                    requirement_type="nice_to_have",
                )
                for index in range(5)
            ],
            _build_requirement(
                "req_missing_must",
                "Rust experience",
                extracted_keywords=["Rust"],
                importance="medium",
                requirement_type="must_have",
            ),
        ]
    )

    result = analyze_match_basic(request)

    assert result.overall_score == 0.85
    assert result.fit_classification == "high"
    assert result.recommendation == "generate_with_caution"


def test_missing_high_priority_must_have_blocks_high_fit_even_with_many_low_nice_matches() -> None:
    request = _build_request(
        [
            *[
                _build_requirement(
                    f"req_low_match_{index}",
                    "PLC basics",
                    extracted_keywords=["PLC"],
                    importance="low",
                    requirement_type="nice_to_have",
                )
                for index in range(20)
            ],
            _build_requirement(
                "req_critical_missing",
                "Production Kubernetes experience",
                extracted_keywords=["Kubernetes"],
                importance="high",
                requirement_type="must_have",
            ),
        ]
    )

    result = analyze_match_basic(request)

    assert result.overall_score == 0.1
    assert result.fit_classification == "low"
    assert result.recommendation == "do_not_recommend"


def test_two_missing_must_haves_force_do_not_recommend() -> None:
    request = _build_request(
        [
            *[
                _build_requirement(
                    f"req_high_match_{index}",
                    "PLC basics",
                    extracted_keywords=["PLC"],
                    importance="high",
                    requirement_type="nice_to_have",
                )
                for index in range(8)
            ],
            _build_requirement(
                "req_missing_must_one",
                "Rust experience",
                extracted_keywords=["Rust"],
                importance="medium",
                requirement_type="must_have",
            ),
            _build_requirement(
                "req_missing_must_two",
                "Go experience",
                extracted_keywords=["Go"],
                importance="medium",
                requirement_type="must_have",
            ),
        ]
    )

    result = analyze_match_basic(request)

    assert result.overall_score == 0.81
    assert result.fit_classification == "high"
    assert result.recommendation == "do_not_recommend"


def test_unverifiable_formal_must_have_stays_neutral_for_score_but_triggers_caution() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_plc",
                "Basic knowledge of PLC systems",
                extracted_keywords=["PLC"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            ),
            _build_requirement(
                "req_age",
                "Must be at least 18 years old",
                extracted_keywords=["18 years", "age"],
                category="other",
                requirement_type="must_have",
                importance="high",
            ),
        ]
    )

    result = analyze_match_basic(request)

    assert _get_requirement_match(result, "req_plc").match_status == "matched"
    assert _get_requirement_match(result, "req_age").match_status == "not_verifiable"
    assert result.overall_score == 1.0
    assert result.fit_classification == "high"
    assert result.recommendation == "generate_with_caution"
    assert any("Could not verify requirement: Must be at least 18 years old." in gap for gap in result.gaps)


def test_technical_not_verifiable_core_is_reported_differently_than_manual_confirmation(monkeypatch) -> None:
    technical_request = _build_request(
        [
            _build_requirement(
                "req_plc",
                "Basic knowledge of PLC systems",
                extracted_keywords=["PLC"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            ),
            _build_requirement(
                "req_education_missing",
                "Bachelor's degree in Automation and Robotics",
                extracted_keywords=["Bachelor degree", "Automation and Robotics"],
                category="education",
                requirement_type="must_have",
                importance="high",
            ),
        ],
        candidate_overrides={"education_entries": []},
    )
    manual_request = _build_request(
        [
            _build_requirement(
                "req_plc",
                "Basic knowledge of PLC systems",
                extracted_keywords=["PLC"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            ),
            _build_requirement(
                "req_availability",
                "Available 32 hours per week from Monday to Friday",
                extracted_keywords=["32 hours", "Monday-Friday"],
                category="other",
                requirement_type="must_have",
                importance="high",
            ),
        ]
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    _disable_requirement_prioritization(monkeypatch)
    _disable_candidate_profile_understanding(monkeypatch)
    _disable_ai_requirement_candidate_matching(monkeypatch)
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_type_with_openai",
        lambda requirement, *_args, **_kwargs: _build_requirement_type_output(
            (
                "application_constraint"
                if requirement.id == "req_availability"
                else "education"
                if requirement.id == "req_education_missing"
                else "technical_skill"
            )
        ),
    )
    monkeypatch.setattr(
        "app.services.match_service.evaluate_education_requirement_with_openai",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("AI education review should not run without education entries")
        ),
    )

    technical_result = analyze_match_basic(technical_request)
    manual_result = analyze_match_basic(manual_request)

    assert technical_result.recommendation == "generate_with_caution"
    assert "critical not verifiable" in technical_result.final_summary
    assert "Pending confirmations" not in technical_result.final_summary

    assert manual_result.recommendation == "generate_with_caution"
    assert "Pending confirmations" in manual_result.final_summary


def test_experience_year_threshold_without_documented_years_is_partial_not_not_verifiable() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_experience_years",
                "3+ years of PLC experience",
                extracted_keywords=["PLC", "experience"],
                category="experience",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_experience_years")

    assert requirement_match.match_status == "partial"
    assert "3+ years of documented experience" in requirement_match.missing_elements
    assert result.overall_score == 0.72
    assert result.fit_classification == "medium"


def test_related_technical_degree_counts_as_match_when_requirement_allows_related_field() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_education_related",
                "Bachelor's degree in Electrical Engineering or related technical field",
                extracted_keywords=["Bachelor degree", "Electrical Engineering", "related technical field"],
                category="education",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_education_related")

    assert requirement_match.match_status == "matched"
    assert "related technical field" in requirement_match.explanation
    assert result.overall_score == 1.0


def test_missing_education_entries_make_requirement_not_verifiable(monkeypatch) -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_education_missing",
                "Bachelor's degree in Automation and Robotics",
                extracted_keywords=["Bachelor degree", "Automation and Robotics"],
                category="education",
                requirement_type="must_have",
                importance="high",
            )
        ],
        candidate_overrides={"education_entries": []},
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    _disable_requirement_prioritization(monkeypatch)
    _disable_candidate_profile_understanding(monkeypatch)
    _disable_ai_requirement_candidate_matching(monkeypatch)
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_type_with_openai",
        lambda *args, **kwargs: _build_requirement_type_output("education"),
    )
    monkeypatch.setattr(
        "app.services.match_service.evaluate_education_requirement_with_openai",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI should not run without education entries")),
    )

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_education_missing")

    assert requirement_match.match_status == "not_verifiable"
    assert "does not contain education entries" in requirement_match.explanation


def test_certificate_evidence_can_satisfy_requirement_keywords() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_sep_certificate",
                "Valid SEP up to 1kV certificate",
                extracted_keywords=["SEP", "1kV"],
                category="other",
                requirement_type="must_have",
                importance="medium",
            )
        ]
    )

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_sep_certificate")

    assert requirement_match.match_status == "matched"
    assert requirement_match.evidence_texts == ["Certificate 'SEP up to 1kV' is listed in the candidate profile."]
    assert result.overall_score == 1.0


def test_unverifiable_soft_skill_must_have_does_not_downgrade_recommendation() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_plc",
                "Basic knowledge of PLC systems",
                extracted_keywords=["PLC"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            ),
            _build_requirement(
                "req_soft_skill",
                "Strong communication and teamwork skills",
                extracted_keywords=["communication", "teamwork"],
                category="soft_skill",
                requirement_type="must_have",
                importance="high",
            ),
        ]
    )

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_soft_skill")

    assert requirement_match.match_status == "not_verifiable"
    assert result.overall_score == 1.0
    assert result.fit_classification == "high"
    assert result.recommendation == "generate"

def test_explicit_soft_skills_support_soft_signal_requirements() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_plc",
                "Basic knowledge of PLC systems",
                extracted_keywords=["PLC"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            ),
            _build_requirement(
                "req_soft_skill",
                "Strong communication and teamwork skills",
                extracted_keywords=["communication", "teamwork"],
                category="soft_skill",
                requirement_type="must_have",
                importance="high",
            ),
        ],
        candidate_overrides={"soft_skill_entries": ["communication", "teamwork"]},
    )

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_soft_skill")

    assert requirement_match.match_status == "partial"
    assert "communication" in requirement_match.explanation
    assert "teamwork" in requirement_match.explanation
    assert result.recommendation == "generate"


def test_interest_entries_support_interest_or_motivation_signals() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_plc",
                "Basic knowledge of PLC systems",
                extracted_keywords=["PLC"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            ),
            _build_requirement(
                "req_interest",
                "Interest in machine learning and AI topics",
                extracted_keywords=["machine learning"],
                category="soft_skill",
                requirement_type="nice_to_have",
                importance="medium",
            ),
        ],
        candidate_overrides={"interest_entries": ["machine learning", "cognitive science"]},
    )

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_interest")

    assert requirement_match.match_status == "partial"
    assert "machine learning" in requirement_match.explanation
    assert result.recommendation == "generate"



def test_interest_entries_do_not_create_hard_technical_match() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_ml_skill",
                "Hands-on machine learning experience",
                extracted_keywords=["machine learning"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            )
        ],
        candidate_overrides={"interest_entries": ["machine learning"]},
    )

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_ml_skill")

    assert requirement_match.match_status == "missing"
    assert result.overall_score == 0.0
    assert result.recommendation == "do_not_recommend"


def test_candidate_profile_understanding_can_turn_project_signal_into_hard_match() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_openai",
                "Hands-on OpenAI integration experience",
                extracted_keywords=["OpenAI"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )
    request.candidate_profile.project_entries[0].description = (
        "Built an OpenAI API integration for an internal robotics assistant."
    )

    baseline_result = analyze_match_basic(request)
    understanding = CandidateProfileUnderstanding(
        source_signals=[
            CandidateSourceSignal(
                source_type="project",
                source_id="proj_001",
                source_title=request.candidate_profile.project_entries[0].project_name,
                signal_label="OpenAI",
                signal_kind="technical_competency",
                evidence_class="hard_evidence",
                normalized_terms=["OpenAI", "OpenAI API integration"],
                supporting_snippets=["OpenAI API integration"],
                confidence="high",
                reasoning_note="The project explicitly describes an OpenAI API integration.",
            )
        ],
        profile_signals=[
            CandidateProfileSignal(
                signal_label="OpenAI",
                signal_kind="technical_competency",
                evidence_class="hard_evidence",
                normalized_terms=["OpenAI", "OpenAI API integration"],
                source_refs=[
                    CandidateProfileSourceRef(source_type="project", source_id="proj_001")
                ],
                confidence="high",
                reasoning_note="Canonical profile signal aggregated from one grounded project signal.",
            )
        ],
        language_normalizations=[],
        thematic_alignments=[],
    )

    result = analyze_match_basic(
        request,
        candidate_profile_understanding=understanding,
    )
    requirement_match = _get_requirement_match(result, "req_openai")

    assert baseline_result.requirement_matches[0].match_status == "missing"
    assert requirement_match.match_status == "matched"
    assert requirement_match.matched_project_ids == ["proj_001"]
    assert any("AI-understood technical competency 'OpenAI'" in text for text in requirement_match.evidence_texts)


def test_candidate_profile_understanding_normalizes_language_descriptors() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_english",
                "Fluent written and spoken English",
                category="language",
                extracted_keywords=["English", "fluent", "written", "spoken"],
                requirement_type="must_have",
                importance="high",
            )
        ],
        candidate_overrides={
            "language_entries": [
                {
                    "language_name": "English",
                    "proficiency_level": "C1",
                }
            ]
        },
    )

    baseline_result = analyze_match_basic(request)
    understanding = CandidateProfileUnderstanding(
        source_signals=[],
        profile_signals=[],
        language_normalizations=[
            CandidateLanguageNormalization(
                source_id="language_001",
                language_name="English",
                source_level="C1",
                normalized_cefr="c1",
                semantic_descriptors=[
                    "fluent",
                    "written",
                    "spoken",
                    "professional_written",
                    "professional_spoken",
                ],
                confidence="high",
                reasoning_note="C1 supports fluent written and spoken professional communication.",
            )
        ],
        thematic_alignments=[],
    )

    result = analyze_match_basic(
        request,
        candidate_profile_understanding=understanding,
    )
    requirement_match = _get_requirement_match(result, "req_english")

    assert baseline_result.requirement_matches[0].match_status == "partial"
    assert requirement_match.match_status == "matched"
    assert "normalized language evidence" in requirement_match.explanation


def test_ai_semantic_matching_can_upgrade_project_signal_to_match(monkeypatch) -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_openai",
                "Hands-on OpenAI integration experience",
                extracted_keywords=["OpenAI"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )
    request.candidate_profile.project_entries[0].description = (
        "Built an OpenAI API integration for an internal robotics assistant."
    )

    baseline_result = analyze_match_basic(
        request,
        candidate_profile_understanding=CandidateProfileUnderstanding(),
        requirement_priority_lookup={},
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    _disable_requirement_prioritization(monkeypatch)
    _disable_candidate_profile_understanding(monkeypatch)
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_type_with_openai",
        lambda *args, **kwargs: _build_requirement_type_output("technical_skill"),
    )
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_candidate_block_with_openai",
        lambda *_args, **_kwargs: RequirementCandidateMatchOutput(
            items=[
                RequirementCandidateMatchItem(
                    requirement_id="req_openai",
                    suggested_status="matched",
                    grounding_strength="strong",
                    evidence_basis="hard_evidence",
                    reasoning_note="A grounded project source explicitly describes an OpenAI API integration.",
                    evidence_refs=[
                        RequirementCandidateEvidenceRef(
                            source_type="project",
                            source_id="proj_001",
                            supporting_snippet="OpenAI API integration",
                        )
                    ],
                    supporting_signal_labels=["OpenAI"],
                    missing_elements=[],
                )
            ]
        ),
    )

    result = analyze_match_basic(
        request,
        candidate_profile_understanding=CandidateProfileUnderstanding(),
        requirement_priority_lookup={},
    )
    requirement_match = _get_requirement_match(result, "req_openai")

    assert baseline_result.requirement_matches[0].match_status == "missing"
    assert requirement_match.match_status == "matched"
    assert requirement_match.matched_project_ids == ["proj_001"]
    assert any("AI-grounded evidence 'OpenAI API integration'" in text for text in requirement_match.evidence_texts)
    assert "AI-assisted semantic review" in requirement_match.explanation
    assert "AI semantic requirement matching improved 1 requirement decision" in result.final_summary


def test_ai_semantic_matching_can_upgrade_language_requirement(monkeypatch) -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_english",
                "Fluent written and spoken English",
                category="language",
                extracted_keywords=["English", "fluent", "written", "spoken"],
                requirement_type="must_have",
                importance="high",
            )
        ],
        candidate_overrides={
            "language_entries": [
                {
                    "language_name": "English",
                    "proficiency_level": "C1",
                }
            ]
        },
    )

    baseline_result = analyze_match_basic(
        request,
        candidate_profile_understanding=CandidateProfileUnderstanding(),
        requirement_priority_lookup={},
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    _disable_requirement_prioritization(monkeypatch)
    _disable_candidate_profile_understanding(monkeypatch)
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_type_with_openai",
        lambda *args, **kwargs: _build_requirement_type_output("language"),
    )
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_candidate_block_with_openai",
        lambda *_args, **_kwargs: RequirementCandidateMatchOutput(
            items=[
                RequirementCandidateMatchItem(
                    requirement_id="req_english",
                    suggested_status="matched",
                    grounding_strength="strong",
                    evidence_basis="hard_evidence",
                    reasoning_note="The normalized English language evidence supports fluent written and spoken communication.",
                    evidence_refs=[
                        RequirementCandidateEvidenceRef(
                            source_type="language",
                            source_id="language_001",
                            supporting_snippet="English | C1",
                        )
                    ],
                    supporting_signal_labels=["English", "fluent", "written", "spoken"],
                    missing_elements=[],
                )
            ]
        ),
    )

    result = analyze_match_basic(
        request,
        candidate_profile_understanding=CandidateProfileUnderstanding(),
        requirement_priority_lookup={},
    )
    requirement_match = _get_requirement_match(result, "req_english")

    assert baseline_result.requirement_matches[0].match_status == "partial"
    assert requirement_match.match_status == "matched"
    assert any("language 'English'" in text for text in requirement_match.evidence_texts)


def test_ai_semantic_matching_does_not_turn_declared_interest_into_hard_technical_match(
    monkeypatch,
) -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_ml_skill",
                "Hands-on machine learning experience",
                extracted_keywords=["machine learning"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            )
        ],
        candidate_overrides={"interest_entries": ["machine learning"]},
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    _disable_requirement_prioritization(monkeypatch)
    _disable_candidate_profile_understanding(monkeypatch)
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_type_with_openai",
        lambda *args, **kwargs: _build_requirement_type_output("technical_skill"),
    )
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_candidate_block_with_openai",
        lambda *_args, **_kwargs: RequirementCandidateMatchOutput(
            items=[
                RequirementCandidateMatchItem(
                    requirement_id="req_ml_skill",
                    suggested_status="matched",
                    grounding_strength="strong",
                    evidence_basis="declared_only",
                    reasoning_note="Only declared interest evidence is available for machine learning.",
                    evidence_refs=[
                        RequirementCandidateEvidenceRef(
                            source_type="interest",
                            source_id="interest_001",
                            supporting_snippet="machine learning",
                        )
                    ],
                    supporting_signal_labels=["machine learning"],
                    missing_elements=[],
                )
            ]
        ),
    )

    result = analyze_match_basic(
        request,
        candidate_profile_understanding=CandidateProfileUnderstanding(),
        requirement_priority_lookup={},
    )
    requirement_match = _get_requirement_match(result, "req_ml_skill")

    assert requirement_match.match_status == "missing"
    assert requirement_match.matched_project_ids == []
    assert requirement_match.matched_skill_names == []


def test_ai_semantic_matching_does_not_override_experience_year_threshold(monkeypatch) -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_openai_years",
                "3+ years of OpenAI experience",
                extracted_keywords=["OpenAI", "experience"],
                category="experience",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    _disable_requirement_prioritization(monkeypatch)
    _disable_candidate_profile_understanding(monkeypatch)
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_type_with_openai",
        lambda *args, **kwargs: _build_requirement_type_output("experience"),
    )
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_candidate_block_with_openai",
        lambda *_args, **_kwargs: RequirementCandidateMatchOutput(
            items=[
                RequirementCandidateMatchItem(
                    requirement_id="req_openai_years",
                    suggested_status="matched",
                    grounding_strength="strong",
                    evidence_basis="hard_evidence",
                    reasoning_note="A project strongly supports OpenAI experience, but documented years are still limited.",
                    evidence_refs=[
                        RequirementCandidateEvidenceRef(
                            source_type="project",
                            source_id="proj_001",
                            supporting_snippet="Robotics Demo Platform",
                        )
                    ],
                    supporting_signal_labels=["OpenAI"],
                    missing_elements=[],
                )
            ]
        ),
    )

    result = analyze_match_basic(
        request,
        candidate_profile_understanding=CandidateProfileUnderstanding(),
        requirement_priority_lookup={},
    )
    requirement_match = _get_requirement_match(result, "req_openai_years")

    assert requirement_match.match_status == "partial"
    assert "3+ years of documented experience" in requirement_match.missing_elements


def test_ai_semantic_matching_skips_application_constraints(monkeypatch) -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_availability",
                "Available 32 hours per week from Monday to Friday",
                extracted_keywords=["32 hours", "Monday-Friday"],
                category="other",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    _disable_requirement_prioritization(monkeypatch)
    _disable_candidate_profile_understanding(monkeypatch)
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_type_with_openai",
        lambda *args, **kwargs: _build_requirement_type_output("application_constraint"),
    )
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_candidate_block_with_openai",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("AI semantic matcher should not run for application constraints")
        ),
    )

    result = analyze_match_basic(
        request,
        candidate_profile_understanding=CandidateProfileUnderstanding(),
        requirement_priority_lookup={},
    )
    requirement_match = _get_requirement_match(result, "req_availability")

    assert requirement_match.match_status == "not_verifiable"


def test_declared_candidate_profile_signals_do_not_create_hard_technical_match() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_ml_skill",
                "Hands-on machine learning experience",
                extracted_keywords=["machine learning"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )
    understanding = CandidateProfileUnderstanding(
        source_signals=[
            CandidateSourceSignal(
                source_type="interest",
                source_id="interest_001",
                source_title="machine learning",
                signal_label="Machine learning",
                signal_kind="declared_interest",
                evidence_class="declared_signal",
                normalized_terms=["Machine learning"],
                supporting_snippets=["machine learning"],
                confidence="high",
                reasoning_note="The profile explicitly lists machine learning as an area of interest.",
            )
        ],
        profile_signals=[
            CandidateProfileSignal(
                signal_label="Machine learning",
                signal_kind="declared_interest",
                evidence_class="declared_signal",
                normalized_terms=["Machine learning"],
                source_refs=[
                    CandidateProfileSourceRef(source_type="interest", source_id="interest_001")
                ],
                confidence="high",
                reasoning_note="Canonical declared-interest signal aggregated from one profile declaration.",
            )
        ],
        language_normalizations=[],
        thematic_alignments=[
            CandidateThematicAlignment(
                theme_label="Machine learning",
                normalized_terms=["Machine learning"],
                source_refs=[
                    CandidateProfileSourceRef(source_type="interest", source_id="interest_001"),
                    CandidateProfileSourceRef(source_type="soft_skill", source_id="soft_skill_001"),
                ],
                confidence="medium",
                reasoning_note="The theme appears in multiple declared profile areas.",
            )
        ],
    )

    result = analyze_match_basic(
        request,
        candidate_profile_understanding=understanding,
    )
    requirement_match = _get_requirement_match(result, "req_ml_skill")

    assert requirement_match.match_status == "missing"
    assert requirement_match.matched_project_ids == []
    assert requirement_match.matched_skill_names == []


def test_exact_education_match_skips_ai_assistance(monkeypatch) -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_education_exact",
                "Engineering degree in Automation and Robotics",
                extracted_keywords=["Engineer", "Automation and Robotics"],
                category="education",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    _disable_requirement_prioritization(monkeypatch)
    _disable_candidate_profile_understanding(monkeypatch)
    _disable_ai_requirement_candidate_matching(monkeypatch)
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_type_with_openai",
        lambda *args, **kwargs: _build_requirement_type_output("education"),
    )
    monkeypatch.setattr(
        "app.services.match_service.evaluate_education_requirement_with_openai",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI should not run for exact deterministic education matches")),
    )

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_education_exact")

    assert requirement_match.match_status == "matched"
    assert "exact degree or field match" in requirement_match.explanation


def test_ai_assisted_education_can_upgrade_partial_match(monkeypatch) -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_education_partial",
                "Bachelor's degree in Electrical Engineering",
                extracted_keywords=["Bachelor degree", "Electrical Engineering"],
                category="education",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    _disable_requirement_prioritization(monkeypatch)
    _disable_candidate_profile_understanding(monkeypatch)
    _disable_ai_requirement_candidate_matching(monkeypatch)
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_type_with_openai",
        lambda *args, **kwargs: _build_requirement_type_output("education"),
    )
    monkeypatch.setattr(
        "app.services.match_service.evaluate_education_requirement_with_openai",
        lambda *args, **kwargs: OpenAIEducationRequirementMatchOutput(
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
        ),
    )

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_education_partial")

    assert requirement_match.match_status == "matched"
    assert requirement_match.explanation.startswith("AI-assisted education review:")
    assert any("Automation and Robotics" in evidence for evidence in requirement_match.evidence_texts)
    assert result.overall_score == 1.0


def test_ai_assisted_education_falls_back_to_deterministic_match_on_openai_error(monkeypatch) -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_education_partial",
                "Bachelor's degree in Electrical Engineering",
                extracted_keywords=["Bachelor degree", "Electrical Engineering"],
                category="education",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    _disable_requirement_prioritization(monkeypatch)
    _disable_ai_requirement_candidate_matching(monkeypatch)
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_type_with_openai",
        lambda *args, **kwargs: _build_requirement_type_output("education"),
    )

    def _raise_openai_error(*args, **kwargs):
        raise EducationRequirementMatchOpenAIError(
            "OpenAI education matching failed. Falling back to deterministic education matching.",
            reason="openai_error",
        )

    monkeypatch.setattr(
        "app.services.match_service.evaluate_education_requirement_with_openai",
        _raise_openai_error,
    )

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_education_partial")

    assert requirement_match.match_status == "partial"
    assert "related technical field" in requirement_match.explanation
    assert result.overall_score == 0.72




def test_ai_requirement_type_classifier_routes_application_constraints_out_of_technical_keyword_flow(monkeypatch) -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_plc",
                "Basic knowledge of PLC systems",
                extracted_keywords=["PLC"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            ),
            _build_requirement(
                "req_availability",
                "Available 30h/week for 6 months",
                extracted_keywords=["30h/week", "6 months"],
                category="other",
                requirement_type="must_have",
                importance="high",
            ),
        ]
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    _disable_requirement_prioritization(monkeypatch)
    _disable_candidate_profile_understanding(monkeypatch)

    def _classify(requirement, job_posting):
        if requirement.id == "req_availability":
            return _build_requirement_type_output(
                "application_constraint",
                reasoning_note="This requirement is about candidate availability and commitment.",
            )
        return _build_requirement_type_output("technical_skill")

    monkeypatch.setattr("app.services.match_service.evaluate_requirement_type_with_openai", _classify)

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_availability")

    assert requirement_match.match_status == "not_verifiable"
    assert "application constraint" in requirement_match.explanation
    assert result.overall_score == 1.0
    assert result.fit_classification == "high"
    assert result.recommendation == "generate_with_caution"


def test_requirement_prioritization_reorders_explainability_and_requirement_matches(monkeypatch) -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_fast_paced",
                "Experience in a fast-paced environment",
                extracted_keywords=["fast-paced"],
                category="soft_skill",
                requirement_type="nice_to_have",
                importance="low",
            ),
            _build_requirement(
                "req_communication",
                "Strong communication skills",
                extracted_keywords=["communication"],
                category="soft_skill",
                requirement_type="nice_to_have",
                importance="medium",
            ),
            _build_requirement(
                "req_plc",
                "Basic knowledge of PLC systems",
                extracted_keywords=["PLC"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            ),
        ],
        candidate_overrides={"soft_skill_entries": ["communication"]},
    )

    priority_lookup = {
        "req_plc": _build_requirement_priority_item(
            "req_plc",
            "core",
            reasoning_note="PLC defines the role's main technical bar.",
        ),
        "req_communication": _build_requirement_priority_item(
            "req_communication",
            "supporting",
            reasoning_note="Communication matters, but it does not define the role as strongly as PLC work.",
        ),
        "req_fast_paced": _build_requirement_priority_item(
            "req_fast_paced",
            "low_signal",
            reasoning_note="Fast-paced environment is too generic to be a strong differentiator.",
        ),
    }

    result = analyze_match_basic(request, requirement_priority_lookup=priority_lookup)

    assert [item.requirement_id for item in result.requirement_matches] == [
        "req_plc",
        "req_communication",
        "req_fast_paced",
    ]
    assert result.strengths[0] == "Matched core signal: Basic knowledge of PLC systems"
    assert result.gaps[0].startswith("Partially matched supporting signal:")
    assert result.gaps[1].startswith("Could not verify low-signal requirement:")
    assert "AI requirement prioritization identified 1 core, 1 supporting, and 1 low-signal requirements." in (
        result.final_summary
    )


def test_keyword_coverage_filters_noisy_user_facing_keywords() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_plc",
                "Basic knowledge of PLC systems",
                extracted_keywords=["PLC"],
                category="technology",
                requirement_type="must_have",
                importance="high",
            )
        ]
    )
    request.job_posting.keywords = [
        "PLC",
        "sta",
        "program",
        "support",
        "projects",
        "engineering",
        "mile widziany",
        "znajomość",
        "frameworki",
        "min. 1 rok",
        "AI",
        "SQL",
    ]

    result = analyze_match_basic(request)

    assert result.keyword_coverage == ["PLC"]
    assert "sta" not in result.final_summary
    assert "program" not in result.final_summary
    assert "mile widziany" not in result.final_summary
    assert "frameworki" not in result.final_summary


def test_keyword_coverage_is_capped_for_user_facing_summary() -> None:
    payload = _load_base_payload()
    payload["job_posting"]["requirements"] = [
        _build_requirement(
            "req_keywords",
            "Broad automation tooling exposure",
            extracted_keywords=["PLC"],
            category="technology",
            requirement_type="must_have",
            importance="high",
        )
    ]
    payload["job_posting"]["keywords"] = [
        "PLC",
        "SQL",
        "AI",
        "commissioning",
        "technical documentation",
        "robotics",
        "automation",
        "testing",
        "SCADA",
        "HMI",
    ]
    payload["candidate_profile"]["skill_entries"].extend(
        [
            {
                "name": "SQL",
                "category": "technology",
                "level": "intermediate",
                "years_of_experience": 1,
                "evidence_sources": [],
                "aliases": [],
            },
            {
                "name": "SCADA",
                "category": "technology",
                "level": "intermediate",
                "years_of_experience": 1,
                "evidence_sources": [],
                "aliases": [],
            },
            {
                "name": "HMI",
                "category": "technology",
                "level": "intermediate",
                "years_of_experience": 1,
                "evidence_sources": [],
                "aliases": [],
            },
        ]
    )
    payload["candidate_profile"]["experience_entries"][0]["keywords"].extend(
        ["commissioning", "technical documentation", "automation", "testing"]
    )
    payload["candidate_profile"]["project_entries"][0]["keywords"].append("robotics")

    request = MatchAnalysisRequest.model_validate(payload)
    result = analyze_match_basic(request)

    assert len(result.keyword_coverage) == 8
    assert result.keyword_coverage == [
        "PLC",
        "SQL",
        "commissioning",
        "technical documentation",
        "robotics",
        "automation",
        "testing",
        "SCADA",
    ]
    assert "AI" not in result.keyword_coverage
    assert "HMI" not in result.keyword_coverage


def test_requirement_type_classifier_falls_back_to_heuristics_when_openai_classification_fails(monkeypatch) -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_language",
                "English at advanced level",
                category="language",
                extracted_keywords=["English", "advanced"],
                requirement_type="nice_to_have",
                importance="medium",
            )
        ]
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    _disable_requirement_prioritization(monkeypatch)
    _disable_candidate_profile_understanding(monkeypatch)
    _disable_ai_requirement_candidate_matching(monkeypatch)

    def _raise_classifier_error(*args, **kwargs):
        raise RequirementTypeClassificationOpenAIError(
            "OpenAI requirement classification failed. Falling back to heuristic requirement classification.",
            reason="openai_error",
        )

    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_type_with_openai",
        _raise_classifier_error,
    )

    result = analyze_match_basic(request)
    requirement_match = _get_requirement_match(result, "req_language")

    assert requirement_match.match_status == "partial"
    assert "language requirement" in requirement_match.explanation


def test_analyze_match_artifacts_exposes_debug_breakdown_for_manual_confirmation() -> None:
    request = _build_request(
        [
            _build_requirement(
                "req_python",
                "Python basics",
                extracted_keywords=["Python"],
                requirement_type="must_have",
                importance="high",
            ),
            _build_requirement(
                "req_availability",
                "Available 30h/week for 6 months",
                extracted_keywords=["30h/week", "6 months"],
                category="other",
                requirement_type="must_have",
                importance="high",
            ),
        ]
    )
    priority_lookup = {
        "req_python": _build_requirement_priority_item("req_python", "core"),
        "req_availability": _build_requirement_priority_item("req_availability", "supporting"),
    }

    artifacts = analyze_match_artifacts(
        request,
        requirement_priority_lookup=priority_lookup,
        candidate_profile_understanding=CandidateProfileUnderstanding(),
    )

    assert artifacts.matching_debug["score_breakdown"]["manual_confirmation_requirement_count"] == 1
    assert artifacts.matching_debug["priority_summary"]["core_count"] == 1
    assert artifacts.matching_debug["priority_summary"]["supporting_count"] == 1
    assert artifacts.matching_debug["manual_confirmation_context"][0]["requirement_id"] == "req_availability"
    availability_debug = next(
        item
        for item in artifacts.matching_debug["requirement_debug"]
        if item["requirement_id"] == "req_availability"
    )
    assert availability_debug["scoring_bucket"] == "manual_confirmation"
    assert availability_debug["priority_tier"] == "supporting"
    assert "matching_only_signals" in artifacts.matching_debug["operational_context"]
