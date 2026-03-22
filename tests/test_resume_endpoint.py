import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes_resume import ResumeGenerationResponse
from app.main import app
from app.db import reset_database_state
from app.models.resume import (
    ResumeFallbackReason,
    ResumeGenerationMode,
    ResumeMatchResultSource,
)

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="Project supports Python 3.12+; in-process FastAPI sync-route tests are unreliable on Python 3.11.0rc1.",
)


@pytest.fixture(autouse=True)
def isolated_resume_endpoint_db(monkeypatch, tmp_path) -> None:
    database_path = tmp_path / "resume-endpoint-test.db"
    monkeypatch.setenv("RESUME_AGENT_DB_URL", f"sqlite:///{database_path}")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    reset_database_state()
    yield
    reset_database_state()


def test_resume_generate_returns_structured_draft_and_report(monkeypatch) -> None:
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

    parsed_response = ResumeGenerationResponse.model_validate(response.json())

    assert parsed_response.generation_mode is ResumeGenerationMode.RULE_BASED_FALLBACK
    assert parsed_response.match_result_source is ResumeMatchResultSource.PROVIDED
    assert parsed_response.fallback_reason is ResumeFallbackReason.MISSING_API_KEY
    assert parsed_response.generation_notes
    assert (
        parsed_response.resume_draft.header.full_name
        == payload["candidate_profile"]["personal_info"]["full_name"]
    )
    assert parsed_response.resume_draft.selected_experience_entries
    assert parsed_response.change_report.detected_keywords == [
        "PLC",
        "automation",
        "technical documentation",
        "commissioning",
        "English",
        "communication",
    ]


def test_resume_generate_can_compute_match_when_not_supplied() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    with TestClient(app) as client:
        response = client.post(
            "/resume/generate",
            json={
                "candidate_profile": payload["candidate_profile"],
                "job_posting": payload["job_posting"],
            },
        )

    assert response.status_code == 200

    parsed_response = ResumeGenerationResponse.model_validate(response.json())

    assert parsed_response.generation_mode is ResumeGenerationMode.RULE_BASED_FALLBACK
    assert parsed_response.match_result_source is ResumeMatchResultSource.COMPUTED
    assert parsed_response.fallback_reason is ResumeFallbackReason.MISSING_API_KEY
    assert parsed_response.resume_draft.target_job_title == payload["job_posting"]["title"]
    assert parsed_response.change_report.warnings
