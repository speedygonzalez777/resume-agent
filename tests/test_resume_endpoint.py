import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.routes_resume import (
    ResumeDraftListItem,
    ResumeDraftRefinementResponse,
    ResumeGenerationResponse,
    StoredResumeDraftResponse,
)
from app.main import app
from app.db import init_db, reset_database_state
from app.models.analysis import MatchAnalysisRequest
from app.models.candidate import CandidateProfile
from app.models.resume import (
    ResumeFallbackReason,
    ResumeGenerationMode,
    ResumeMatchResultSource,
    ResumeProjectEntry,
)
from app.models.typst import (
    TYPST_LIMIT_CONFIG,
    TypstDraftVariant,
    TypstEducationEntry,
    TypstExperienceEntry,
    TypstPayload,
    TypstPdfLayoutMetrics,
    TypstPrepareResponse,
    TypstProfilePayload,
    TypstProjectEntry,
    TypstQualityAnalysis,
    TypstQualityAnalysisResponse,
    TypstFitToPagePlan,
    TypstFitToPagePatch,
    TypstFitToPageRequest,
    TypstRenderOptions,
    TypstRenderResponse,
)
from app.prompts.resume_typst_fitter_prompt import RESUME_TYPST_FITTER_INSTRUCTIONS
from app.services.match_service import analyze_match_basic
from app.services.openai_resume_typst_fitter_service import (
    ResumeTypstFitterOpenAIError,
    ResumeTypstFitterResult,
)
from app.services.openai_typst_quality_analysis_service import (
    TYPST_QUALITY_ANALYSIS_INSTRUCTIONS,
    TypstQualityAnalysisOpenAIError,
)
from app.services.openai_typst_fit_to_page_service import TypstFitToPagePatchResult
from app.services.openai_typst_fit_to_page_service import TYPST_FIT_TO_PAGE_INSTRUCTIONS
from app.services.persistence_service import (
    save_candidate_profile,
    save_resume_draft,
    update_resume_draft_refinement,
)
from app.services.resume_generation_service import generate_resume_artifacts
from app.services import resume_typst_service

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


def _build_fake_typst_payload_from_fitter_input(fitter_input: dict[str, object]) -> TypstPayload:
    render_options = fitter_input["render_options"]
    draft = fitter_input["draft_primary_source"]
    profile_fallback = fitter_input.get("profile_fallback_source", {})

    header = draft["header"]
    header_fallback = profile_fallback.get("header", {})

    experience_entries = [
        *(draft["selected_experience_entries"] or []),
        *(profile_fallback.get("experience_entries", []) or []),
    ]
    project_entries = [
        *(draft["selected_project_entries"] or []),
        *(profile_fallback.get("project_entries", []) or []),
    ]

    draft_skill_entries = [
        *(draft.get("selected_skills") or []),
        *(draft.get("selected_soft_skill_entries") or []),
    ]
    if profile_fallback.get("skill_entries") and (
        len(draft_skill_entries) < 3
        or all(":" not in value for value in draft_skill_entries)
    ):
        skill_entries = profile_fallback.get("skill_entries", [])
    else:
        skill_entries = draft_skill_entries

    draft_language_certificate_entries = [
        *(draft.get("selected_language_entries") or []),
        *(draft.get("selected_certificate_entries") or []),
    ]
    language_certificate_entries = [
        *draft_language_certificate_entries,
        *(profile_fallback.get("language_certificate_entries", []) or []),
    ]

    education_entries = profile_fallback.get("education_entries") or [
        {
            "institution": value,
            "degree": "",
            "date": "",
            "thesis": None,
        }
        for value in draft.get("selected_education_entries", [])[:2]
    ]

    return TypstPayload(
        template_name="cv_one_page",
        language=render_options["language"],
        include_photo=render_options["include_photo"],
        consent_mode=render_options["consent_mode"],
        custom_consent_text=render_options.get("custom_consent_text"),
        photo_asset_id=render_options.get("photo_asset_id"),
        profile=TypstProfilePayload(
            full_name=header["full_name"],
            email=header["email"],
            phone=header["phone"],
            linkedin=header_fallback.get("linkedin"),
            github=header_fallback.get("github"),
        ),
        summary_text=(draft.get("professional_summary") or draft.get("fit_summary") or "Summary"),
        education_entries=[
            TypstEducationEntry.model_validate(entry)
            for entry in education_entries
        ],
        experience_entries=[
            TypstExperienceEntry(
                company=entry["company_name"],
                role=entry["position_title"],
                date=entry["date_range"],
                bullets=(entry.get("bullet_points") or [])[:2],
            )
            if "company_name" in entry
            else TypstExperienceEntry.model_validate(entry)
            for entry in experience_entries[:2]
        ],
        project_entries=[
            TypstProjectEntry(
                name=entry["project_name"],
                description=" ".join((entry.get("bullet_points") or [])[:2]).strip()
                or (entry.get("relevance_note") or ""),
            )
            if "project_name" in entry
            else TypstProjectEntry.model_validate(entry)
            for entry in project_entries[:2]
        ],
        skill_entries=skill_entries[:3],
        language_certificate_entries=language_certificate_entries[:6],
    )


def _install_fake_typst_fitter(monkeypatch, *, result_factory=None):
    calls: list[dict[str, object]] = []

    def fake_generate_typst_payload_with_openai(
        fitter_input: dict[str, object],
        *,
        retry_feedback: str | None = None,
    ) -> ResumeTypstFitterResult:
        calls.append(
            {
                "fitter_input": fitter_input,
                "retry_feedback": retry_feedback,
            }
        )

        if result_factory is None:
            payload = _build_fake_typst_payload_from_fitter_input(fitter_input)
            return ResumeTypstFitterResult(
                typst_payload=payload,
                model_name="gpt-5.4-mini",
            )

        payload_or_error = result_factory(
            fitter_input,
            retry_feedback=retry_feedback,
            call_index=len(calls),
        )
        if isinstance(payload_or_error, Exception):
            raise payload_or_error

        return ResumeTypstFitterResult(
            typst_payload=payload_or_error,
            model_name="gpt-5.4-mini",
        )

    monkeypatch.setattr(
        "app.services.resume_typst_service.generate_typst_payload_with_openai",
        fake_generate_typst_payload_with_openai,
    )
    return calls


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


