import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.match import MatchResult


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
            assert requirement_match["match_status"] in {"matched", "partial", "missing"}
            assert requirement_match["explanation"]
