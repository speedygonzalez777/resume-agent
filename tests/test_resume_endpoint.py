import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes_resume import (
    ResumeDraftListItem,
    ResumeDraftRefinementResponse,
    ResumeGenerationResponse,
    StoredResumeDraftResponse,
)
from app.main import app
from app.db import reset_database_state
from app.models.analysis import MatchAnalysisRequest
from app.models.resume import (
    ResumeFallbackReason,
    ResumeGenerationMode,
    ResumeMatchResultSource,
)
from app.services.match_service import analyze_match_basic
from app.services.persistence_service import save_resume_draft
from app.services.resume_generation_service import generate_resume_artifacts

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
    assert sorted(parsed_response.change_report.detected_keywords) == sorted(
        [
            "PLC",
            "automation",
            "technical documentation",
            "commissioning",
            "English",
            "communication",
        ]
    )
    assert parsed_response.offer_signal_debug is not None
    assert "generation_eligible_offer_terms" in parsed_response.offer_signal_debug
    assert parsed_response.generation_debug is not None
    assert "selected_skills" in parsed_response.generation_debug


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


def test_resume_generate_accepts_matching_handoff() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    with TestClient(app) as client:
        debug_response = client.post("/match/analyze-debug", json=payload)
        assert debug_response.status_code == 200

        debug_body = debug_response.json()
        response = client.post(
            "/resume/generate",
            json={
                "candidate_profile": payload["candidate_profile"],
                "job_posting": payload["job_posting"],
                "match_result": debug_body["match_result"],
                "matching_handoff": debug_body["matching_handoff"],
            },
        )

    assert response.status_code == 200

    parsed_response = ResumeGenerationResponse.model_validate(response.json())

    assert parsed_response.generation_debug is not None
    assert parsed_response.generation_debug["semantic_handoff"]["matching_handoff_supplied"] is True
    assert parsed_response.generation_debug["semantic_handoff"]["reused_sidecars"] == [
        "requirement_priority_lookup",
    ]
    assert parsed_response.generation_debug["semantic_handoff"]["locally_computed_sidecars"] == []


def test_resume_generate_persists_draft_and_exposes_it_in_history() -> None:
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
                "candidate_profile_id": 11,
                "job_posting_id": 22,
                "match_result_id": 33,
            },
        )

        list_response = client.get("/resume/drafts?candidate_profile_id=11&job_posting_id=22")

    assert response.status_code == 200
    assert list_response.status_code == 200

    parsed_response = ResumeGenerationResponse.model_validate(response.json())
    list_items = [ResumeDraftListItem.model_validate(item) for item in list_response.json()]

    assert parsed_response.resume_draft_record_id is not None
    assert parsed_response.resume_draft_saved_at is not None
    assert parsed_response.persistence_warning is None
    assert len(list_items) == 1
    assert list_items[0].id == parsed_response.resume_draft_record_id
    assert list_items[0].target_job_title == payload["job_posting"]["title"]
    assert list_items[0].target_company_name == payload["job_posting"]["company_name"]
    assert list_items[0].has_refined_version is False

    with TestClient(app) as client:
        detail_response = client.get(f"/resume/drafts/{parsed_response.resume_draft_record_id}")

    assert detail_response.status_code == 200

    stored_draft = StoredResumeDraftResponse.model_validate(detail_response.json())

    assert stored_draft.id == parsed_response.resume_draft_record_id
    assert stored_draft.candidate_profile_id == 11
    assert stored_draft.job_posting_id == 22
    assert stored_draft.match_result_id == 33
    assert stored_draft.target_job_title == payload["job_posting"]["title"]
    assert stored_draft.target_company_name == payload["job_posting"]["company_name"]
    assert stored_draft.base_resume_artifacts.resume_draft_record_id == parsed_response.resume_draft_record_id
    assert stored_draft.base_resume_artifacts.resume_draft.target_company_name == payload["job_posting"]["company_name"]
    assert stored_draft.resume_debug_envelope.matching_handoff is False
    assert stored_draft.resume_debug_envelope.request_body is not None
    assert stored_draft.resume_debug_envelope.request_body["candidate_profile_id"] == 11
    assert stored_draft.resume_debug_envelope.request_body["job_posting_id"] == 22
    assert stored_draft.resume_debug_envelope.request_body["match_result_id"] == 33
    assert stored_draft.resume_debug_envelope.response_body is not None
    assert (
        stored_draft.resume_debug_envelope.response_body["resume_draft_record_id"]
        == parsed_response.resume_draft_record_id
    )
    assert stored_draft.resume_debug_envelope.request_body_unavailable_reason is None
    assert stored_draft.refined_resume_artifacts is None


