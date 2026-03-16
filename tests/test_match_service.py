import json
from pathlib import Path
from typing import Any

from app.models.analysis import MatchAnalysisRequest
from app.services.match_service import analyze_match_basic

_MATCH_PAYLOAD_FIXTURE = Path("data/match_analysis_test.json")


def _load_base_payload() -> dict[str, Any]:
    """Load the reusable match-analysis fixture payload from disk."""
    return json.loads(_MATCH_PAYLOAD_FIXTURE.read_text(encoding="utf-8"))


def _build_requirement(
    requirement_id: str,
    text: str,
    *,
    extracted_keywords: list[str],
    requirement_type: str = "nice_to_have",
    importance: str = "medium",
) -> dict[str, Any]:
    """Build a lightweight requirement payload for service-level scoring tests."""
    return {
        "id": requirement_id,
        "text": text,
        "category": "technology",
        "requirement_type": requirement_type,
        "importance": importance,
        "extracted_keywords": extracted_keywords,
    }


def _build_request(requirements: list[dict[str, Any]]) -> MatchAnalysisRequest:
    """Create a MatchAnalysisRequest with custom job requirements."""
    payload = _load_base_payload()
    payload["job_posting"]["requirements"] = requirements

    job_keywords: list[str] = []
    for requirement in requirements:
        for keyword in requirement["extracted_keywords"]:
            if keyword not in job_keywords:
                job_keywords.append(keyword)
    payload["job_posting"]["keywords"] = job_keywords

    return MatchAnalysisRequest.model_validate(payload)


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
                "Communicative English",
                extracted_keywords=["English", "communication"],
                requirement_type="nice_to_have",
                importance="low",
            ),
        ]
    )

    result = analyze_match_basic(request)

    assert result.requirement_matches[0].match_status == "matched"
    assert result.requirement_matches[1].match_status == "partial"
    assert result.overall_score == 0.89


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
