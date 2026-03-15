import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import reset_database_state
from app.main import app
from app.models.candidate import CandidateProfile


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    temp_db_path = Path("data") / f"test_resume_agent_{uuid4().hex}.db"
    database_url = f"sqlite:///{temp_db_path.resolve().as_posix()}"
    monkeypatch.setenv("RESUME_AGENT_DB_URL", database_url)
    reset_database_state()

    with TestClient(app) as test_client:
        yield test_client

    reset_database_state()
    if temp_db_path.exists():
        temp_db_path.unlink()


def test_profile_persistence_endpoints(client: TestClient) -> None:
    payload = _load_json("candidate_profile_test.json")
    normalized_payload = CandidateProfile.model_validate(payload).model_dump(mode="json")

    save_response = client.post("/profile/save", json=payload)
    assert save_response.status_code == 200

    stored_profile = save_response.json()
    profile_id = stored_profile["id"]

    assert stored_profile["full_name"] == payload["personal_info"]["full_name"]
    assert stored_profile["payload"] == normalized_payload

    get_response = client.get(f"/profile/{profile_id}")
    assert get_response.status_code == 200
    assert get_response.json()["payload"] == normalized_payload


def test_job_persistence_endpoints(client: TestClient) -> None:
    payload = _load_json("job_posting_test.json")

    save_response = client.post(
        "/job/save",
        json={
            "job_posting": payload,
            "source_url": "https://example.com/jobs/python-role",
        },
    )
    assert save_response.status_code == 200

    stored_job = save_response.json()
    job_id = stored_job["id"]

    assert stored_job["source_url"] == "https://example.com/jobs/python-role"
    assert stored_job["payload"] == payload

    list_response = client.get("/job")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] == job_id

    get_response = client.get(f"/job/{job_id}")
    assert get_response.status_code == 200
    assert get_response.json()["payload"] == payload


def test_match_result_persistence_endpoints(client: TestClient) -> None:
    analyze_payload = _load_json("match_analysis_test.json")

    analyze_response = client.post("/match/analyze", json=analyze_payload)
    assert analyze_response.status_code == 200

    save_response = client.post(
        "/match/save",
        json={
            "match_result": analyze_response.json(),
            "candidate_profile_id": 1,
            "job_posting_id": 1,
        },
    )
    assert save_response.status_code == 200

    stored_match = save_response.json()
    match_id = stored_match["id"]

    assert stored_match["candidate_profile_id"] == 1
    assert stored_match["job_posting_id"] == 1
    assert stored_match["payload"]["fit_classification"] in {"high", "medium", "low"}

    list_response = client.get("/match")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] == match_id

    get_response = client.get(f"/match/{match_id}")
    assert get_response.status_code == 200
    assert get_response.json()["payload"] == analyze_response.json()


def _load_json(filename: str) -> dict:
    return json.loads(Path("data", filename).read_text(encoding="utf-8"))