def test_resume_draft_detail_falls_back_for_legacy_records_without_saved_request_body() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)
    match_result = analyze_match_basic(request)
    artifacts = ResumeGenerationResponse.model_validate(
        generate_resume_artifacts(
            request.candidate_profile,
            request.job_posting,
            match_result,
        )
    )

    with TestClient(app) as client:
        stored_record = save_resume_draft(
            candidate_profile_id=5,
            job_posting_id=6,
            match_result_id=7,
            target_job_title=artifacts.resume_draft.target_job_title,
            target_company_name=artifacts.resume_draft.target_company_name,
            generation_mode=artifacts.generation_mode.value,
            base_resume_artifacts=artifacts.model_dump(
                mode="json",
                exclude={"resume_draft_record_id", "resume_draft_saved_at", "persistence_warning"},
            ),
        )
        detail_response = client.get(f"/resume/drafts/{stored_record['id']}")

    assert detail_response.status_code == 200

    stored_draft = StoredResumeDraftResponse.model_validate(detail_response.json())

    assert stored_draft.id == stored_record["id"]
    assert stored_draft.resume_debug_envelope.request_body is None
    assert stored_draft.resume_debug_envelope.matching_handoff is None
    assert stored_draft.resume_debug_envelope.response_body is not None
    assert stored_draft.resume_debug_envelope.response_body["resume_draft_record_id"] == stored_record["id"]
    assert (
        stored_draft.resume_debug_envelope.request_body_unavailable_reason
        == "Historyczny request resume nie zostal zapisany dla tego draftu."
    )


