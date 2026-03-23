import json
from pathlib import Path
from typing import Any

from app.models.analysis import MatchAnalysisRequest
from app.services.match_service import analyze_match_basic
from app.services.openai_education_match_service import (
    EducationRequirementMatchOpenAIError,
    OpenAIEducationRequirementMatchOutput,
)
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
    assert result.overall_score == 0.91


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

    assert low_importance_result.overall_score == 0.64
    assert high_importance_result.overall_score == 0.41
    assert low_importance_result.overall_score > high_importance_result.overall_score


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
    assert must_have_result.overall_score == 0.42
    assert nice_to_have_result.overall_score > must_have_result.overall_score


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

    assert result.overall_score == 0.84
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

    assert result.overall_score == 0.85
    assert result.fit_classification == "medium"
    assert result.recommendation == "generate_with_caution"


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

    assert result.overall_score == 0.8
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
    assert result.overall_score == 0.5
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
    assert result.overall_score == 0.5




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