def test_resume_typst_prepare_resolves_stored_base_draft_and_returns_fitted_payload(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["thesis_title"] = "Adaptive PLC control for distributed automation cells"

    request = MatchAnalysisRequest.model_validate(payload)
    calls = _install_fake_typst_fitter(monkeypatch)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        stored_draft = save_resume_draft(
            candidate_profile_id=stored_profile["id"],
            job_posting_id=22,
            match_result_id=33,
            target_job_title=artifacts.resume_draft.target_job_title,
            target_company_name=artifacts.resume_draft.target_company_name,
            generation_mode=artifacts.generation_mode.value,
            base_resume_artifacts=artifacts.model_dump(
                mode="json",
                exclude={"resume_draft_record_id", "resume_draft_saved_at", "persistence_warning"},
            ),
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "draft_id": stored_draft["id"],
                "draft_variant": "base",
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200

    parsed_response = TypstPrepareResponse.model_validate(response.json())

    assert parsed_response.prepare_debug is not None
    assert calls[0]["fitter_input"]["limit_config"]["summary"]["target_chars"] == 370
    assert calls[0]["fitter_input"]["limit_config"]["summary"]["hard_chars"] == 390
    primary_summary_source = calls[0]["fitter_input"]["primary_summary_source"]
    assert primary_summary_source["user_authored_profile_summary"] == request.candidate_profile.professional_summary_base
    assert primary_summary_source["user_authored_profile_summary_available"] is True
    assert primary_summary_source["existing_resume_draft_summary"] == artifacts.resume_draft.professional_summary
    assert "rewrite_from_keywords" in primary_summary_source["forbidden_summary_operations"]
    assert "rewrite_from_projects" in primary_summary_source["forbidden_summary_operations"]
    assert "rewrite_from_technologies" in primary_summary_source["forbidden_summary_operations"]
    assert parsed_response.prepare_debug.source_mode == "draft_id"
    assert parsed_response.prepare_debug.draft_variant == "base"
    assert parsed_response.prepare_debug.stored_resume_draft_id == stored_draft["id"]
    assert parsed_response.prepare_debug.resolved_candidate_profile_id == stored_profile["id"]
    assert parsed_response.prepare_debug.candidate_profile_available is True
    assert parsed_response.prepare_debug.stub_mode is False
    assert parsed_response.prepare_debug.fitter_model == "gpt-5.4-mini"
    assert parsed_response.prepare_debug.translation_applied is False
    assert parsed_response.typst_payload.profile.linkedin is not None
    assert parsed_response.typst_payload.profile.github is not None
    assert len(parsed_response.typst_payload.experience_entries) <= 2
    assert all(len(item.bullets) <= 2 for item in parsed_response.typst_payload.experience_entries)
    assert parsed_response.typst_payload.education_entries
    assert all(entry.thesis is None for entry in parsed_response.typst_payload.education_entries)
    assert "education" in parsed_response.prepare_debug.profile_assisted_sections


def test_resume_typst_prepare_preserves_user_authored_profile_summary_source() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    synthetic_summary = (
        "Alex Example is an operations-focused candidate with experience improving service workflows, "
        "coordinating small teams and keeping customer-facing processes organized."
    )
    payload["candidate_profile"]["personal_info"]["full_name"] = "Alex Example"
    payload["candidate_profile"]["professional_summary_base"] = synthetic_summary
    request = MatchAnalysisRequest.model_validate(payload)
    candidate_profile = CandidateProfile.model_validate(payload["candidate_profile"])
    artifacts = ResumeGenerationResponse.model_validate(
        generate_resume_artifacts(
            request.candidate_profile,
            request.job_posting,
            analyze_match_basic(request),
        )
    )
    resolved_source = resume_typst_service.ResolvedTypstPrepareSource(
        resume_draft=artifacts.resume_draft,
        candidate_profile=candidate_profile,
        source_mode="inline_draft",
        draft_variant=None,
        stored_resume_draft_id=None,
        candidate_profile_id=1,
        warnings=[],
    )
    options = TypstRenderOptions(
        language="en",
        include_photo=False,
        consent_mode="default",
        custom_consent_text=None,
        photo_asset_id=None,
    )

    fitter_input_bundle = resume_typst_service._build_typst_fitter_input_bundle(  # noqa: SLF001
        resolved_source,
        options,
    )
    fake_payload = _build_fake_typst_payload_from_fitter_input(fitter_input_bundle.payload)

    primary_summary_source = fitter_input_bundle.payload["primary_summary_source"]
    source_priority_rules = fitter_input_bundle.payload["source_priority_rules"]
    joined_source_priority_rules = "\n".join(source_priority_rules)
    assert primary_summary_source["user_authored_profile_summary"] == synthetic_summary
    assert primary_summary_source["user_authored_profile_summary_available"] is True
    assert primary_summary_source["existing_resume_draft_summary"] == synthetic_summary
    assert fake_payload.summary_text == synthetic_summary
    assert "ResumeDraft is the primary source for most CV sections" in joined_source_priority_rules
    assert "summary_text has its own source hierarchy" in joined_source_priority_rules
    assert "user_authored_profile_summary outranks ResumeDraft.professional_summary" in joined_source_priority_rules
    assert "semantic source of truth for summary meaning, professional direction and key facts" in joined_source_priority_rules
    assert "not text to copy word for word" in joined_source_priority_rules
    assert "do not copy it verbatim if it would exceed limit_config.summary.hard_chars" in joined_source_priority_rules
    assert "currently 370" in joined_source_priority_rules
    assert "currently 390" in joined_source_priority_rules
    assert "Hard limit compliance has priority over exact wording" in joined_source_priority_rules
    assert "not primary sources for summary_text" in joined_source_priority_rules


def test_resume_typst_summary_limit_config_uses_relaxed_target_with_same_hard_limit() -> None:
    assert TYPST_LIMIT_CONFIG["summary"]["target_chars"] == 370
    assert TYPST_LIMIT_CONFIG["summary"]["hard_chars"] == 390


def test_resume_typst_prepare_does_not_offer_content_fallbacks_when_draft_already_has_usable_content(
    monkeypatch,
) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        complete_resume_draft = artifacts.resume_draft.model_dump(mode="json")
        complete_resume_draft["selected_experience_entries"] = [
            {
                "source_experience_id": "exp_manual_1",
                "company_name": "Orion Systems",
                "position_title": "Automation Engineer",
                "date_range": "Oct 2025 - Mar 2026",
                "bullet_points": [
                    "Designed IoT-based building automation systems for educational institutions."
                ],
                "highlighted_keywords": ["automation"],
                "relevance_note": "Directly relevant automation experience.",
                "source_highlights": ["Designed IoT-based building automation systems"],
            },
            {
                "source_experience_id": "exp_manual_2",
                "company_name": "Northbridge Automation",
                "position_title": "Electrical Engineering Intern",
                "date_range": "Jun 2025 - Aug 2025",
                "bullet_points": [
                    "Assembled control cabinets based on technical documentation."
                ],
                "highlighted_keywords": ["documentation"],
                "relevance_note": "Relevant technical documentation experience.",
                "source_highlights": ["Assembled control cabinets"],
            },
        ]
        complete_resume_draft["selected_project_entries"] = [
            {
                "source_project_id": "project_manual_1",
                "project_name": "Resume Agent Project",
                "role": "Developer",
                "link": None,
                "bullet_points": [
                    "Built a local MVP for truthful-first CV tailoring with FastAPI and React."
                ],
                "highlighted_keywords": ["FastAPI"],
                "relevance_note": "Directly relevant engineering project.",
                "source_highlights": ["Built a local MVP"],
            }
        ]
        complete_resume_draft["selected_project_entries"].append(
            {
                "source_project_id": "project_manual_2",
                "project_name": "Robotics Demo Platform",
                "role": "Embedded Developer",
                "link": None,
                "bullet_points": [
                    "Implemented embedded control logic for a walking robot prototype."
                ],
                "highlighted_keywords": ["embedded"],
                "relevance_note": "Relevant robotics project.",
                "source_highlights": ["Implemented embedded control logic"],
            }
        )
        complete_resume_draft["selected_skills"] = [
            "Software & AI: Python, FastAPI",
            "Automation & Engineering: PLC programming, electrical design",
            "Soft skills: teamwork, analytical problem-solving",
        ]
        complete_resume_draft["selected_soft_skill_entries"] = []
        complete_resume_draft["selected_language_entries"] = [
            "English - C1",
            "German - A2/B1",
            "Polish - Native",
        ]
        complete_resume_draft["selected_certificate_entries"] = [
            "Example English Certificate (B2)",
            "Example Elec Cert",
            "Example Safety Training",
        ]
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": complete_resume_draft,
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    profile_fallback_source = captured_inputs[0]["profile_fallback_source"]
    assert "experience_entries" not in profile_fallback_source
    assert "project_entries" not in profile_fallback_source
    assert "skill_entries" not in profile_fallback_source
    assert "language_certificate_entries" not in profile_fallback_source
    assert "skill_source_material" in profile_fallback_source


def test_resume_typst_prepare_rejects_missing_refined_variant_for_stored_draft() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        stored_draft = save_resume_draft(
            candidate_profile_id=stored_profile["id"],
            job_posting_id=22,
            match_result_id=33,
            target_job_title=artifacts.resume_draft.target_job_title,
            target_company_name=artifacts.resume_draft.target_company_name,
            generation_mode=artifacts.generation_mode.value,
            base_resume_artifacts=artifacts.model_dump(
                mode="json",
                exclude={"resume_draft_record_id", "resume_draft_saved_at", "persistence_warning"},
            ),
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "draft_id": stored_draft["id"],
                "draft_variant": "refined",
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_code"] == "typst_prepare_source_error"
    assert detail["stage"] == "prepare"
    assert detail["message"] == "Requested refined draft variant is not available for this stored draft."


def test_resume_typst_prepare_accepts_inline_final_draft_with_profile_reference(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["thesis_title"] = "Human-aware automation system verification"

    request = MatchAnalysisRequest.model_validate(payload)
    _install_fake_typst_fitter(monkeypatch)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": artifacts.resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "pl",
                    "include_photo": True,
                    "consent_mode": "custom",
                    "custom_consent_text": "Wyrazam zgode na przetwarzanie moich danych osobowych.",
                    "photo_asset_id": "photo_stub_001",
                },
            },
        )

    assert response.status_code == 200

    parsed_response = TypstPrepareResponse.model_validate(response.json())

    assert parsed_response.prepare_debug is not None
    assert parsed_response.prepare_debug.source_mode == "inline_draft"
    assert parsed_response.prepare_debug.draft_variant is None
    assert parsed_response.prepare_debug.stored_resume_draft_id is None
    assert parsed_response.prepare_debug.resolved_candidate_profile_id == stored_profile["id"]
    assert parsed_response.prepare_debug.translation_applied is True
    assert parsed_response.typst_payload.language == "pl"
    assert parsed_response.typst_payload.include_photo is True
    assert parsed_response.typst_payload.consent_mode == "custom"
    assert parsed_response.typst_payload.photo_asset_id == "photo_stub_001"
    assert len(parsed_response.typst_payload.skill_entries) <= 3
    assert len(parsed_response.typst_payload.language_certificate_entries) <= 6


def test_resume_typst_prepare_accepts_full_profile_links_without_shortening(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    linkedin_url = "https://www.linkedin.com/in/alex-example"
    github_url = "https://github.com/alex-example"
    payload["candidate_profile"]["personal_info"]["linkedin_url"] = linkedin_url
    payload["candidate_profile"]["personal_info"]["github_url"] = github_url

    request = MatchAnalysisRequest.model_validate(payload)
    _install_fake_typst_fitter(monkeypatch)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": artifacts.resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    parsed_response = TypstPrepareResponse.model_validate(response.json())
    assert parsed_response.typst_payload.profile.linkedin == linkedin_url
    assert parsed_response.typst_payload.profile.github == github_url
    assert parsed_response.prepare_debug is not None
    assert parsed_response.prepare_debug.char_metrics["profile"]["linkedin"]["hard_chars"] == 90
    assert parsed_response.prepare_debug.char_metrics["profile"]["github"]["hard_chars"] == 70
    assert parsed_response.prepare_debug.char_metrics["profile"]["linkedin"]["exceeds_hard"] is False
    assert parsed_response.prepare_debug.char_metrics["profile"]["github"]["exceeds_hard"] is False


def test_resume_typst_prepare_rejects_conflicting_source_modes() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/prepare",
            json={
                "draft_id": 1,
                "draft_variant": "base",
                "final_resume_draft": generate_resume_artifacts(
                    request.candidate_profile,
                    request.job_posting,
                    analyze_match_basic(request),
                )["resume_draft"].model_dump(mode="json"),
                "candidate_profile_id": 1,
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 422
    assert "Provide exactly one source" in response.text


def _build_typst_render_request(
    *,
    profile_overrides: dict[str, object] | None = None,
    payload_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    typst_payload: dict[str, object] = {
        "template_name": "cv_one_page",
        "language": "en",
        "include_photo": False,
        "consent_mode": "default",
        "custom_consent_text": None,
        "photo_asset_id": None,
        "profile": {
            "full_name": "Jan Kowalski",
            "email": "jan@example.com",
            "phone": "+48 555 111 222",
            "linkedin": "linkedin.com/in/jankowalski",
            "github": "github.com/jankowalski",
        },
        "summary_text": 'Automation engineer focused on PLC systems, Python tools and "safe" delivery.',
        "education_entries": [
            {
                "institution": "Example University of Technology",
                "degree": "BSc Automation and Robotics",
                "date": "2021 - 2025",
                "thesis": "Robotics demo platform with embedded C++ control",
            }
        ],
        "experience_entries": [
            {
                "company": "Orion Systems",
                "role": "Automation Engineer",
                "date": "2025 - 2026",
                "bullets": [
                    "Built PLC motion-control functions for industrial cells.",
                    "Integrated Python tooling for repeatable engineering checks.",
                ],
            }
        ],
        "project_entries": [
            {
                "name": "Resume Tailoring Agent",
                "description": "FastAPI and SQLite workflow for tailored CV drafts.",
            }
        ],
        "skill_entries": [
            "Python, FastAPI, SQLite",
            "PLC, CODESYS, Structured Text",
        ],
        "language_certificate_entries": [
            "English - C1",
            "Example Elec Cert",
        ],
    }
    if profile_overrides:
        profile = dict(typst_payload["profile"])
        profile.update(profile_overrides)
        typst_payload["profile"] = profile
    if payload_overrides:
        typst_payload.update(payload_overrides)
    return {"typst_payload": typst_payload}


def _install_fake_typst_runtime(
    monkeypatch,
    tmp_path,
    *,
    returncode: int = 0,
    stderr: str = "",
):
    artifacts_dir = tmp_path / "artifacts"
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(resume_typst_service, "_ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(resume_typst_service, "_resolve_typst_binary", lambda: "/usr/bin/typst")
    monkeypatch.setattr(
        resume_typst_service,
        "analyze_typst_pdf_layout",
        lambda _pdf_path: _build_test_layout_metrics(),
    )

    def fake_subprocess_run(command, *, cwd, capture_output, text, check, timeout):
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "check": check,
                "timeout": timeout,
            }
        )
        if returncode == 0:
            Path(command[-1]).write_bytes(b"%PDF-1.7\n% fake test pdf\n")
        return subprocess.CompletedProcess(command, returncode, stdout="", stderr=stderr)

    monkeypatch.setattr(resume_typst_service.subprocess, "run", fake_subprocess_run)
    return artifacts_dir, calls


def _build_test_layout_metrics(**overrides) -> TypstPdfLayoutMetrics:
    payload = {
        "page_count": 1,
        "is_single_page": True,
        "page_width_pt": 595.28,
        "page_height_pt": 841.89,
        "main_content_bottom_y": 650.0,
        "footer_top_y": 770.0,
        "free_space_before_footer_pt": 120.0,
        "estimated_fill_ratio": 0.844,
        "underfilled": False,
        "overfilled": False,
        "footer_overlap_risk": False,
        "footer_detected": True,
        "analysis_warnings": [],
    }
    payload.update(overrides)
    return TypstPdfLayoutMetrics.model_validate(payload)


def _build_test_quality_analysis(**overrides) -> TypstQualityAnalysis:
    payload = {
        "overall_status": "underfilled",
        "summary": "The document can use more factual detail in existing sections.",
        "recommended_actions": ["Expand experience bullets first."],
        "sections_to_expand": ["experience_entries", "project_entries"],
        "sections_to_shorten": [],
        "risk_notes": ["Do not add facts outside the current payload."],
        "should_offer_fit_to_page": True,
        "fit_to_page_plan": {
            "action": "expand",
            "priority_sections": ["experience_entries", "project_entries"],
            "avoid_sections": ["profile", "education"],
            "intensity": "small",
            "reason": "Layout metrics show unused first-page space.",
        },
        "confidence": 0.8,
    }
    payload.update(overrides)
    return TypstQualityAnalysis.model_validate(payload)


def _build_typst_fit_to_page_request(
    *,
    payload_overrides: dict[str, object] | None = None,
    force: bool = False,
) -> dict[str, object]:
    return {
        "typst_payload": _build_typst_render_request(payload_overrides=payload_overrides)["typst_payload"],
        "layout_metrics": _build_test_layout_metrics(underfilled=True).model_dump(mode="json"),
        "quality_analysis": _build_test_quality_analysis().model_dump(mode="json"),
        "char_metrics": {"summary_text": {"char_count": 70, "target_chars": 370, "hard_chars": 390}},
        "limit_config": {"summary": {"target_chars": 370, "hard_chars": 390}},
        "render_warnings": [],
        "force": force,
    }


def _build_two_project_fit_to_page_request() -> dict[str, object]:
    return _build_typst_fit_to_page_request(
        payload_overrides={
            "project_entries": [
                {
                    "name": "Resume Tailoring Agent",
                    "description": "FastAPI and SQLite workflow for tailored CV drafts.",
                },
                {
                    "name": "Robotics Demo Platform",
                    "description": "C++ control software for a six-legged walking robot.",
                },
            ],
        }
    )


def _build_source_evidence_test_objects():
    payload = json.loads(Path("data/match_analysis_test.json").read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)
    candidate_profile = CandidateProfile.model_validate(payload["candidate_profile"])
    artifacts = ResumeGenerationResponse.model_validate(
        generate_resume_artifacts(
            request.candidate_profile,
            request.job_posting,
            analyze_match_basic(request),
        )
    )
    resume_draft = artifacts.resume_draft
    if not resume_draft.selected_project_entries:
        profile_project = candidate_profile.project_entries[0]
        resume_draft = resume_draft.model_copy(
            update={
                "selected_project_entries": [
                    ResumeProjectEntry(
                        source_project_id=profile_project.id,
                        project_name=profile_project.project_name,
                        role=profile_project.role,
                        link=str(profile_project.link) if profile_project.link is not None else None,
                        bullet_points=[profile_project.description],
                        highlighted_keywords=profile_project.keywords,
                        relevance_note="Synthetic project selected for source evidence tests.",
                        source_highlights=[profile_project.description],
                    )
                ]
            }
        )
    assert resume_draft.selected_experience_entries
    assert resume_draft.selected_project_entries

    typst_payload = TypstPayload(
        template_name="cv_one_page",
        language="en",
        include_photo=False,
        consent_mode="default",
        custom_consent_text=None,
        photo_asset_id=None,
        profile=TypstProfilePayload(
            full_name=resume_draft.header.full_name,
            email=resume_draft.header.email,
            phone=resume_draft.header.phone,
            linkedin=None,
            github=None,
        ),
        summary_text=resume_draft.professional_summary or resume_draft.fit_summary or "Summary",
        education_entries=[],
        experience_entries=[
            TypstExperienceEntry(
                company=entry.company_name,
                role=entry.position_title,
                date=entry.date_range,
                bullets=entry.bullet_points[:2] or ["Supported source-backed work."],
            )
            for entry in resume_draft.selected_experience_entries[:2]
        ],
        project_entries=[
            TypstProjectEntry(
                name=entry.project_name,
                description=" ".join(entry.bullet_points[:2]) or entry.relevance_note or "Project description.",
            )
            for entry in resume_draft.selected_project_entries[:2]
        ],
        skill_entries=[],
        language_certificate_entries=[],
    )
    resolved_source = resume_typst_service.ResolvedTypstPrepareSource(
        resume_draft=resume_draft,
        candidate_profile=candidate_profile,
        source_mode="draft_id",
        draft_variant=TypstDraftVariant.BASE,
        stored_resume_draft_id=1,
        candidate_profile_id=1,
        warnings=[],
    )
    return payload, artifacts, typst_payload, resolved_source


def test_typst_source_evidence_pack_maps_payload_entries_to_source_entries() -> None:
    _, _, typst_payload, resolved_source = _build_source_evidence_test_objects()

    pack = resume_typst_service.build_typst_source_evidence_pack(typst_payload, resolved_source)

    assert len(pack.experience_items) == min(2, len(typst_payload.experience_entries))
    assert len(pack.project_items) == min(2, len(typst_payload.project_entries))
    experience_item = pack.experience_items[0]
    project_item = pack.project_items[0]
    assert experience_item.source_id == "exp_001"
    assert experience_item.match_confidence == "high"
    assert experience_item.responsibilities
    assert len(experience_item.responsibilities) <= 3
    assert len(experience_item.technologies) <= 8
    assert project_item.source_id == "proj_001"
    assert project_item.match_confidence == "high"
    assert project_item.outcomes
    assert pack.summary_context is not None
    assert pack.summary_context.match_confidence == "high"
    assert any("User-authored profile summary" in item for item in pack.summary_context.source_highlights)
    assert any("semantic source of truth for summary_text" in item for item in pack.summary_context.constraints)
    assert any("job keywords, projects, technologies" in item for item in pack.summary_context.constraints)
    assert pack.concept_grounding


def test_typst_source_evidence_pack_falls_back_to_project_name_mapping() -> None:
    _, _, typst_payload, resolved_source = _build_source_evidence_test_objects()
    project_entry = resolved_source.resume_draft.selected_project_entries[0].model_copy(
        update={"source_project_id": ""}
    )
    resume_draft = resolved_source.resume_draft.model_copy(
        update={"selected_project_entries": [project_entry]}
    )
    resolved_without_project_id = resume_typst_service.ResolvedTypstPrepareSource(
        resume_draft=resume_draft,
        candidate_profile=resolved_source.candidate_profile,
        source_mode=resolved_source.source_mode,
        draft_variant=resolved_source.draft_variant,
        stored_resume_draft_id=resolved_source.stored_resume_draft_id,
        candidate_profile_id=resolved_source.candidate_profile_id,
        warnings=[],
    )

    pack = resume_typst_service.build_typst_source_evidence_pack(typst_payload, resolved_without_project_id)

    assert pack.project_items[0].source_id == "proj_001"
    assert pack.project_items[0].match_confidence == "high"
    assert any("project-name fallback" in warning for warning in pack.project_items[0].warnings)


def test_typst_source_evidence_pack_low_confidence_mapping_warns() -> None:
    _, _, typst_payload, resolved_source = _build_source_evidence_test_objects()
    mismatched_payload = typst_payload.model_copy(
        update={
            "experience_entries": [
                TypstExperienceEntry(
                    company="Unknown Example Co",
                    role="Unmapped Role",
                    date="2020",
                    bullets=["Existing bullet kept as the only safe context."],
                )
            ],
            "project_entries": [
                TypstProjectEntry(
                    name="Unmapped Example Project",
                    description="Existing project description.",
                )
            ],
        }
    )

    pack = resume_typst_service.build_typst_source_evidence_pack(mismatched_payload, resolved_source)

    assert pack.experience_items[0].match_confidence == "low"
    assert pack.project_items[0].match_confidence == "low"
    assert pack.mapping_warnings
    assert "Low-confidence mapping" in pack.experience_items[0].constraints[-1]


def test_resume_typst_fit_to_page_receives_source_evidence_pack(monkeypatch) -> None:
    payload, artifacts, typst_payload, resolved_source = _build_source_evidence_test_objects()
    patch = TypstFitToPagePatch(
        summary_text=None,
        experience_bullet_updates=[],
        project_description_updates=[],
        rationale="No safe changes needed for this evidence capture test.",
        warnings=[],
    )
    captured_requests = []

    def fake_fit_service(request, *, retry_feedback=None):
        assert retry_feedback is None
        captured_requests.append(request)
        return TypstFitToPagePatchResult(patch=patch, model_name="fake-fit-model")

    monkeypatch.setattr(
        resume_typst_service,
        "generate_typst_fit_to_page_patch_with_openai",
        fake_fit_service,
    )

    init_db()
    stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
    stored_draft = save_resume_draft(
        candidate_profile_id=stored_profile["id"],
        job_posting_id=22,
        match_result_id=33,
        target_job_title=resolved_source.resume_draft.target_job_title,
        target_company_name=resolved_source.resume_draft.target_company_name,
        generation_mode=artifacts.generation_mode.value,
        base_resume_artifacts=artifacts.model_copy(
            update={"resume_draft": resolved_source.resume_draft}
        ).model_dump(
            mode="json",
            exclude={"resume_draft_record_id", "resume_draft_saved_at", "persistence_warning"},
        ),
    )
    request_body = _build_typst_fit_to_page_request()
    request_body["typst_payload"] = typst_payload.model_dump(mode="json")
    request_body["draft_id"] = stored_draft["id"]
    request_body["stored_resume_draft_id"] = stored_draft["id"]
    request_body["draft_variant"] = "base"
    response = resume_typst_service.fit_typst_payload_to_page(
        TypstFitToPageRequest.model_validate(request_body)
    )

    assert captured_requests
    source_evidence_pack = captured_requests[0].source_evidence_pack
    assert source_evidence_pack is not None
    assert source_evidence_pack.experience_items[0].source_id == "exp_001"
    assert source_evidence_pack.project_items[0].source_id == "proj_001"
    assert response.fit_debug.source_evidence_pack_used is True
    assert response.fit_debug.source_evidence_entry_counts["experience"] >= 1


def test_resume_typst_render_writes_typ_and_pdf_artifacts(monkeypatch, tmp_path) -> None:
    artifacts_dir, calls = _install_fake_typst_runtime(monkeypatch, tmp_path)

    def fail_if_openai_is_called(*args, **kwargs):
        raise AssertionError("render endpoint must not call the Typst fitter")

    monkeypatch.setattr(
        resume_typst_service,
        "generate_typst_payload_with_openai",
        fail_if_openai_is_called,
    )

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/render",
            json=_build_typst_render_request(),
        )

    assert response.status_code == 200

    parsed_response = TypstRenderResponse.model_validate(response.json())

    assert parsed_response.status == "completed"
    assert parsed_response.render_id is not None
    assert parsed_response.template_name == "cv_one_page"
    assert parsed_response.typ_source_artifact is not None
    assert parsed_response.pdf_artifact is not None
    assert parsed_response.layout_metrics is not None
    assert parsed_response.layout_metrics.page_count == 1
    assert parsed_response.layout_metrics.footer_detected is True
    assert parsed_response.typ_source_artifact.artifact_type == "typst_source"
    assert parsed_response.typ_source_artifact.media_type == "text/x-typst"
    assert parsed_response.pdf_artifact.artifact_type == "pdf"
    assert parsed_response.pdf_artifact.media_type == "application/pdf"
    assert parsed_response.typ_source_artifact.size_bytes is not None
    assert parsed_response.typ_source_artifact.size_bytes > 0
    assert parsed_response.pdf_artifact.size_bytes is not None
    assert parsed_response.pdf_artifact.size_bytes > 0

    typ_path = artifacts_dir / parsed_response.typ_source_artifact.filename
    pdf_path = artifacts_dir / parsed_response.pdf_artifact.filename
    assert typ_path.exists()
    assert pdf_path.exists()
    typ_source = typ_path.read_text(encoding="utf-8")
    assert "Generated Typst source from resume-agent" in typ_source
    assert "You may copy or edit this artifact manually if needed." in typ_source
    assert "Do not edit this artifact in place" not in typ_source
    assert 'font: ("Calibri", "Carlito", "Arial", "Liberation Sans", "DejaVu Sans")' in typ_source
    assert "Calibri" in typ_source
    assert "Carlito" in typ_source
    assert "Arial" in typ_source
    assert "Liberation Sans" in typ_source
    assert "DejaVu Sans" in typ_source
    assert 'margin: (top: 0.68cm, bottom: 0.72cm, left: 1.05cm, right: 1.05cm)' in typ_source
    assert "size: 10.6pt" in typ_source
    assert "#set par(justify: false, leading: 0.68em)" in typ_source
    assert "#set list(tight: true)" in typ_source
    assert "#let header_height = 3.45cm" in typ_source
    assert '#render-text("JAN KOWALSKI")' in typ_source
    assert '#render-text("Jan Kowalski")' not in typ_source
    assert calls == [
        {
            "command": ["/usr/bin/typst", "compile", str(typ_path), str(pdf_path)],
            "cwd": str(resume_typst_service._PROJECT_ROOT),  # noqa: SLF001
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": resume_typst_service._TYPST_RENDER_TIMEOUT_SECONDS,  # noqa: SLF001
        }
    ]


def test_resume_typst_render_keeps_artifacts_when_layout_analysis_fails(monkeypatch, tmp_path) -> None:
    artifacts_dir, _calls = _install_fake_typst_runtime(monkeypatch, tmp_path)

    def fail_layout_analysis(_pdf_path):
        raise resume_typst_service.TypstPdfLayoutAnalysisError("test analysis failure")

    monkeypatch.setattr(resume_typst_service, "analyze_typst_pdf_layout", fail_layout_analysis)

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/render",
            json=_build_typst_render_request(),
        )

    assert response.status_code == 200
    parsed_response = TypstRenderResponse.model_validate(response.json())
    assert parsed_response.typ_source_artifact is not None
    assert parsed_response.pdf_artifact is not None
    assert parsed_response.layout_metrics is None
    assert any("PDF layout analysis failed" in warning for warning in parsed_response.warnings)
    assert (artifacts_dir / parsed_response.typ_source_artifact.filename).exists()
    assert (artifacts_dir / parsed_response.pdf_artifact.filename).exists()


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("profile.jpg", "image/jpeg"),
        ("profile.png", "image/png"),
    ],
)
def test_resume_typst_upload_photo_accepts_jpg_and_png(
    monkeypatch,
    tmp_path,
    filename,
    content_type,
) -> None:
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setattr(resume_typst_service, "_ARTIFACTS_DIR", artifacts_dir)

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/photo-assets",
            files={"file": (filename, b"fake image bytes", content_type)},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["photo_asset_id"].startswith("photo_")
    assert payload["photo_asset_id"].endswith(Path(filename).suffix)
    assert "/" not in payload["photo_asset_id"]
    assert ".." not in payload["photo_asset_id"]
    assert (artifacts_dir / "uploads" / payload["photo_asset_id"]).exists()
    assert payload["photo_artifact"]["artifact_type"] == "photo_asset"