def test_resume_generate_returns_draft_even_when_persistence_save_fails(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    def _broken_save_resume_draft(*_args, **_kwargs):
        raise RuntimeError("sqlite unavailable")

    monkeypatch.setattr("app.api.routes_resume.save_resume_draft", _broken_save_resume_draft)

    with TestClient(app) as client:
        response = client.post(
            "/resume/generate",
            json={
                "candidate_profile": payload["candidate_profile"],
                "job_posting": payload["job_posting"],
            },
        )
        list_response = client.get("/resume/drafts")

    assert response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json() == []

    parsed_response = ResumeGenerationResponse.model_validate(response.json())

    assert parsed_response.resume_draft_record_id is None
    assert parsed_response.resume_draft_saved_at is None
    assert parsed_response.persistence_warning == "Generated draft could not be saved to local SQLite storage."
    assert parsed_response.resume_draft.target_job_title == payload["job_posting"]["title"]
    assert parsed_response.change_report.warnings


def test_resume_refine_draft_returns_refined_resume_without_re_running_generation(
    monkeypatch,
) -> None:
    def _unexpected_generation_call(*_args, **_kwargs):
        raise AssertionError("generate_resume_artifacts should not be called by /resume/refine-draft")

    def _fake_refine_resume_draft(*_args, **_kwargs):
        return {
            "refined_resume_draft": {
                "header": {
                    "full_name": "Jan Kowalski",
                    "professional_headline": "PLC Automation Engineer",
                    "email": "jan@example.com",
                    "phone": "+48 555 111 222",
                    "location": "Krakow",
                    "links": ["https://linkedin.com/in/jankowalski"],
                },
                "target_job_title": "Automation Engineer",
                "target_company_name": "Example Automation",
                "fit_summary": "Strong fit for PLC-heavy automation role.",
                "professional_summary": "Automation engineer focused on PLC commissioning and reporting standardization.",
                "selected_skills": ["PLC", "Python"],
                "selected_experience_entries": [
                    {
                        "source_experience_id": "exp_1",
                        "company_name": "Factory Systems",
                        "position_title": "Automation Engineer",
                        "date_range": "2021-2024",
                        "bullet_points": [
                            "Commissioned PLC lines for production plants.",
                            "Led SAP rollout for reporting standardization.",
                        ],
                        "highlighted_keywords": ["PLC", "reporting"],
                        "relevance_note": "Strong factory automation fit.",
                        "source_highlights": ["PLC commissioning", "SAP reporting"],
                    }
                ],
                "selected_project_entries": [],
                "selected_education_entries": ["BSc Automation and Robotics"],
                "selected_language_entries": ["English - B2"],
                "selected_certificate_entries": ["Siemens PLC Certificate"],
                "selected_keywords": ["PLC", "reporting"],
                "keyword_usage": ["PLC", "reporting"],
            },
            "refinement_patch": {
                "header": {
                    "professional_headline": "PLC Automation Engineer",
                },
                "professional_summary": "Automation engineer focused on PLC commissioning and reporting standardization.",
                "selected_skills": ["PLC", "Python"],
                "selected_keywords": ["PLC", "reporting"],
                "keyword_usage": ["PLC", "reporting"],
                "selected_experience_entries": [
                    {
                        "source_experience_id": "exp_1",
                        "bullet_points": [
                            "Commissioned PLC lines for production plants.",
                            "Led SAP rollout for reporting standardization.",
                        ],
                        "highlighted_keywords": ["PLC", "reporting"],
                    }
                ],
                "selected_project_entries": [],
            },
        }

    monkeypatch.setattr(
        "app.api.routes_resume.generate_resume_artifacts",
        _unexpected_generation_call,
    )
    monkeypatch.setattr(
        "app.api.routes_resume.refine_resume_draft_service",
        _fake_refine_resume_draft,
    )

    with TestClient(app) as client:
        response = client.post(
            "/resume/refine-draft",
            json={
                "resume_draft": {
                    "header": {
                        "full_name": "Jan Kowalski",
                        "professional_headline": "Automation Engineer",
                        "email": "jan@example.com",
                        "phone": "+48 555 111 222",
                        "location": "Krakow",
                        "links": ["https://linkedin.com/in/jankowalski"],
                    },
                    "target_job_title": "Automation Engineer",
                    "target_company_name": "Example Automation",
                    "fit_summary": "Strong fit for PLC-heavy automation role.",
                    "professional_summary": "Automation engineer focused on PLC commissioning and SAP reporting.",
                    "selected_skills": ["PLC", "Python", "SAP"],
                    "selected_experience_entries": [
                        {
                            "source_experience_id": "exp_1",
                            "company_name": "Factory Systems",
                            "position_title": "Automation Engineer",
                            "date_range": "2021-2024",
                            "bullet_points": [
                                "Commissioned PLC lines for production plants.",
                                "Led expert SAP rollout for reporting standardization.",
                            ],
                            "highlighted_keywords": ["PLC", "SAP"],
                            "relevance_note": "Strong factory automation fit.",
                            "source_highlights": ["PLC commissioning", "SAP reporting"],
                        }
                    ],
                    "selected_project_entries": [],
                    "selected_education_entries": ["BSc Automation and Robotics"],
                    "selected_language_entries": ["English - B2"],
                    "selected_certificate_entries": ["Siemens PLC Certificate"],
                    "selected_keywords": ["PLC", "SAP"],
                    "keyword_usage": ["PLC", "SAP"],
                },
                "guidance": {
                    "must_include_terms": ["PLC"],
                    "avoid_or_deemphasize_terms": ["SAP"],
                    "forbidden_claims_or_phrases": ["expert"],
                    "skills_allowlist": ["PLC", "Python"],
                    "additional_instructions": "Keep the tone concise.",
                },
            },
        )

    assert response.status_code == 200

    parsed_response = ResumeDraftRefinementResponse.model_validate(response.json())

    assert parsed_response.refined_resume_draft.selected_skills == ["PLC", "Python"]
    assert parsed_response.refined_resume_draft.header.full_name == "Jan Kowalski"
    assert parsed_response.refined_resume_draft.selected_experience_entries[0].bullet_points == [
        "Commissioned PLC lines for production plants.",
        "Led SAP rollout for reporting standardization.",
    ]
    assert parsed_response.refinement_patch.selected_skills == ["PLC", "Python"]
    assert parsed_response.refinement_patch.selected_keywords == ["PLC", "reporting"]


def test_resume_refine_draft_updates_existing_saved_record(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    def _fake_refine_resume_draft(*_args, **_kwargs):
        return {
            "refined_resume_draft": {
                "header": {
                    "full_name": "Jan Kowalski",
                    "professional_headline": "PLC Automation Engineer",
                    "email": "jan@example.com",
                    "phone": "+48 555 111 222",
                    "location": "Krakow",
                    "links": ["https://linkedin.com/in/jankowalski"],
                },
                "target_job_title": "Automation Engineer",
                "target_company_name": "Example Automation",
                "fit_summary": "Strong fit for PLC-heavy automation role.",
                "professional_summary": "Automation engineer focused on PLC commissioning and reporting standardization.",
                "selected_skills": ["PLC", "Python"],
                "selected_experience_entries": [
                    {
                        "source_experience_id": "exp_1",
                        "company_name": "Factory Systems",
                        "position_title": "Automation Engineer",
                        "date_range": "2021-2024",
                        "bullet_points": [
                            "Commissioned PLC lines for production plants.",
                            "Led SAP rollout for reporting standardization.",
                        ],
                        "highlighted_keywords": ["PLC", "reporting"],
                        "relevance_note": "Strong factory automation fit.",
                        "source_highlights": ["PLC commissioning", "SAP reporting"],
                    }
                ],
                "selected_project_entries": [],
                "selected_education_entries": ["BSc Automation and Robotics"],
                "selected_language_entries": ["English - B2"],
                "selected_certificate_entries": ["Siemens PLC Certificate"],
                "selected_keywords": ["PLC", "reporting"],
                "keyword_usage": ["PLC", "reporting"],
            },
            "refinement_patch": {
                "header": {
                    "professional_headline": "PLC Automation Engineer",
                },
                "professional_summary": "Automation engineer focused on PLC commissioning and reporting standardization.",
                "selected_skills": ["PLC", "Python"],
                "selected_keywords": ["PLC", "reporting"],
                "keyword_usage": ["PLC", "reporting"],
                "selected_experience_entries": [
                    {
                        "source_experience_id": "exp_1",
                        "bullet_points": [
                            "Commissioned PLC lines for production plants.",
                            "Led SAP rollout for reporting standardization.",
                        ],
                        "highlighted_keywords": ["PLC", "reporting"],
                    }
                ],
                "selected_project_entries": [],
            },
        }

    monkeypatch.setattr(
        "app.api.routes_resume.refine_resume_draft_service",
        _fake_refine_resume_draft,
    )

    with TestClient(app) as client:
        generate_response = client.post(
            "/resume/generate",
            json={
                "candidate_profile": payload["candidate_profile"],
                "job_posting": payload["job_posting"],
                "candidate_profile_id": 1,
                "job_posting_id": 2,
            },
        )
        assert generate_response.status_code == 200

        generated_payload = ResumeGenerationResponse.model_validate(generate_response.json())
        assert generated_payload.resume_draft_record_id is not None

        refine_response = client.post(
            "/resume/refine-draft",
            json={
                "resume_draft": generated_payload.resume_draft.model_dump(mode="json"),
                "guidance": {
                    "must_include_terms": ["PLC"],
                    "avoid_or_deemphasize_terms": ["SAP"],
                    "forbidden_claims_or_phrases": ["expert"],
                    "skills_allowlist": ["PLC", "Python"],
                    "additional_instructions": "Keep the tone concise.",
                },
                "resume_draft_record_id": generated_payload.resume_draft_record_id,
            },
        )
        detail_response = client.get(f"/resume/drafts/{generated_payload.resume_draft_record_id}")

    assert refine_response.status_code == 200
    assert detail_response.status_code == 200

    parsed_refinement = ResumeDraftRefinementResponse.model_validate(refine_response.json())
    stored_draft = StoredResumeDraftResponse.model_validate(detail_response.json())

    assert parsed_refinement.resume_draft_record_id == generated_payload.resume_draft_record_id
    assert parsed_refinement.resume_draft_updated_at is not None
    assert parsed_refinement.persistence_warning is None
    assert stored_draft.has_refined_version is True
    assert stored_draft.refined_resume_artifacts is not None
    assert stored_draft.refined_resume_artifacts.refined_resume_draft.selected_skills == ["PLC", "Python"]


def test_resume_refine_draft_returns_readable_error_when_openai_key_is_missing() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/resume/refine-draft",
            json={
                "resume_draft": {
                    "header": {
                        "full_name": "Jan Kowalski",
                        "professional_headline": "Automation Engineer",
                        "email": "jan@example.com",
                        "phone": "+48 555 111 222",
                        "location": "Krakow",
                        "links": ["https://linkedin.com/in/jankowalski"],
                    },
                    "target_job_title": "Automation Engineer",
                    "target_company_name": "Example Automation",
                    "fit_summary": "Strong fit for PLC-heavy automation role.",
                    "professional_summary": "Automation engineer focused on PLC commissioning and SAP reporting.",
                    "selected_skills": ["PLC", "Python", "SAP"],
                    "selected_experience_entries": [
                        {
                            "source_experience_id": "exp_1",
                            "company_name": "Factory Systems",
                            "position_title": "Automation Engineer",
                            "date_range": "2021-2024",
                            "bullet_points": [
                                "Commissioned PLC lines for production plants."
                            ],
                            "highlighted_keywords": ["PLC", "SAP"],
                            "relevance_note": "Strong factory automation fit.",
                            "source_highlights": ["PLC commissioning", "SAP reporting"],
                        }
                    ],
                    "selected_project_entries": [],
                    "selected_education_entries": ["BSc Automation and Robotics"],
                    "selected_language_entries": ["English - B2"],
                    "selected_certificate_entries": ["Siemens PLC Certificate"],
                    "selected_keywords": ["PLC", "SAP"],
                    "keyword_usage": ["PLC", "SAP"],
                },
                "guidance": {
                    "must_include_terms": ["PLC"],
                    "avoid_or_deemphasize_terms": [],
                    "forbidden_claims_or_phrases": [],
                    "skills_allowlist": [],
                    "additional_instructions": "Keep it concise.",
                },
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "OpenAI API key is missing. AI CV refinement is unavailable."
