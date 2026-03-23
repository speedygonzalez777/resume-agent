import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.match import MatchResult
from app.services.openai_education_match_service import OpenAIEducationRequirementMatchOutput
from app.services.openai_requirement_type_service import OpenAIRequirementTypeClassificationOutput


def test_match_analyze_returns_match_result_structure() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    with TestClient(app) as client:
        response = client.post("/match/analyze", json=payload)

        assert response.status_code == 200

        body = response.json()
        parsed_result = MatchResult.model_validate(body)

        assert "overall_score" in body
        assert "fit_classification" in body
        assert "recommendation" in body
        assert "requirement_matches" in body
        assert "strengths" in body
        assert "gaps" in body
        assert "keyword_coverage" in body
        assert "final_summary" in body

        assert len(body["requirement_matches"]) == len(payload["job_posting"]["requirements"])
        assert len(parsed_result.requirement_matches) == len(payload["job_posting"]["requirements"])

        for requirement_match in body["requirement_matches"]:
            assert "requirement_id" in requirement_match
            assert "match_status" in requirement_match
            assert "explanation" in requirement_match
            assert requirement_match["match_status"] in {"matched", "partial", "missing", "not_verifiable"}
            assert requirement_match["explanation"]


def test_match_analyze_returns_not_verifiable_for_formal_requirement() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["job_posting"]["requirements"] = [
        {
            "id": "req_plc",
            "text": "Basic knowledge of PLC systems",
            "category": "technology",
            "requirement_type": "must_have",
            "importance": "high",
            "extracted_keywords": ["PLC"],
        },
        {
            "id": "req_age",
            "text": "Must be at least 18 years old",
            "category": "other",
            "requirement_type": "must_have",
            "importance": "high",
            "extracted_keywords": ["18 years", "age"],
        },
    ]
    payload["job_posting"]["keywords"] = ["PLC", "18 years", "age"]

    with TestClient(app) as client:
        response = client.post("/match/analyze", json=payload)

    assert response.status_code == 200

    body = response.json()
    parsed_result = MatchResult.model_validate(body)
    requirement_matches = {item.requirement_id: item for item in parsed_result.requirement_matches}

    assert requirement_matches["req_plc"].match_status == "matched"
    assert requirement_matches["req_age"].match_status == "not_verifiable"
    assert parsed_result.overall_score == 1.0
    assert parsed_result.fit_classification == "high"
    assert parsed_result.recommendation == "generate_with_caution"


def test_match_analyze_can_return_ai_assisted_education_match(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["job_posting"]["requirements"] = [
        {
            "id": "req_education_partial",
            "text": "Bachelor's degree in Electrical Engineering",
            "category": "education",
            "requirement_type": "must_have",
            "importance": "high",
            "extracted_keywords": ["Bachelor degree", "Electrical Engineering"],
        }
    ]
    payload["job_posting"]["keywords"] = ["Electrical Engineering"]

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_type_with_openai",
        lambda *args, **kwargs: OpenAIRequirementTypeClassificationOutput(
            normalized_requirement_type="education",
            confidence="high",
            reasoning_note="This requirement is clearly educational.",
        ),
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

    with TestClient(app) as client:
        response = client.post("/match/analyze", json=payload)

    assert response.status_code == 200

    parsed_result = MatchResult.model_validate(response.json())
    requirement_match = parsed_result.requirement_matches[0]

    assert requirement_match.requirement_id == "req_education_partial"
    assert requirement_match.match_status == "matched"
    assert requirement_match.explanation.startswith("AI-assisted education review:")
    assert parsed_result.overall_score == 1.0


def test_match_analyze_can_use_ai_requirement_type_classifier_for_application_constraint(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["job_posting"]["requirements"] = [
        {
            "id": "req_plc",
            "text": "Basic knowledge of PLC systems",
            "category": "technology",
            "requirement_type": "must_have",
            "importance": "high",
            "extracted_keywords": ["PLC"],
        },
        {
            "id": "req_availability",
            "text": "Available 30h/week for 6 months",
            "category": "other",
            "requirement_type": "must_have",
            "importance": "high",
            "extracted_keywords": ["30h/week", "6 months"],
        },
    ]
    payload["job_posting"]["keywords"] = ["PLC", "30h/week", "6 months"]

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")

    def _classify(requirement, job_posting):
        if requirement.id == "req_availability":
            return OpenAIRequirementTypeClassificationOutput(
                normalized_requirement_type="application_constraint",
                confidence="high",
                reasoning_note="This requirement is about availability and commitment.",
            )
        return OpenAIRequirementTypeClassificationOutput(
            normalized_requirement_type="technical_skill",
            confidence="high",
            reasoning_note="This requirement names a technical capability.",
        )

    monkeypatch.setattr("app.services.match_service.evaluate_requirement_type_with_openai", _classify)

    with TestClient(app) as client:
        response = client.post("/match/analyze", json=payload)

    assert response.status_code == 200

    parsed_result = MatchResult.model_validate(response.json())
    requirement_matches = {item.requirement_id: item for item in parsed_result.requirement_matches}

    assert requirement_matches["req_plc"].match_status == "matched"
    assert requirement_matches["req_availability"].match_status == "not_verifiable"
    assert "application constraint" in requirement_matches["req_availability"].explanation
    assert parsed_result.overall_score == 1.0
    assert parsed_result.recommendation == "generate_with_caution"
