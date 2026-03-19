import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.resume import ChangeReport, ResumeDraft


def test_resume_generate_returns_structured_draft_and_report() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    with TestClient(app) as client:
        match_response = client.post("/match/analyze", json=payload)
        assert match_response.status_code == 200

        response = client.post(
            "/resume/generate",
            json={
                "candidate_profile": payload["candidate_profile"],
                "job_posting": payload["job_posting"],
                "match_result": match_response.json(),
            },
        )

    assert response.status_code == 200

    body = response.json()
    parsed_resume_draft = ResumeDraft.model_validate(body["resume_draft"])
    parsed_change_report = ChangeReport.model_validate(body["change_report"])

    assert parsed_resume_draft.header.full_name == payload["candidate_profile"]["personal_info"]["full_name"]
    assert parsed_resume_draft.selected_experience_entries
    assert parsed_change_report.detected_keywords == payload["job_posting"]["keywords"]