def test_resume_typst_upload_photo_rejects_unsupported_extension(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(resume_typst_service, "_ARTIFACTS_DIR", tmp_path / "artifacts")

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/photo-assets",
            files={"file": ("profile.gif", b"fake image bytes", "image/gif")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported photo file extension. Use .jpg, .jpeg or .png."


def test_resume_typst_upload_photo_ignores_path_traversal_filename(monkeypatch, tmp_path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setattr(resume_typst_service, "_ARTIFACTS_DIR", artifacts_dir)

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/photo-assets",
            files={"file": ("../../profile.jpg", b"fake image bytes", "image/jpeg")},
        )

    assert response.status_code == 200
    payload = response.json()
    stored_path = artifacts_dir / "uploads" / payload["photo_asset_id"]
    assert stored_path.exists()
    assert stored_path.resolve().is_relative_to((artifacts_dir / "uploads").resolve())


def test_resume_typst_render_requires_photo_asset_id_when_photo_enabled(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(resume_typst_service, "_ARTIFACTS_DIR", tmp_path / "artifacts")

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/render",
            json=_build_typst_render_request(
                payload_overrides={
                    "include_photo": True,
                    "photo_asset_id": None,
                },
            ),
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error_code"] == "typst_render_failed"
    assert detail["stage"] == "render"
    assert detail["message"] == "Photo rendering was requested, but photo_asset_id is missing."


def test_resume_typst_render_uses_uploaded_photo_asset(monkeypatch, tmp_path) -> None:
    artifacts_dir, _calls = _install_fake_typst_runtime(monkeypatch, tmp_path)

    with TestClient(app) as client:
        upload_response = client.post(
            "/resume/typst/photo-assets",
            files={"file": ("profile.jpg", b"fake image bytes", "image/jpeg")},
        )
        assert upload_response.status_code == 200
        photo_asset_id = upload_response.json()["photo_asset_id"]

        response = client.post(
            "/resume/typst/render",
            json=_build_typst_render_request(
                payload_overrides={
                    "include_photo": True,
                    "photo_asset_id": photo_asset_id,
                },
            ),
        )

    assert response.status_code == 200
    parsed_response = TypstRenderResponse.model_validate(response.json())
    assert parsed_response.typ_source_artifact is not None
    assert parsed_response.warnings == []

    typ_source = (artifacts_dir / parsed_response.typ_source_artifact.filename).read_text(
        encoding="utf-8"
    )
    assert f"uploads/{photo_asset_id}" in typ_source
    assert f'#image("uploads/{photo_asset_id}", width: 2.75cm, height: 3.45cm, fit: "cover")' in typ_source


def test_resume_typst_render_omits_empty_links_and_renders_thesis(monkeypatch, tmp_path) -> None:
    artifacts_dir, _calls = _install_fake_typst_runtime(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/render",
            json=_build_typst_render_request(
                profile_overrides={
                    "linkedin": None,
                    "github": None,
                },
            ),
        )

    assert response.status_code == 200
    parsed_response = TypstRenderResponse.model_validate(response.json())
    assert parsed_response.typ_source_artifact is not None
    typ_source = (artifacts_dir / parsed_response.typ_source_artifact.filename).read_text(
        encoding="utf-8"
    )

    assert "LinkedIn:" not in typ_source
    assert "GitHub:" not in typ_source
    assert "#image(" not in typ_source
    assert "Thesis:" in typ_source
    assert "Robotics demo platform with embedded C++ control" in typ_source


def test_resume_typst_artifact_download_returns_typ_and_pdf(monkeypatch, tmp_path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setattr(resume_typst_service, "_ARTIFACTS_DIR", artifacts_dir)
    artifacts_dir.mkdir()
    render_id = "20260424_131500_abcd"
    typ_path = artifacts_dir / f"render_{render_id}.typ"
    pdf_path = artifacts_dir / f"render_{render_id}.pdf"
    typ_path.write_text("#set text(size: 10pt)\n", encoding="utf-8")
    pdf_path.write_bytes(b"%PDF-1.7\n")

    with TestClient(app) as client:
        typ_response = client.get(f"/resume/typst/artifacts/{render_id}/typ")
        pdf_response = client.get(f"/resume/typst/artifacts/{render_id}/pdf")
        pdf_inline_response = client.get(
            f"/resume/typst/artifacts/{render_id}/pdf?disposition=inline"
        )
        pdf_attachment_response = client.get(
            f"/resume/typst/artifacts/{render_id}/pdf?disposition=attachment"
        )
        typ_inline_response = client.get(
            f"/resume/typst/artifacts/{render_id}/typ?disposition=inline"
        )

    assert typ_response.status_code == 200
    assert typ_response.text == "#set text(size: 10pt)\n"
    assert typ_response.headers["content-type"].startswith("text/plain")
    assert typ_response.headers["content-disposition"].startswith("attachment")
    assert pdf_response.status_code == 200
    assert pdf_response.content == b"%PDF-1.7\n"
    assert pdf_response.headers["content-type"].startswith("application/pdf")
    assert pdf_response.headers["content-disposition"].startswith("attachment")
    assert pdf_inline_response.status_code == 200
    assert pdf_inline_response.headers["content-disposition"].startswith("inline")
    assert pdf_attachment_response.status_code == 200
    assert pdf_attachment_response.headers["content-disposition"].startswith("attachment")
    assert typ_inline_response.status_code == 200
    assert typ_inline_response.headers["content-disposition"].startswith("attachment")


def test_resume_typst_artifact_download_rejects_invalid_disposition(monkeypatch, tmp_path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setattr(resume_typst_service, "_ARTIFACTS_DIR", artifacts_dir)
    artifacts_dir.mkdir()
    render_id = "20260424_131500_abcd"
    (artifacts_dir / f"render_{render_id}.pdf").write_bytes(b"%PDF-1.7\n")

    with TestClient(app) as client:
        response = client.get(f"/resume/typst/artifacts/{render_id}/pdf?disposition=preview")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid disposition. Use 'attachment' or 'inline'."


def test_resume_typst_artifact_download_returns_404_for_missing_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(resume_typst_service, "_ARTIFACTS_DIR", tmp_path / "artifacts")

    with TestClient(app) as client:
        response = client.get("/resume/typst/artifacts/20260424_131500_abcd/pdf")

    assert response.status_code == 404
    assert response.json()["detail"] == "Requested Typst artifact was not found."


def test_resume_typst_artifact_download_rejects_traversal_like_id(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(resume_typst_service, "_ARTIFACTS_DIR", tmp_path / "artifacts")

    with TestClient(app) as client:
        response = client.get("/resume/typst/artifacts/..%2F..%2Fetc%2Fpasswd/pdf")

    assert response.status_code in {400, 404}

    with pytest.raises(resume_typst_service.TypstArtifactError):
        resume_typst_service.resolve_typst_render_artifact(  # noqa: SLF001
            render_id="../../etc/passwd",
            artifact_type="pdf",
        )


@pytest.mark.parametrize(
    ("consent_mode", "custom_text", "expected_text", "unexpected_text"),
    [
        ("default", None, "I consent to the processing of my personal data", "Custom consent"),
        ("custom", "Custom consent with #hash and (parentheses).", "Custom consent", "I consent"),
        ("none", None, "#let consent_text = none", "I consent to the processing of my personal data"),
    ],
)
def test_resume_typst_render_respects_consent_modes(
    monkeypatch,
    tmp_path,
    consent_mode,
    custom_text,
    expected_text,
    unexpected_text,
) -> None:
    artifacts_dir, _calls = _install_fake_typst_runtime(monkeypatch, tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/render",
            json=_build_typst_render_request(
                payload_overrides={
                    "consent_mode": consent_mode,
                    "custom_consent_text": custom_text,
                },
            ),
        )

    assert response.status_code == 200
    parsed_response = TypstRenderResponse.model_validate(response.json())
    assert parsed_response.typ_source_artifact is not None
    typ_source = (artifacts_dir / parsed_response.typ_source_artifact.filename).read_text(
        encoding="utf-8"
    )

    assert expected_text in typ_source
    assert unexpected_text not in typ_source


def test_resume_typst_render_escapes_special_text_without_breaking_source(
    monkeypatch,
    tmp_path,
) -> None:
    artifacts_dir, _calls = _install_fake_typst_runtime(monkeypatch, tmp_path)
    special_summary = 'Zażółć gęślą jaźń "quote" apostrof\'s #hash (test) / path'

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/render",
            json=_build_typst_render_request(
                payload_overrides={
                    "summary_text": special_summary,
                },
            ),
        )

    assert response.status_code == 200
    parsed_response = TypstRenderResponse.model_validate(response.json())
    assert parsed_response.typ_source_artifact is not None
    typ_source = (artifacts_dir / parsed_response.typ_source_artifact.filename).read_text(
        encoding="utf-8"
    )

    assert "Zażółć gęślą jaźń" in typ_source
    assert '\\"quote\\"' in typ_source
    assert "apostrof's #hash (test) / path" in typ_source


def test_resume_typst_render_returns_controlled_error_when_typst_compile_fails(
    monkeypatch,
    tmp_path,
) -> None:
    artifacts_dir, _calls = _install_fake_typst_runtime(
        monkeypatch,
        tmp_path,
        returncode=1,
        stderr="error: failed to compile generated source",
    )

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/render",
            json=_build_typst_render_request(),
        )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["error_code"] == "typst_render_failed"
    assert detail["stage"] == "render"
    assert "Typst PDF compilation failed" in detail["message"]
    assert "failed to compile generated source" in detail["message"]
    assert list(artifacts_dir.glob("*.typ"))
    assert not list(artifacts_dir.glob("*.pdf"))


def test_resume_typst_render_returns_controlled_error_without_typst_binary(
    monkeypatch,
    tmp_path,
) -> None:
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setattr(resume_typst_service, "_ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(resume_typst_service, "_resolve_typst_binary", lambda: None)

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/render",
            json=_build_typst_render_request(),
        )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error_code"] == "typst_render_failed"
    assert detail["stage"] == "render"
    assert detail["message"] == (
        "Typst binary was not found. Set TYPST_BINARY_PATH or install typst in PATH."
    )
    assert list(artifacts_dir.glob("*.typ"))


def test_resume_typst_render_returns_structured_validation_error() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/render",
            json=_build_typst_render_request(
                payload_overrides={
                    "summary_text": "Y" * 500,
                },
            ),
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error_code"] == "typst_payload_validation_failed"
    assert detail["stage"] == "render"
    assert detail["message"] == "Typst payload validation failed."
    assert detail["retry_attempted"] is False
    assert detail["fitter_model"] is None
    assert "summary_text exceeds the hard character limit." in detail["validation_errors"]
    assert detail["char_metrics"]["summary_text"]["char_count"] == 500
    assert detail["section_counts"]["project_entries"] == 1


def test_resume_typst_render_still_rejects_absurdly_long_profile_links() -> None:
    long_linkedin = f"https://www.linkedin.com/in/{'x' * 90}"
    long_github = f"https://github.com/{'y' * 70}"

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/render",
            json=_build_typst_render_request(
                profile_overrides={
                    "linkedin": long_linkedin,
                    "github": long_github,
                },
            ),
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error_code"] == "typst_payload_validation_failed"
    assert detail["stage"] == "render"
    assert "profile.linkedin exceeds the hard character limit." in detail["validation_errors"]
    assert "profile.github exceeds the hard character limit." in detail["validation_errors"]
    assert detail["char_metrics"]["profile"]["linkedin"]["hard_chars"] == 90
    assert detail["char_metrics"]["profile"]["github"]["hard_chars"] == 70
    assert detail["char_metrics"]["profile"]["linkedin"]["exceeds_hard"] is True
    assert detail["char_metrics"]["profile"]["github"]["exceeds_hard"] is True


def test_resume_typst_analyze_render_returns_structured_quality_analysis(monkeypatch) -> None:
    captured_request = {}

    def fake_analyze(payload):
        captured_request["payload"] = payload
        return TypstQualityAnalysisResponse(
            analysis=TypstQualityAnalysis(
                overall_status="underfilled",
                summary="The document has useful content but leaves measurable space before the footer.",
                recommended_actions=["Expand experience bullets before changing layout."],
                sections_to_expand=["experience_entries", "project_entries"],
                sections_to_shorten=[],
                risk_notes=["Do not add facts outside the existing payload."],
                should_offer_fit_to_page=True,
                fit_to_page_plan=TypstFitToPagePlan(
                    action="expand",
                    priority_sections=["experience_entries", "project_entries"],
                    avoid_sections=["profile"],
                    intensity="small",
                    reason="The measured free space suggests a light content expansion.",
                ),
                confidence=0.82,
            ),
            model="fake-quality-model",
            warnings=[],
        )

    monkeypatch.setattr(
        "app.api.routes_resume.analyze_typst_render_quality_with_openai",
        fake_analyze,
    )

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/analyze-render",
            json={
                "typst_payload": _build_typst_render_request()["typst_payload"],
                "layout_metrics": _build_test_layout_metrics().model_dump(mode="json"),
                "char_metrics": {"summary_text": {"char_count": 120}},
                "limit_config": {"summary": {"target_chars": 370, "hard_chars": 390}},
                "render_warnings": [],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "fake-quality-model"
    assert payload["analysis"]["overall_status"] == "underfilled"
    assert payload["analysis"]["should_offer_fit_to_page"] is True
    assert payload["analysis"]["fit_to_page_plan"]["action"] == "expand"
    assert captured_request["payload"].layout_metrics.page_count == 1
    assert captured_request["payload"].typst_payload.profile.full_name == "Jan Kowalski"


def test_resume_typst_analyze_render_returns_structured_openai_error(monkeypatch) -> None:
    def fail_analyze(_payload):
        raise TypstQualityAnalysisOpenAIError(
            "OpenAI Typst quality analysis request failed.",
            status_code=502,
            details={"model": "fake-quality-model", "reason": "network disabled in test"},
        )

    monkeypatch.setattr(
        "app.api.routes_resume.analyze_typst_render_quality_with_openai",
        fail_analyze,
    )

    with TestClient(app) as client:
        response = client.post(
            "/resume/typst/analyze-render",
            json={
                "typst_payload": _build_typst_render_request()["typst_payload"],
                "layout_metrics": _build_test_layout_metrics().model_dump(mode="json"),
                "char_metrics": {},
                "limit_config": {},
                "render_warnings": [],
            },
        )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["error_code"] == "typst_quality_analysis_failed"
    assert detail["stage"] == "analyze-render"
    assert detail["message"] == "OpenAI Typst quality analysis request failed."
    assert detail["model"] == "fake-quality-model"
    assert detail["reason"] == "network disabled in test"


def test_resume_typst_fit_to_page_merges_allowed_experience_patch(monkeypatch) -> None:
    patch = TypstFitToPagePatch(
        summary_text=None,
        experience_bullet_updates=[
            {
                "entry_index": 0,
                "bullet_index": 0,
                "text": "Built PLC motion-control functions for industrial cells, using existing engineering documentation to support repeatable automation checks.",
                "reason": "Expand a short existing bullet with factual context already present in the payload.",
            },
            {
                "entry_index": 0,
                "bullet_index": 1,
                "text": "Integrated Python tooling into engineering checks, keeping the workflow repeatable for validation work already described in the payload.",
                "reason": "Expand a second short bullet without changing immutable fields.",
            }
        ],
        project_description_updates=[],
        rationale="Expand multiple short experience bullets while preserving immutable fields.",
        warnings=[],
    )

    monkeypatch.setattr(
        resume_typst_service,
        "generate_typst_fit_to_page_patch_with_openai",
        lambda _request: TypstFitToPagePatchResult(patch=patch, model_name="fake-fit-model"),
    )

    with TestClient(app) as client:
        response = client.post("/resume/typst/fit-to-page", json=_build_typst_fit_to_page_request())

    assert response.status_code == 200
    payload = response.json()
    original_payload = _build_typst_render_request()["typst_payload"]
    assert payload["fit_debug"]["model"] == "fake-fit-model"
    assert payload["fit_debug"]["retry_attempted"] is False
    assert payload["fit_debug"]["retry_feedback"] is None
    assert payload["fit_debug"]["initial_validation_errors"] == []
    assert payload["fit_debug"]["changed_sections"] == ["experience"]
    assert payload["fit_debug"]["changed_fields"] == [
        "experience_entries[0].bullets[0]",
        "experience_entries[0].bullets[1]",
    ]
    assert payload["typst_payload"]["experience_entries"][0]["bullets"][0].startswith(
        "Built PLC motion-control functions"
    )
    assert payload["typst_payload"]["experience_entries"][0]["bullets"][1].startswith(
        "Integrated Python tooling"
    )
    assert payload["typst_payload"]["profile"] == original_payload["profile"]
    assert payload["typst_payload"]["education_entries"] == original_payload["education_entries"]
    assert payload["typst_payload"]["experience_entries"][0]["company"] == "Orion Systems"
    assert payload["typst_payload"]["experience_entries"][0]["role"] == "Automation Engineer"
    assert payload["typst_payload"]["experience_entries"][0]["date"] == "2025 - 2026"
    assert len(payload["typst_payload"]["experience_entries"][0]["bullets"]) == len(
        original_payload["experience_entries"][0]["bullets"]
    )
    assert payload["typst_payload"]["project_entries"][0]["name"] == original_payload["project_entries"][0]["name"]
    assert payload["typst_payload"]["skill_entries"] == original_payload["skill_entries"]
    assert payload["typst_payload"]["language_certificate_entries"] == original_payload["language_certificate_entries"]


def test_resume_typst_fit_to_page_accepts_manual_force_override(monkeypatch) -> None:
    patch = TypstFitToPagePatch(
        summary_text=None,
        experience_bullet_updates=[
            {
                "entry_index": 0,
                "bullet_index": 0,
                "text": "Built PLC motion-control functions for industrial cells, using existing engineering documentation to support repeatable automation checks.",
                "reason": "Optional manual expansion requested by the user.",
            }
        ],
        project_description_updates=[],
        rationale="Conservative forced expansion.",
        warnings=[],
    )
    captured_force_values: list[bool] = []

    def fake_fit_service(request, *, retry_feedback=None):
        assert retry_feedback is None
        captured_force_values.append(request.force)
        return TypstFitToPagePatchResult(patch=patch, model_name="fake-fit-model")

    monkeypatch.setattr(
        resume_typst_service,
        "generate_typst_fit_to_page_patch_with_openai",
        fake_fit_service,
    )

    request_body = _build_typst_fit_to_page_request(force=True)
    request_body["quality_analysis"]["should_offer_fit_to_page"] = False
    request_body["layout_metrics"]["free_space_before_footer_pt"] = 109.0
    request_body["layout_metrics"]["estimated_fill_ratio"] = 0.86

    with TestClient(app) as client:
        response = client.post("/resume/typst/fit-to-page", json=request_body)

    assert response.status_code == 200
    assert captured_force_values == [True]
    payload = response.json()
    assert payload["fit_debug"]["changed_fields"] == ["experience_entries[0].bullets[0]"]


def test_resume_typst_fit_to_page_rejects_missing_experience_index(monkeypatch) -> None:
    patch = TypstFitToPagePatch(
        summary_text=None,
        experience_bullet_updates=[
            {
                "entry_index": 99,
                "bullet_index": 0,
                "text": "Expanded existing bullet text.",
                "reason": "Invalid index test.",
            }
        ],
        project_description_updates=[],
        rationale="Invalid index test.",
        warnings=[],
    )
    monkeypatch.setattr(
        resume_typst_service,
        "generate_typst_fit_to_page_patch_with_openai",
        lambda _request: TypstFitToPagePatchResult(patch=patch, model_name="fake-fit-model"),
    )

    with TestClient(app) as client:
        response = client.post("/resume/typst/fit-to-page", json=_build_typst_fit_to_page_request())

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error_code"] == "typst_fit_to_page_failed"
    assert detail["stage"] == "fit-to-page"
    assert "experience_entries[99] does not exist." in detail["validation_errors"]


def test_resume_typst_fit_to_page_retries_after_project_hard_limit_and_succeeds(monkeypatch) -> None:
    bad_patch = TypstFitToPagePatch(
        summary_text=None,
        experience_bullet_updates=[],
        project_description_updates=[
            {
                "entry_index": 1,
                "description": (
                    "Python-based kinematic analysis and gait trajectory generation for a six-legged walking robot, "
                    "including C++ control software notes and repeated implementation context that makes this project "
                    "description exceed the one-page Typst project hard limit during validation."
                ),
                "reason": "Intentionally too long first patch.",
            }
        ],
        rationale="Expand the project too aggressively.",
        warnings=[],
    )
    good_patch = TypstFitToPagePatch(
        summary_text=None,
        experience_bullet_updates=[
            {
                "entry_index": 0,
                "bullet_index": 0,
                "text": "Built PLC motion-control functions for industrial cells, using engineering documentation to support repeatable automation checks.",
                "reason": "Use experience bullet room after project validation failed.",
            }
        ],
        project_description_updates=[
            {
                "entry_index": 1,
                "description": "Python-based kinematic analysis and C++ control software for a six-legged walking robot.",
                "reason": "Shorten project description below the hard limit.",
            }
        ],
        rationale="Correct the project length and shift useful detail into experience.",
        warnings=[],
    )
    retry_feedbacks: list[str | None] = []

    def fake_fit_service(_request, *, retry_feedback=None):
        retry_feedbacks.append(retry_feedback)
        patch = bad_patch if retry_feedback is None else good_patch
        return TypstFitToPagePatchResult(patch=patch, model_name="fake-fit-model")

    monkeypatch.setattr(
        resume_typst_service,
        "generate_typst_fit_to_page_patch_with_openai",
        fake_fit_service,
    )

    with TestClient(app) as client:
        response = client.post("/resume/typst/fit-to-page", json=_build_two_project_fit_to_page_request())

    assert response.status_code == 200
    assert len(retry_feedbacks) == 2
    retry_feedback = retry_feedbacks[1]
    assert retry_feedback is not None
    assert "project_entries[1].description" in retry_feedback
    assert "Current length:" in retry_feedback
    assert "Target: 230 characters" in retry_feedback
    assert "Hard limit: 240 characters" in retry_feedback
    assert "Shorten project_entries[1].description" in retry_feedback
    assert "Do not expand project_entries[1] again" in retry_feedback
    assert "Prefer using available space in experience bullets" in retry_feedback

    payload = response.json()
    assert payload["fit_debug"]["retry_attempted"] is True
    assert payload["fit_debug"]["retry_feedback"] == retry_feedback
    assert payload["fit_debug"]["initial_validation_errors"] == [
        "project_entries[1] exceed the hard character limit."
    ]
    assert payload["fit_debug"]["changed_fields"] == [
        "experience_entries[0].bullets[0]",
        "project_entries[1].description",
    ]
    assert payload["fit_debug"]["char_metrics"]["project_entries"][1]["entry_total"]["exceeds_hard"] is False
    assert payload["typst_payload"]["project_entries"][1]["description"].startswith(
        "Python-based kinematic analysis"
    )


def test_resume_typst_fit_to_page_returns_structured_error_after_retry_failure(monkeypatch) -> None:
    patch = TypstFitToPagePatch(
        summary_text=None,
        experience_bullet_updates=[
            {
                "entry_index": 0,
                "bullet_index": 0,
                "text": "X" * 230,
                "reason": "Hard limit test.",
            }
        ],
        project_description_updates=[],
        rationale="Hard limit test.",
        warnings=[],
    )
    retry_feedbacks: list[str | None] = []

    def fake_fit_service(_request, *, retry_feedback=None):
        retry_feedbacks.append(retry_feedback)
        return TypstFitToPagePatchResult(patch=patch, model_name="fake-fit-model")

    monkeypatch.setattr(
        resume_typst_service,
        "generate_typst_fit_to_page_patch_with_openai",
        fake_fit_service,
    )

    with TestClient(app) as client:
        response = client.post("/resume/typst/fit-to-page", json=_build_typst_fit_to_page_request())

    assert response.status_code == 422
    assert len(retry_feedbacks) == 2
    assert retry_feedbacks[1] is not None
    detail = response.json()["detail"]
    assert detail["error_code"] == "typst_fit_to_page_failed"
    assert detail["message"] == "Typst fit-to-page failed after corrective retry."
    assert detail["stage"] == "fit-to-page"
    assert "experience_entries[0].bullets[0] exceed the hard character limit." in detail["validation_errors"]
    assert detail["retry_attempted"] is True
    assert "experience_entries[0].bullets[0]" in detail["retry_feedback"]
    assert detail["changed_fields"] == ["experience_entries[0].bullets[0]"]
    assert detail["char_metrics"]["experience_entries"][0]["bullets"][0]["hard_chars"] == 205


def test_resume_typst_fit_to_page_retries_after_summary_recent_task_style_violation(monkeypatch) -> None:
    bad_patch = TypstFitToPagePatch(
        summary_text=(
            "Recent work includes PLC programming, IoT building automation and Python tooling for engineering tasks."
        ),
        experience_bullet_updates=[],
        project_description_updates=[],
        rationale="Try to fill the page through summary.",
        warnings=[],
    )
    good_patch = TypstFitToPagePatch(
        summary_text=(
            "Automation and Robotics engineer combining industrial automation experience with "
            "Python-based software and AI-related engineering work."
        ),
        experience_bullet_updates=[],
        project_description_updates=[],
        rationale="Rewrite summary as a candidate profile instead of a recent-task list.",
        warnings=[],
    )
    retry_feedbacks: list[str | None] = []

    def fake_fit_service(_request, *, retry_feedback=None):
        retry_feedbacks.append(retry_feedback)
        patch = bad_patch if retry_feedback is None else good_patch
        return TypstFitToPagePatchResult(patch=patch, model_name="fake-fit-model")

    monkeypatch.setattr(
        resume_typst_service,
        "generate_typst_fit_to_page_patch_with_openai",
        fake_fit_service,
    )

    with TestClient(app) as client:
        response = client.post("/resume/typst/fit-to-page", json=_build_typst_fit_to_page_request())

    assert response.status_code == 200
    assert len(retry_feedbacks) == 2
    retry_feedback = retry_feedbacks[1]
    assert retry_feedback is not None
    assert "Recent work includes" in retry_feedback
    assert "candidate profile" in retry_feedback
    assert "Do not list recent tasks" in retry_feedback

    payload = response.json()
    assert payload["fit_debug"]["retry_attempted"] is True
    assert payload["fit_debug"]["initial_validation_errors"] == [
        (
            'summary_text uses a system-like or recent-task phrase: "Recent work includes". '
            "Rewrite summary_text as a fluent candidate profile paragraph. It should describe the "
            "candidate profile, practical background and professional direction. Do not list recent "
            "tasks in summary; keep project-specific and technical details in Experience, Projects or Skills."
        )
    ]
    assert payload["typst_payload"]["summary_text"].startswith("Automation and Robotics engineer")


def test_resume_typst_fit_to_page_retries_after_summary_third_person_style_violation(monkeypatch) -> None:
    bad_patch = TypstFitToPagePatch(
        summary_text=(
            "He has practical experience in PLC programming, IoT systems and Python-based engineering tools."
        ),
        experience_bullet_updates=[],
        project_description_updates=[],
        rationale="Try to rewrite summary in third person.",
        warnings=[],
    )
    good_patch = TypstFitToPagePatch(
        summary_text=(
            "Automation and Robotics engineer combining industrial automation experience with "
            "Python-based software and AI-related engineering work."
        ),
        experience_bullet_updates=[],
        project_description_updates=[],
        rationale="Rewrite summary as an implied-subject CV profile.",
        warnings=[],
    )
    retry_feedbacks: list[str | None] = []

    def fake_fit_service(_request, *, retry_feedback=None):
        retry_feedbacks.append(retry_feedback)
        patch = bad_patch if retry_feedback is None else good_patch
        return TypstFitToPagePatchResult(patch=patch, model_name="fake-fit-model")

    monkeypatch.setattr(
        resume_typst_service,
        "generate_typst_fit_to_page_patch_with_openai",
        fake_fit_service,
    )

    with TestClient(app) as client:
        response = client.post("/resume/typst/fit-to-page", json=_build_typst_fit_to_page_request())

    assert response.status_code == 200
    assert len(retry_feedbacks) == 2
    retry_feedback = retry_feedbacks[1]
    assert retry_feedback is not None
    assert "He has" in retry_feedback
    assert "third person" in retry_feedback
    assert "without third-person wording" in retry_feedback
    payload = response.json()
    assert payload["fit_debug"]["retry_attempted"] is True
    assert payload["typst_payload"]["summary_text"].startswith("Automation and Robotics engineer")


@pytest.mark.parametrize(
    "forbidden_payload",
    [
        {"profile": {"full_name": "Changed"}},
        {"skill_entry_updates": [{"entry_index": 0, "text": "Changed skill"}]},
        {"experience_entries": [{"company": "Changed"}]},
        {"project_entries": [{"name": "Changed"}]},
    ],
)
def test_typst_fit_to_page_patch_model_rejects_forbidden_fields(forbidden_payload) -> None:
    payload = {
        "summary_text": None,
        "experience_bullet_updates": [],
        "project_description_updates": [],
        "rationale": "Forbidden field test.",
        "warnings": [],
        **forbidden_payload,
    }

    with pytest.raises(ValidationError):
        TypstFitToPagePatch.model_validate(payload)


def test_resume_typst_prepare_resolves_stored_refined_draft(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)

    _install_fake_typst_fitter(monkeypatch)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        stored_draft = save_resume_draft(
            candidate_profile_id=stored_profile["id"],
            job_posting_id=22,
            match_result_id=33,
            target_job_title=artifacts.resume_draft.target_job_title,
            target_company_name=artifacts.resume_draft.target_company_name,
            generation_mode=artifacts.generation_mode.value,
            base_resume_artifacts=artifacts.model_dump(
                mode="json",
                exclude={"resume_draft_record_id", "resume_draft_saved_at", "persistence_warning"},
            ),
        )
        refined_resume_draft = artifacts.resume_draft.model_copy(
            update={
                "professional_summary": "Refined professional summary for Typst prepare.",
            }
        )
        update_resume_draft_refinement(
            stored_draft["id"],
            refined_resume_artifacts={
                "refined_resume_draft": refined_resume_draft.model_dump(mode="json"),
                "refinement_patch": {
                    "professional_summary": "Refined professional summary for Typst prepare.",
                },
            },
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "draft_id": stored_draft["id"],
                "draft_variant": "refined",
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    parsed_response = TypstPrepareResponse.model_validate(response.json())
    assert parsed_response.prepare_debug is not None
    assert parsed_response.prepare_debug.draft_variant == "refined"
    assert parsed_response.typst_payload.summary_text == "Refined professional summary for Typst prepare."


def test_resume_typst_prepare_assigns_thesis_to_first_completed_entry(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["thesis_title"] = "Adaptive PLC control for distributed automation cells"
    payload["candidate_profile"]["education_entries"] = [
        {
            "institution_name": "Current University",
            "degree": "MSc",
            "field_of_study": "Artificial Intelligence",
            "start_date": "2025",
            "end_date": None,
            "is_current": True,
        },
        {
            "institution_name": "Completed University",
            "degree": "BSc",
            "field_of_study": "Automation",
            "start_date": "2021",
            "end_date": "2024",
            "is_current": False,
        },
    ]

    request = MatchAnalysisRequest.model_validate(payload)
    _install_fake_typst_fitter(monkeypatch)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": artifacts.resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    parsed_response = TypstPrepareResponse.model_validate(response.json())
    assert parsed_response.typst_payload.education_entries[0].thesis is None
    assert (
        parsed_response.typst_payload.education_entries[1].thesis
        == "Adaptive PLC control for distributed automation cells"
    )


def test_resume_typst_prepare_orders_current_education_first_and_formats_english_degree(
    monkeypatch,
) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["thesis_title"] = "Robotics demo platform with embedded control"
    payload["candidate_profile"]["education_entries"] = [
        {
            "institution_name": "Example University of Technology",
            "institution_name_en": "Example University of Technology",
            "degree": "Bachelor",
            "field_of_study": "Automation and Robotics",
            "start_date": "2021-10-01",
            "end_date": "2025-01-23",
            "is_current": False,
        },
        {
            "institution_name": "Example University of Technology",
            "institution_name_en": "Example University of Technology",
            "degree": "Master",
            "field_of_study": "Biomedical engineering",
            "start_date": "2026-02-23",
            "end_date": None,
            "is_current": True,
        },
    ]
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": artifacts.resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    education_entries = captured_inputs[0]["profile_fallback_source"]["education_entries"]
    assert education_entries[0]["institution"] == "Example University of Technology"
    assert education_entries[0]["degree"] == "Master's degree in Biomedical Engineering"
    assert education_entries[0]["thesis"] is None
    assert education_entries[1]["institution"] == "Example University of Technology"
    assert education_entries[1]["degree"] == "Bachelor's degree in Automation and Robotics"
    assert education_entries[1]["thesis"] == "Robotics demo platform with embedded control"
    assert "Bachelor -" not in education_entries[1]["degree"]


def test_resume_typst_prepare_uses_original_institution_name_when_english_alias_is_missing(
    monkeypatch,
) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["education_entries"] = [
        {
            "institution_name": "Example University of Technology",
            "degree": "Master",
            "field_of_study": "Biomedical engineering",
            "start_date": "2026-02-23",
            "end_date": None,
            "is_current": True,
        },
    ]
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": artifacts.resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    education_entries = captured_inputs[0]["profile_fallback_source"]["education_entries"]
    assert education_entries[0]["institution"] == "Example University of Technology"


def test_resume_typst_prepare_omits_thesis_when_only_current_studies_are_selected(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["thesis_title"] = "Adaptive PLC control for distributed automation cells"
    payload["candidate_profile"]["education_entries"] = [
        {
            "institution_name": "Current University One",
            "degree": "MSc",
            "field_of_study": "Artificial Intelligence",
            "start_date": "2025",
            "end_date": None,
            "is_current": True,
        },
        {
            "institution_name": "Current University Two",
            "degree": "Postgraduate Programme",
            "field_of_study": "Data Engineering",
            "start_date": "2026",
            "end_date": None,
            "is_current": True,
        },
    ]

    request = MatchAnalysisRequest.model_validate(payload)
    _install_fake_typst_fitter(monkeypatch)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": artifacts.resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    parsed_response = TypstPrepareResponse.model_validate(response.json())
    assert all(entry.thesis is None for entry in parsed_response.typst_payload.education_entries)


def test_resume_typst_prepare_retries_once_after_limit_validation(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)

    def result_factory(fitter_input, *, retry_feedback, call_index):
        base_payload = _build_fake_typst_payload_from_fitter_input(fitter_input)
        if call_index == 1:
            return base_payload.model_copy(update={"summary_text": "X" * 500})
        assert retry_feedback is not None
        assert "summary_text" in retry_feedback
        assert "500" in retry_feedback
        assert "370" in retry_feedback
        assert "390" in retry_feedback
        assert "never above 390 characters" in retry_feedback
        return base_payload

    calls = _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": artifacts.resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    assert len(calls) == 2
    parsed_response = TypstPrepareResponse.model_validate(response.json())
    assert parsed_response.prepare_debug is not None
    assert "retry" in " ".join(parsed_response.prepare_debug.warnings).lower()
    assert parsed_response.prepare_debug.char_metrics["summary_text"]["char_count"] <= 390


def test_resume_typst_prepare_retries_after_summary_recent_task_style_violation(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    synthetic_user_summary = (
        "Alex Example is an operations-focused candidate with experience improving service workflows, "
        "coordinating small teams and keeping customer-facing processes organized."
    )
    payload["candidate_profile"]["personal_info"]["full_name"] = "Alex Example"
    payload["candidate_profile"]["professional_summary_base"] = synthetic_user_summary
    request = MatchAnalysisRequest.model_validate(payload)

    good_summary = (
        "Automation and Robotics engineer combining industrial automation experience with "
        "Python-based software and AI-related engineering work."
    )

    def result_factory(fitter_input, *, retry_feedback, call_index):
        base_payload = _build_fake_typst_payload_from_fitter_input(fitter_input)
        if call_index == 1:
            return base_payload.model_copy(
                update={
                    "summary_text": (
                        "Recent work includes PLC programming, IoT building automation and "
                        "Python-based tools for engineering tasks."
                    )
                }
            )
        assert retry_feedback is not None
        assert "Recent work includes" in retry_feedback
        assert "candidate profile" in retry_feedback
        assert "Do not list recent tasks" in retry_feedback
        assert "User-authored profile summary preservation" in retry_feedback
        assert "forbidden/system-like phrase" in retry_feedback
        assert "Do not use this phrase or similar system-like/recent-task phrasing" in retry_feedback
        assert "conservative adaptation of the user-authored profile summary below" in retry_feedback
        assert synthetic_user_summary in retry_feedback
        assert "Do not replace it with a project, keyword, technology or job-posting summary" in retry_feedback
        return base_payload.model_copy(update={"summary_text": good_summary})

    calls = _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": artifacts.resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    assert len(calls) == 2
    parsed_response = TypstPrepareResponse.model_validate(response.json())
    assert parsed_response.typst_payload.summary_text == good_summary
    assert parsed_response.prepare_debug is not None
    assert parsed_response.prepare_debug.char_metrics["summary_text"]["exceeds_hard"] is False


def test_resume_typst_summary_retry_feedback_includes_failed_phrase_and_source_summary() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    synthetic_user_summary = (
        "Alex Example is a customer operations specialist focused on clear service processes, "
        "team coordination and reliable day-to-day execution."
    )
    payload["candidate_profile"]["personal_info"]["full_name"] = "Alex Example"
    payload["candidate_profile"]["professional_summary_base"] = synthetic_user_summary
    request = MatchAnalysisRequest.model_validate(payload)
    candidate_profile = CandidateProfile.model_validate(payload["candidate_profile"])
    artifacts = ResumeGenerationResponse.model_validate(
        generate_resume_artifacts(
            request.candidate_profile,
            request.job_posting,
            analyze_match_basic(request),
        )
    )
    resolved_source = resume_typst_service.ResolvedTypstPrepareSource(
        resume_draft=artifacts.resume_draft,
        candidate_profile=candidate_profile,
        source_mode="inline_draft",
        draft_variant=None,
        stored_resume_draft_id=None,
        candidate_profile_id=1,
        warnings=[],
    )

    retry_feedback = resume_typst_service._build_user_authored_summary_retry_feedback(  # noqa: SLF001
        resolved_source,
        [
            (
                'summary_text uses a system-like or recent-task phrase: "Experience spans". '
                "Rewrite summary_text as a fluent candidate profile paragraph."
            )
        ],
    )

    assert retry_feedback is not None
    assert "Experience spans" in retry_feedback
    assert "forbidden/system-like phrase" in retry_feedback
    assert "Do not use this phrase or similar system-like/recent-task phrasing" in retry_feedback
    assert "conservative adaptation of the user-authored profile summary below" in retry_feedback
    assert synthetic_user_summary in retry_feedback
    assert "Do not replace it with a project, keyword, technology or job-posting summary" in retry_feedback


def test_resume_typst_summary_retry_feedback_includes_length_overflow_and_source_summary() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    synthetic_user_summary = (
        "Alex Example is a customer operations specialist focused on clear service processes, "
        "team coordination and reliable day-to-day execution across busy support environments."
    )
    payload["candidate_profile"]["personal_info"]["full_name"] = "Alex Example"
    payload["candidate_profile"]["professional_summary_base"] = synthetic_user_summary
    request = MatchAnalysisRequest.model_validate(payload)
    candidate_profile = CandidateProfile.model_validate(payload["candidate_profile"])
    artifacts = ResumeGenerationResponse.model_validate(
        generate_resume_artifacts(
            request.candidate_profile,
            request.job_posting,
            analyze_match_basic(request),
        )
    )
    resolved_source = resume_typst_service.ResolvedTypstPrepareSource(
        resume_draft=artifacts.resume_draft,
        candidate_profile=candidate_profile,
        source_mode="inline_draft",
        draft_variant=None,
        stored_resume_draft_id=None,
        candidate_profile_id=1,
        warnings=[],
    )

    retry_feedback = resume_typst_service._build_user_authored_summary_retry_feedback(  # noqa: SLF001
        resolved_source,
        ["summary_text exceeds the hard character limit."],
        {
            "summary_text": {
                "char_count": 430,
                "target_chars": 370,
                "hard_chars": 390,
                "exceeds_target": True,
                "exceeds_hard": True,
            }
        },
    )

    assert retry_feedback is not None
    assert "430" in retry_feedback
    assert "370" in retry_feedback
    assert "390" in retry_feedback
    assert "about 370" in retry_feedback
    assert "must be <= 390" in retry_feedback
    assert "semantic source of truth" in retry_feedback
    assert "Hard character limits outrank wording preservation" in retry_feedback
    assert "do not preserve exact wording if that prevents meeting the limit" in retry_feedback
    assert "Do not copy source transitions like My recent experience includes" in retry_feedback
    assert synthetic_user_summary in retry_feedback
    assert "Preserve its meaning and professional direction" in retry_feedback
    assert "Do not replace it with a project, keyword, technology or job-posting summary" in retry_feedback


def test_resume_typst_summary_retry_feedback_combines_failed_phrase_and_length_overflow() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    synthetic_user_summary = (
        "Alex Example is a logistics coordinator focused on reliable warehouse processes, "
        "clear operational communication and practical problem-solving."
    )
    payload["candidate_profile"]["personal_info"]["full_name"] = "Alex Example"
    payload["candidate_profile"]["professional_summary_base"] = synthetic_user_summary
    request = MatchAnalysisRequest.model_validate(payload)
    candidate_profile = CandidateProfile.model_validate(payload["candidate_profile"])
    artifacts = ResumeGenerationResponse.model_validate(
        generate_resume_artifacts(
            request.candidate_profile,
            request.job_posting,
            analyze_match_basic(request),
        )
    )
    resolved_source = resume_typst_service.ResolvedTypstPrepareSource(
        resume_draft=artifacts.resume_draft,
        candidate_profile=candidate_profile,
        source_mode="inline_draft",
        draft_variant=None,
        stored_resume_draft_id=None,
        candidate_profile_id=1,
        warnings=[],
    )

    retry_feedback = resume_typst_service._build_user_authored_summary_retry_feedback(  # noqa: SLF001
        resolved_source,
        [
            'summary_text uses a system-like or recent-task phrase: "Recent experience includes".',
            "summary_text exceeds the hard character limit.",
        ],
        {
            "summary_text": {
                "char_count": 430,
                "target_chars": 370,
                "hard_chars": 390,
                "exceeds_target": True,
                "exceeds_hard": True,
            }
        },
    )

    assert retry_feedback is not None
    assert "Recent experience includes" in retry_feedback
    assert "Do not use this phrase or similar system-like/recent-task phrasing" in retry_feedback
    assert "430" in retry_feedback
    assert "about 370" in retry_feedback
    assert "must be <= 390" in retry_feedback
    assert "semantic source of truth" in retry_feedback
    assert synthetic_user_summary in retry_feedback


def test_resume_typst_prepare_retry_feedback_includes_summary_char_metrics() -> None:
    validation_error = resume_typst_service.TypstPayloadValidationError(
        "Typst payload validation failed.",
        violations=["summary_text exceeds the hard character limit."],
        section_counts={},
        char_metrics={
            "summary_text": {
                "char_count": 419,
                "target_chars": 370,
                "hard_chars": 390,
                "exceeds_target": True,
                "exceeds_hard": True,
            }
        },
    )

    retry_feedback = validation_error.to_retry_feedback()

    assert "summary_text" in retry_feedback
    assert "419" in retry_feedback
    assert "370" in retry_feedback
    assert "390" in retry_feedback
    assert "Hard character limits are absolute" in retry_feedback
    assert "never above 390 characters" in retry_feedback


def test_resume_typst_summary_style_guardrail_blocks_recent_task_phrases() -> None:
    payload = TypstPayload.model_validate(_build_typst_render_request()["typst_payload"]).model_copy(
        update={
            "summary_text": (
                "Recent work includes PLC programming, IoT building automation and Python tools."
            )
        }
    )

    with pytest.raises(resume_typst_service.TypstPayloadValidationError) as exc_info:
        resume_typst_service._validate_typst_payload(payload)  # noqa: SLF001

    validation_error = exc_info.value
    assert any(
        'summary_text uses a system-like or recent-task phrase: "Recent work includes"'
        in violation
        for violation in validation_error.violations
    )
    retry_feedback = validation_error.to_retry_feedback()
    assert "Recent work includes" in retry_feedback
    assert "candidate profile" in retry_feedback
    assert "Do not list recent tasks" in retry_feedback


def test_resume_typst_summary_style_guardrail_allows_career_direction_phrases() -> None:
    for summary in [
        (
            "Automation and Robotics engineer pursuing a Master's degree in Biomedical Engineering. "
            "Interested in growing toward software and AI engineering roles focused on practical applications."
        ),
        (
            "Automation and Robotics engineer combining PLC/CODESYS work with Python software development. "
            "Looking to grow in engineering roles that connect automation, data and software tools."
        ),
    ]:
        payload = TypstPayload.model_validate(_build_typst_render_request()["typst_payload"]).model_copy(
            update={"summary_text": summary}
        )
        section_counts, char_metrics = resume_typst_service._validate_typst_payload(payload)  # noqa: SLF001
        assert section_counts["experience_entries"] == 1
        assert char_metrics["summary_text"]["exceeds_hard"] is False


@pytest.mark.parametrize(
    "summary, blocked_phrase",
    [
        (
            "He has practical experience in PLC programming and Python-based software tools.",
            "He has",
        ),
        (
            "The candidate has practical experience in PLC programming and Python-based software tools.",
            "The candidate has",
        ),
    ],
)
def test_resume_typst_summary_style_guardrail_blocks_third_person_phrases(
    summary,
    blocked_phrase,
) -> None:
    payload = TypstPayload.model_validate(_build_typst_render_request()["typst_payload"]).model_copy(
        update={"summary_text": summary}
    )

    with pytest.raises(resume_typst_service.TypstPayloadValidationError) as exc_info:
        resume_typst_service._validate_typst_payload(payload)  # noqa: SLF001

    validation_error = exc_info.value
    assert any(
        f'summary_text is written in third person ("{blocked_phrase}")' in violation
        for violation in validation_error.violations
    )
    retry_feedback = validation_error.to_retry_feedback()
    assert blocked_phrase in retry_feedback
    assert "third person" in retry_feedback
    assert "without third-person wording" in retry_feedback


def test_resume_typst_fitter_prompt_documents_translation_and_source_technology_rules() -> None:
    prompt = RESUME_TYPST_FITTER_INSTRUCTIONS

    assert "faithfully translate" in prompt
    assert "must not add new facts" in prompt
    assert "institution_name_en" in prompt
    assert "controlled display alias" in prompt
    assert "selected projects and selected experience are strong evidence" in prompt
    assert "source_technologies" in prompt
    assert "FastAPI" in prompt
    assert "CiA 402" in prompt


def test_resume_typst_fitter_prompt_keeps_summary_profile_oriented() -> None:
    prompt = RESUME_TYPST_FITTER_INSTRUCTIONS

    assert "profile-oriented CV summary" in prompt
    assert "primary_summary_source" in prompt
    assert "user_authored_profile_summary_available" in prompt
    assert "conservative adaptation of `primary_summary_source.user_authored_profile_summary`" in prompt
    assert "semantic source of truth for `summary_text`" in prompt
    assert "aim for about 370 characters and never exceed 390 characters" in prompt
    assert "Preserve meaning and professional direction, not necessarily exact wording" in prompt
    assert "Keep wording close to the original only when it fits within the character limits" in prompt
    assert "Hard character limits outrank wording preservation" in prompt
    assert "compress it aggressively enough to fit `target_chars` when possible and always under `hard_chars`" in prompt
    assert "Do not copy the full user-authored summary if it exceeds the limit" in prompt
    assert "meaning preservation > hard limit compliance > concise CV style > wording preservation > light role alignment" in prompt
    assert "Preserve its meaning, professional direction, structure and most of its wording" not in prompt
    assert "If `primary_summary_source.user_authored_profile_summary_available` is true, do not compose a new summary" in prompt
    assert "Do not generate a new summary from job keywords, projects, technologies or job posting content" in prompt
    assert "Do not replace the user-authored profile summary with a project summary" in prompt
    assert "fluent, natural CV profile paragraph" in prompt
    assert "usually 2 connected sentences and maximum 3 only if still under target and hard limits" in prompt
    assert "Do not write `summary_text` as a keyword list" in prompt
    assert "list of recent tasks" in prompt
    assert "Do not copy source-note transitions" in prompt
    assert "My recent experience includes" in prompt
    assert "Avoid first-person pronouns" in prompt
    assert "Recent work includes" in prompt
    assert "Recent experience includes" in prompt
    assert "Current work includes" in prompt
    assert "Experience spans" in prompt
    assert "Background spans" in prompt
    assert "Candidate has" in prompt
    assert "Profile includes" in prompt
    assert "He has" in prompt
    assert "She has" in prompt
    assert "The candidate has" in prompt
    assert "This candidate" in prompt
    assert "Do not use third-person wording" in prompt
    assert "rather than writing as if describing another person" in prompt
    assert "Interested in" in prompt
    assert "Looking to grow" in prompt
    assert "career direction, target roles or professional development" in prompt
    assert "Do not use a generic first/second/third sentence structure as a replacement" in prompt
    assert "The first/second/third sentence guidance applies only when no usable user-authored profile summary exists" in prompt
    assert "When no usable user-authored profile summary exists, the first sentence should state the candidate profile" in prompt
    assert "When no usable user-authored profile summary exists, the second sentence should connect practical experience" in prompt
    assert "When no usable user-authored profile summary exists, an optional third sentence may indicate professional direction" in prompt
    assert "describe the candidate as a whole" in prompt
    assert "stay within the domains and direction already present in that summary" in prompt
    assert "must not become a technology or keyword inventory" in prompt
    assert "Do not use `summary_text` as a place to pack technical details" in prompt
    assert "Detailed systems, product names, project names and technical standards belong in Experience, Projects and Skills" in prompt
    assert "specificity" in prompt
    assert "Experience and Projects before making the summary longer" in prompt


def test_resume_typst_fitter_prompt_keeps_soft_skills_separate_from_technical_skills() -> None:
    prompt = RESUME_TYPST_FITTER_INSTRUCTIONS

    assert "Soft skills must remain separate from technical skills" in prompt
    assert "dedicated line such as `Soft skills:" in prompt
    assert "Never mix soft skills and technical skills in the same skill line" in prompt
    assert "`Electrical Engineering & Soft skills`" in prompt
    assert "`Automation & Soft skills`" in prompt
    assert "`Software & Soft skills`" in prompt
    assert "2 technical lines plus 1 separate soft-skills line, or 3 technical lines" in prompt


def test_resume_typst_fitter_prompt_guides_experience_bullets_without_technology_overload() -> None:
    prompt = RESUME_TYPST_FITTER_INSTRUCTIONS

    assert "professionally specific and recruiter-readable" in prompt
    assert "not laboratory notes or overloaded technical documentation" in prompt
    assert "Usually 1-2 relevant technologies" in prompt
    assert "Do not pack a long technology list into one bullet" in prompt
    assert "Avoid vague phrasing such as \"contributed to\"" in prompt
    assert "source_technologies" in prompt
    assert "source_keywords" in prompt
    assert "source_responsibilities" in prompt
    assert "source_achievements" in prompt
    assert "only when those fields are attached to that same selected or fallback experience entry" in prompt
    assert "not to be copied wholesale into dense lists" in prompt


def test_typst_quality_analysis_prompt_keeps_summary_as_light_underfilled_option() -> None:
    prompt = TYPST_QUALITY_ANALYSIS_INSTRUCTIONS

    assert "summary only lightly and generally" in prompt
    assert "Do not treat the summary as the main page-filling mechanism" in prompt
    assert "expanding experience bullets and project descriptions before summary" in prompt
    assert "do not recommend filling the page by adding task" in prompt
    assert "career direction or ambition" in prompt
    assert "Recent work includes" in prompt
    assert "mark it as a style issue" in prompt
    assert "candidate profile" in prompt
    assert "Do not recommend adding detailed technical systems" in prompt
    assert "Experience, Projects or Skills" in prompt


def test_typst_fit_to_page_prompt_prefers_meaningful_experience_expansion() -> None:
    prompt = TYPST_FIT_TO_PAGE_INSTRUCTIONS

    assert "Retry feedback is mandatory and must be followed exactly" in prompt
    assert "Never exceed hard limits" in prompt
    assert "shorten that project description instead of expanding it again" in prompt
    assert "Project descriptions are secondary expansion targets" in prompt
    assert "must stay comfortably below hard limits" in prompt
    assert "expand experience bullets first, project descriptions second, and summary" in prompt
    assert "summary only last and lightly" in prompt
    assert "meaningful rather than cosmetic" in prompt
    assert "Do not stop after one minor wording change" in prompt
    assert "Prefer improving most short experience bullets" in prompt
    assert "Use the supplied target lengths as density guidance" in prompt
    assert "standard CV bullet style with implied first person" in prompt
    assert "\"Worked on\" is allowed" in prompt
    assert "do not use it as the default weak opening" in prompt
    assert "no forced third-person phrasing" in prompt


def test_typst_fit_to_page_prompt_blocks_artificial_filler_phrases() -> None:
    prompt = TYPST_FIT_TO_PAGE_INSTRUCTIONS

    assert "Recent work includes" in prompt
    assert "Recent experience includes" in prompt
    assert "Current work includes" in prompt
    assert "Experience spans" in prompt
    assert "Background spans" in prompt
    assert "Profile includes" in prompt
    assert "Candidate has" in prompt
    assert "He has" in prompt
    assert "She has" in prompt
    assert "The candidate has" in prompt
    assert "This candidate" in prompt
    assert "natural CV profile style with an implied subject" in prompt
    assert "force" in prompt
    assert "optional expansion despite quality analysis not requiring it" in prompt
    assert "Summary is not a page filler" in prompt
    assert "default fit-to-page behavior is to return" in prompt
    assert "`summary_text: null`" in prompt
    assert "Modify `summary_text` only when needed for overfill, hard limit, explicit style" in prompt
    assert "user-authored profile summary" in prompt
    assert "preserve that source summary's meaning and professional direction" in prompt
    assert "Hard limits outrank" in prompt
    assert "wording preservation" in prompt
    assert "Do not replace summary_text with job keywords, projects, technologies" in prompt
    assert "candidate-profile style" in prompt
    assert "recent tasks" in prompt
    assert "Interested in" in prompt
    assert "Looking to grow" in prompt
    assert "career direction, target roles or professional development" in prompt
    assert "Interested in ... practical engineering workflows" in prompt
    assert "practical shop-floor environment" in prompt
    assert "practical engineering workflows" in prompt
    assert "turning analysis into real-world" in prompt
    assert "bridging concepts with operational outcomes" in prompt
    assert "pseudo-technical phrasing" in prompt
    assert "direct factual phrasing" in prompt
    assert "source evidence" in prompt
    assert "leave it unchanged rather than adding abstract marketing filler" in prompt


def test_typst_fit_to_page_prompt_contains_semantic_precision_rules() -> None:
    prompt = TYPST_FIT_TO_PAGE_INSTRUCTIONS

    assert "source_evidence_pack as the source of truth" in prompt
    assert "Do not create new relationships between tools, languages, standards, methods" in prompt
    assert "certificates, tasks, products and outcomes" in prompt
    assert "use more neutral phrasing or keep the text shorter" in prompt
    assert "Do not join terms into one phrase just because they appear near each other" in prompt
    assert "When evidence confidence is low" in prompt
    assert "No external lookup is available" in prompt
    assert "a tool is not automatically a programming" in prompt


def test_resume_typst_prepare_returns_controlled_error_when_fitter_fails(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)

    def result_factory(fitter_input, *, retry_feedback, call_index):
        return ResumeTypstFitterOpenAIError(
            "OpenAI Typst fitter request failed.",
            status_code=502,
        )

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": artifacts.resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["error_code"] == "typst_fitter_failed"
    assert detail["stage"] == "prepare"
    assert detail["message"] == "OpenAI Typst fitter request failed."
    assert detail["retry_attempted"] is False
    assert detail["fitter_model"] is None


def test_resume_typst_prepare_returns_422_when_payload_still_breaks_limits_after_retry(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)

    def result_factory(fitter_input, *, retry_feedback, call_index):
        base_payload = _build_fake_typst_payload_from_fitter_input(fitter_input)
        return base_payload.model_copy(update={"summary_text": "Y" * 500})

    calls = _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": artifacts.resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert len(calls) == 2
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error_code"] == "typst_payload_validation_failed"
    assert detail["stage"] == "prepare"
    assert detail["message"] == "Typst payload validation failed."
    assert detail["retry_attempted"] is True
    assert detail["fitter_model"] == "gpt-5.4-mini"
    assert "summary_text exceeds the hard character limit." in detail["validation_errors"]
    assert detail["char_metrics"]["summary_text"]["char_count"] == 500
    assert detail["section_counts"]["experience_entries"] <= 2


def test_resume_typst_prepare_uses_profile_fallback_only_when_natural(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        sparse_resume_draft = artifacts.resume_draft.model_copy(
            update={
                "selected_skills": [],
                "selected_soft_skill_entries": [],
                "selected_language_entries": [],
                "selected_certificate_entries": [],
            }
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": sparse_resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "pl",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    assert len(captured_inputs) == 1
    profile_fallback_source = captured_inputs[0]["profile_fallback_source"]
    assert captured_inputs[0]["draft_primary_source"]["selected_skills"] == []
    assert captured_inputs[0]["draft_primary_source"]["selected_soft_skill_entries"] == []
    assert "skill_entries" in profile_fallback_source
    assert "language_certificate_entries" in profile_fallback_source
    assert "experience_entries" not in profile_fallback_source
    assert "project_entries" in profile_fallback_source


def test_resume_typst_prepare_exposes_sensible_experience_fallback_when_draft_has_none(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        sparse_resume_draft = artifacts.resume_draft.model_copy(
            update={
                "selected_experience_entries": [],
            }
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": sparse_resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    assert len(captured_inputs) == 1
    profile_fallback_source = captured_inputs[0]["profile_fallback_source"]
    assert "experience_entries" in profile_fallback_source
    assert profile_fallback_source["experience_entries"]


def test_resume_typst_prepare_tops_up_experience_when_draft_has_one(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["experience_entries"] = [
        {
            "id": "exp_primary",
            "company_name": "Orion Systems",
            "position_title": "Automation Engineer",
            "start_date": "2025-10-01",
            "end_date": "2026-03-10",
            "is_current": False,
            "location": "Example City",
            "responsibilities": [
                "Designed IoT-based building automation systems for educational institutions.",
                "Configured drive control sequences for robotic workstations.",
            ],
            "achievements": [],
            "technologies_used": ["PLC", "CiA 402", "drive control", "cobot programming"],
            "keywords": ["IoT automation", "motion control"],
        },
        {
            "id": "exp_topup",
            "company_name": "Northbridge Automation",
            "position_title": "Electrical Engineering Intern",
            "start_date": "2025-06-01",
            "end_date": "2025-08-30",
            "is_current": False,
            "location": "Example City",
            "responsibilities": [
                "Assembled control cabinets based on technical documentation."
            ],
            "achievements": [],
            "technologies_used": ["EPLAN", "control cabinets"],
            "keywords": ["technical documentation"],
        },
    ]
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        one_experience_draft = artifacts.resume_draft.model_dump(mode="json")
        one_experience_draft["selected_experience_entries"] = [
            {
                "source_experience_id": "exp_primary",
                "company_name": "Orion Systems",
                "position_title": "Automation Engineer",
                "date_range": "2025-10-01 - 2026-03-10",
                "bullet_points": [
                    "Designed IoT-based building automation systems for educational institutions."
                ],
                "highlighted_keywords": ["automation"],
                "relevance_note": "Relevant automation work.",
                "source_highlights": ["Designed IoT-based building automation systems"],
            }
        ]
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": one_experience_draft,
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    profile_fallback_source = captured_inputs[0]["profile_fallback_source"]
    draft_primary_source = captured_inputs[0]["draft_primary_source"]
    selected_experience = draft_primary_source["selected_experience_entries"][0]
    assert selected_experience["source_technologies"] == [
        "PLC",
        "CiA 402",
        "drive control",
        "cobot programming",
    ]
    assert selected_experience["source_keywords"] == [
        "IoT automation",
        "motion control",
    ]
    assert selected_experience["source_responsibilities"] == [
        "Designed IoT-based building automation systems for educational institutions.",
        "Configured drive control sequences for robotic workstations.",
    ]
    assert profile_fallback_source["skill_source_material"]["selected_experience_technologies"] == [
        "PLC",
        "CiA 402",
        "drive control",
        "cobot programming",
    ]
    assert "experience_entries" in profile_fallback_source
    assert len(profile_fallback_source["experience_entries"]) == 1
    assert " -01" not in profile_fallback_source["experience_entries"][0]["date"]
    assert profile_fallback_source["experience_entries"][0]["source_technologies"] == [
        "EPLAN",
        "control cabinets",
    ]
    assert profile_fallback_source["experience_entries"][0]["source_keywords"] == [
        "technical documentation"
    ]

    parsed_response = TypstPrepareResponse.model_validate(response.json())
    assert len(parsed_response.typst_payload.experience_entries) == 2


def test_resume_typst_prepare_tops_up_project_when_draft_has_one(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["project_entries"] = [
        {
            "id": "project_primary",
            "project_name": "Resume Tailoring Agent",
            "role": "Developer",
            "description": "Local app for tailoring CVs to job offers.",
            "technologies_used": ["Python", "FastAPI", "React", "SQLite", "OpenAI API"],
            "outcomes": [
                "Built a FastAPI backend and React frontend for resume draft generation."
            ],
            "keywords": ["AI-assisted CV tailoring"],
            "link": None,
        },
        {
            "id": "project_topup",
            "project_name": "Robotics Demo Platform",
            "role": "Embedded Developer",
            "description": "Designed and implemented a walking robot prototype.",
            "technologies_used": ["C++"],
            "outcomes": [
                "Built embedded control logic and mechanical integration for the prototype."
            ],
            "keywords": [],
            "link": None,
        },
    ]
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        one_project_draft = artifacts.resume_draft.model_dump(mode="json")
        one_project_draft["selected_project_entries"] = [
            {
                "source_project_id": "project_primary",
                "project_name": "Resume Tailoring Agent",
                "role": "Developer",
                "link": None,
                "bullet_points": [
                    "Built a FastAPI backend and React frontend for resume draft generation."
                ],
                "highlighted_keywords": ["FastAPI"],
                "relevance_note": "Relevant software project.",
                "source_highlights": ["Built a FastAPI backend"],
            }
        ]
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": one_project_draft,
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    profile_fallback_source = captured_inputs[0]["profile_fallback_source"]
    draft_primary_source = captured_inputs[0]["draft_primary_source"]
    selected_project = draft_primary_source["selected_project_entries"][0]
    assert selected_project["source_technologies"] == [
        "Python",
        "FastAPI",
        "React",
        "SQLite",
        "OpenAI API",
    ]
    assert selected_project["source_keywords"] == ["AI-assisted CV tailoring"]
    assert selected_project["source_outcomes"] == [
        "Built a FastAPI backend and React frontend for resume draft generation."
    ]
    assert profile_fallback_source["skill_source_material"]["selected_project_technologies"] == [
        "Python",
        "FastAPI",
        "React",
        "SQLite",
        "OpenAI API",
    ]
    assert "project_entries" in profile_fallback_source
    assert len(profile_fallback_source["project_entries"]) == 1

    parsed_response = TypstPrepareResponse.model_validate(response.json())
    project_names = [entry.name.lower().strip() for entry in parsed_response.typst_payload.project_entries]
    assert len(project_names) == 2
    assert len(set(project_names)) == 2


def test_resume_typst_prepare_deduplicates_duplicate_project_names_from_fitter(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)

    def result_factory(fitter_input, *, retry_feedback, call_index):
        base_payload = _build_fake_typst_payload_from_fitter_input(fitter_input)
        duplicate_projects = [
            TypstProjectEntry(
                name="Resume Tailoring Agent",
                description="Local CV tailoring app with FastAPI and React.",
            ),
            TypstProjectEntry(
                name=" resume   tailoring agent ",
                description="Duplicate wording for the same project should not survive.",
            ),
        ]
        return base_payload.model_copy(update={"project_entries": duplicate_projects})

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": artifacts.resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    parsed_response = TypstPrepareResponse.model_validate(response.json())
    assert [entry.name for entry in parsed_response.typst_payload.project_entries] == [
        "Resume Tailoring Agent"
    ]


def test_resume_typst_prepare_exposes_skill_category_lines_when_draft_skills_are_sparse(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["skill_entries"] = [
        {
            "name": "Python",
            "category": "Programming",
            "level": "Intermediate",
            "years_of_experience": None,
            "evidence_sources": [],
            "aliases": [],
        },
        {
            "name": "PLC programming",
            "category": "Industrial Automation",
            "level": "Intermediate",
            "years_of_experience": None,
            "evidence_sources": [],
            "aliases": ["CODESYS", "TIA Portal", "Structured Text", "CiA 402"],
        },
        {
            "name": "Electrical design",
            "category": "Electrical Engineering",
            "level": "Intermediate",
            "years_of_experience": None,
            "evidence_sources": [],
            "aliases": [],
        },
    ]
    payload["candidate_profile"]["soft_skill_entries"] = [
        "analytical problem-solving",
        "teamwork",
        "time management",
    ]
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        sparse_skill_draft = artifacts.resume_draft.model_copy(
            update={
                "selected_skills": ["Python"],
                "selected_soft_skill_entries": [],
            }
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": sparse_skill_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    profile_fallback_source = captured_inputs[0]["profile_fallback_source"]
    assert profile_fallback_source["skill_entries"]
    assert all(":" in entry for entry in profile_fallback_source["skill_entries"])
    assert profile_fallback_source["skill_entries"] != ["Python", "Backend"]
    assert any(
        entry.startswith("Automation & Control:") and "PLC programming" in entry
        for entry in profile_fallback_source["skill_entries"]
    )
    assert not any(
        entry.startswith("Software & AI:") and "PLC programming" in entry
        for entry in profile_fallback_source["skill_entries"]
    )
    assert profile_fallback_source["skill_source_material"]["soft_skills"] == [
        "analytical problem-solving",
        "teamwork",
        "time management",
    ]
    plc_material = next(
        entry
        for entry in profile_fallback_source["skill_source_material"]["technical_skills"]
        if entry["name"] == "PLC programming"
    )
    assert plc_material["aliases"] == ["CODESYS", "TIA Portal", "Structured Text", "CiA 402"]

    parsed_response = TypstPrepareResponse.model_validate(response.json())
    assert all(":" in entry for entry in parsed_response.typst_payload.skill_entries)


def test_resume_typst_prepare_skips_unusable_project_fallback(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["project_entries"] = [
        {
            "id": "proj_bad_1",
            "project_name": "X",
            "role": "Dev",
            "description": "",
            "technologies_used": [],
            "outcomes": [""],
            "keywords": [],
            "link": None,
        }
    ]
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": artifacts.resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    assert "project_entries" not in captured_inputs[0]["profile_fallback_source"]


def test_resume_typst_prepare_skips_unusable_experience_fallback(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["experience_entries"] = [
        {
            "id": "exp_bad_1",
            "company_name": "A",
            "position_title": "B",
            "start_date": "2024",
            "end_date": None,
            "is_current": False,
            "location": "Remote",
            "responsibilities": [""],
            "achievements": [""],
            "technologies_used": [],
            "keywords": [],
        }
    ]
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        sparse_resume_draft = artifacts.resume_draft.model_copy(
            update={
                "selected_experience_entries": [],
            }
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": sparse_resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    assert "experience_entries" not in captured_inputs[0]["profile_fallback_source"]


def test_resume_typst_prepare_skips_unusable_skill_and_language_fallbacks(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["skill_entries"] = [
        {
            "name": "",
            "category": "",
            "level": "",
            "years_of_experience": None,
            "evidence_sources": [],
            "aliases": [],
        }
    ]
    payload["candidate_profile"]["soft_skill_entries"] = [""]
    payload["candidate_profile"]["language_entries"] = [
        {
            "language_name": "",
            "proficiency_level": "",
        }
    ]
    payload["candidate_profile"]["certificate_entries"] = [
        {
            "certificate_name": "",
            "issuer": "",
            "issue_date": None,
            "notes": None,
        }
    ]
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        sparse_resume_draft = artifacts.resume_draft.model_copy(
            update={
                "selected_skills": [],
                "selected_soft_skill_entries": [],
                "selected_language_entries": [],
                "selected_certificate_entries": [],
            }
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": sparse_resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    profile_fallback_source = captured_inputs[0]["profile_fallback_source"]
    assert "skill_entries" not in profile_fallback_source
    assert "language_certificate_entries" not in profile_fallback_source


def test_resume_typst_prepare_tops_up_language_certificates_without_noise(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["language_entries"] = [
        {
            "language_name": "English",
            "proficiency_level": "C1",
        }
    ]
    payload["candidate_profile"]["certificate_entries"] = [
        {
            "certificate_name": "Example English Certificate (B2)",
            "issuer": "",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": "Example Elec Cert",
            "issuer": "Example Org",
            "issue_date": "2025-08-20",
            "notes": "1kV",
        },
        {
            "certificate_name": "Example Safety Training",
            "issuer": "",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": "",
            "issuer": "Coursera",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": "todo",
            "issuer": "Microsoft",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": "Blocked Cert",
            "issuer": "Vendor",
            "issue_date": None,
            "notes": None,
        },
    ]
    payload["candidate_profile"]["immutable_rules"]["forbidden_certificates"] = ["Blocked Cert"]
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        partial_language_certificate_draft = artifacts.resume_draft.model_copy(
            update={
                "selected_language_entries": ["English - C1"],
                "selected_certificate_entries": ["Example English Certificate (B2)"],
            }
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": partial_language_certificate_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    profile_fallback_source = captured_inputs[0]["profile_fallback_source"]
    assert profile_fallback_source["language_certificate_entries"] == [
        "Example Elec Cert (1kV)",
        "Example Safety Training",
    ]

    parsed_response = TypstPrepareResponse.model_validate(response.json())
    assert "Example Elec Cert (1kV)" in parsed_response.typst_payload.language_certificate_entries
    assert "Example Safety Training" in parsed_response.typst_payload.language_certificate_entries
    assert "Coursera" not in parsed_response.typst_payload.language_certificate_entries
    assert "Blocked Cert - Vendor" not in parsed_response.typst_payload.language_certificate_entries
    assert not any(
        "2025-08-20" in entry
        for entry in parsed_response.typst_payload.language_certificate_entries
    )


def test_resume_typst_prepare_filters_language_certificate_fallback_quality(monkeypatch) -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["language_entries"] = [
        {
            "language_name": "English",
            "proficiency_level": "C1",
        },
        {
            "language_name": "  english  ",
            "proficiency_level": " C1 ",
        },
        {
            "language_name": "English",
            "proficiency_level": "",
        },
        {
            "language_name": "",
            "proficiency_level": "C1",
        },
        {
            "language_name": "unknown",
            "proficiency_level": "B2",
        },
        {
            "language_name": "2024",
            "proficiency_level": "",
        },
        {
            "language_name": "-",
            "proficiency_level": "",
        },
    ]
    payload["candidate_profile"]["certificate_entries"] = [
        {
            "certificate_name": "Example Elec Cert",
            "issuer": "Example Org",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": " old short cert ",
            "issuer": " legacy org ",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": "",
            "issuer": "Coursera",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": "n/a",
            "issuer": "Issuer",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": "unknown",
            "issuer": "",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": "todo",
            "issuer": "Microsoft",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": "-",
            "issuer": "",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": "2024-05",
            "issuer": "",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": "Blocked Cert",
            "issuer": "Microsoft",
            "issue_date": None,
            "notes": None,
        },
        {
            "certificate_name": "Legacy Cert",
            "issuer": "Vendor",
            "issue_date": None,
            "notes": None,
        },
    ]
    payload["candidate_profile"]["immutable_rules"]["forbidden_certificates"] = [
        "blocked cert",
        "old short cert - legacy org",
        "Legacy Cert - Vendor",
    ]
    request = MatchAnalysisRequest.model_validate(payload)

    captured_inputs: list[dict[str, object]] = []

    def result_factory(fitter_input, *, retry_feedback, call_index):
        captured_inputs.append(fitter_input)
        return _build_fake_typst_payload_from_fitter_input(fitter_input)

    _install_fake_typst_fitter(monkeypatch, result_factory=result_factory)

    with TestClient(app) as client:
        stored_profile = save_candidate_profile(CandidateProfile.model_validate(payload["candidate_profile"]))
        artifacts = ResumeGenerationResponse.model_validate(
            generate_resume_artifacts(
                request.candidate_profile,
                request.job_posting,
                analyze_match_basic(request),
            )
        )
        sparse_resume_draft = artifacts.resume_draft.model_copy(
            update={
                "selected_language_entries": [],
                "selected_certificate_entries": [],
            }
        )
        response = client.post(
            "/resume/typst/prepare",
            json={
                "final_resume_draft": sparse_resume_draft.model_dump(mode="json"),
                "candidate_profile_id": stored_profile["id"],
                "options": {
                    "language": "en",
                    "include_photo": False,
                    "consent_mode": "default",
                    "custom_consent_text": None,
                    "photo_asset_id": None,
                },
            },
        )

    assert response.status_code == 200
    profile_fallback_source = captured_inputs[0]["profile_fallback_source"]
    assert profile_fallback_source["language_certificate_entries"] == [
        "English - C1",
        "English",
        "Example Elec Cert - Example Org",
    ]

    parsed_response = TypstPrepareResponse.model_validate(response.json())
    assert parsed_response.typst_payload.language_certificate_entries == [
        "English - C1",
        "English",
        "Example Elec Cert - Example Org",
    ]


def test_resume_typst_prepare_language_certificate_formatters_require_specific_names() -> None:
    assert resume_typst_service._format_language_entry("English", "C1") == "English - C1"  # noqa: SLF001
    assert resume_typst_service._format_language_entry("English", "") == "English"  # noqa: SLF001
    assert resume_typst_service._format_language_entry("", "C1") is None  # noqa: SLF001
    assert resume_typst_service._format_language_entry("C1", "") is None  # noqa: SLF001

    assert resume_typst_service._format_certificate_entry("Example Elec Cert", "Example Org", "2025-08-20") == "Example Elec Cert - Example Org"  # noqa: SLF001
    assert resume_typst_service._format_certificate_entry("Example Elec Cert", "Example Org", "2025-08-20", "1kV") == "Example Elec Cert (1kV)"  # noqa: SLF001
    assert resume_typst_service._format_certificate_entry("Legacy Cert", "Vendor", None) == "Legacy Cert - Vendor"  # noqa: SLF001
    assert resume_typst_service._format_certificate_entry("", "Coursera", None) is None  # noqa: SLF001
    assert resume_typst_service._format_certificate_entry("n/a", "Issuer", None) is None  # noqa: SLF001
    assert resume_typst_service._format_certificate_entry("unknown", "Issuer", None) is None  # noqa: SLF001
    assert resume_typst_service._format_certificate_entry("todo", "Issuer", None) is None  # noqa: SLF001
    assert resume_typst_service._format_certificate_entry("-", "Issuer", None) is None  # noqa: SLF001
    assert resume_typst_service._format_certificate_entry("2024-05", "Issuer", None) is None  # noqa: SLF001


def test_resume_typst_prepare_formats_iso_dates_for_cv_display() -> None:
    assert (
        resume_typst_service._format_cv_friendly_education_date_value(  # noqa: SLF001
            "2022-10-01 - 2026-01-23"
        )
        == "2022 - 2026"
    )
    assert (
        resume_typst_service._format_cv_friendly_education_date_value(  # noqa: SLF001
            "2026-02-23 - Present"
        )
        == "2026 - Present"
    )
    assert (
        resume_typst_service._format_cv_friendly_experience_date_value(  # noqa: SLF001
            "2025-06-01 - 2025-08-30"
        )
        == "Jun 2025 - Aug 2025"
    )
    assert (
        resume_typst_service._format_cv_friendly_experience_date_value(  # noqa: SLF001
            "2025-10-01 - 2026-03-10"
        )
        == "Oct 2025 - Mar 2026"
    )
    assert (
        resume_typst_service._strip_certificate_issue_date_from_display(  # noqa: SLF001
            "Example Elec Cert - Example Org - 2025-08-20"
        )
        == "Example Elec Cert - Example Org"
    )


def test_resume_typst_prepare_resolve_supported_links_prefers_profile_over_draft_links() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request = MatchAnalysisRequest.model_validate(payload)
    artifacts = ResumeGenerationResponse.model_validate(
        generate_resume_artifacts(
            request.candidate_profile,
            request.job_posting,
            analyze_match_basic(request),
        )
    )
    draft_with_different_links = artifacts.resume_draft.model_copy(
        update={
            "header": artifacts.resume_draft.header.model_copy(
                update={
                    "links": [
                        "https://linkedin.com/in/example-from-draft",
                        "https://github.com/example-from-draft",
                    ]
                }
            )
        }
    )

    linkedin, github = resume_typst_service._resolve_supported_links(  # noqa: SLF001
        draft_with_different_links,
        request.candidate_profile,
    )

    assert linkedin == str(request.candidate_profile.personal_info.linkedin_url)
    assert github == str(request.candidate_profile.personal_info.github_url)


def test_resolve_supported_links_prefers_profile_then_uses_safe_draft_heuristic() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["personal_info"]["linkedin_url"] = None
    payload["candidate_profile"]["personal_info"]["github_url"] = None
    request = MatchAnalysisRequest.model_validate(payload)
    artifacts = ResumeGenerationResponse.model_validate(
        generate_resume_artifacts(
            request.candidate_profile,
            request.job_posting,
            analyze_match_basic(request),
        )
    )
    draft_with_links_only_in_header = artifacts.resume_draft.model_copy(
        update={
            "header": artifacts.resume_draft.header.model_copy(
                update={
                    "links": [
                        "https://linkedin.com/in/example-from-draft",
                        "https://github.com/example-from-draft",
                    ]
                }
            )
        }
    )

    linkedin, github = resume_typst_service._resolve_supported_links(  # noqa: SLF001
        draft_with_links_only_in_header,
        request.candidate_profile,
    )

    assert linkedin == "https://linkedin.com/in/example-from-draft"
    assert github == "https://github.com/example-from-draft"


def test_resolve_supported_links_returns_none_when_profile_and_draft_both_lack_links() -> None:
    payload_path = Path("data/match_analysis_test.json")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["candidate_profile"]["personal_info"]["linkedin_url"] = None
    payload["candidate_profile"]["personal_info"]["github_url"] = None
    request = MatchAnalysisRequest.model_validate(payload)
    artifacts = ResumeGenerationResponse.model_validate(
        generate_resume_artifacts(
            request.candidate_profile,
            request.job_posting,
            analyze_match_basic(request),
        )
    )
    draft_without_links = artifacts.resume_draft.model_copy(
        update={
            "header": artifacts.resume_draft.header.model_copy(update={"links": []})
        }
    )

    linkedin, github = resume_typst_service._resolve_supported_links(  # noqa: SLF001
        draft_without_links,
        request.candidate_profile,
    )

    assert linkedin is None
    assert github is None
