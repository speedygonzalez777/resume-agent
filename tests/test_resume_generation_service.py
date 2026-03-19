import json
from pathlib import Path

from app.models.analysis import MatchAnalysisRequest
from app.services.match_service import analyze_match_basic
from app.services.resume_generation_service import generate_resume_artifacts

_MATCH_PAYLOAD_FIXTURE = Path("data/match_analysis_test.json")


def _load_request() -> MatchAnalysisRequest:
    """Load the reusable match-analysis fixture as a validated request model."""
    payload = json.loads(_MATCH_PAYLOAD_FIXTURE.read_text(encoding="utf-8"))
    return MatchAnalysisRequest.model_validate(payload)


def test_generate_resume_artifacts_builds_structured_cv_and_report() -> None:
    request = _load_request()
    match_result = analyze_match_basic(request)

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )

    resume_draft = artifacts["resume_draft"]
    change_report = artifacts["change_report"]

    assert resume_draft.header.full_name == request.candidate_profile.personal_info.full_name
    assert resume_draft.header.professional_headline == request.job_posting.title
    assert "Most relevant for the" in (resume_draft.professional_summary or "")
    assert "PLC" in resume_draft.selected_skills
    assert "TIA Portal" in resume_draft.selected_skills
    assert [entry.source_experience_id for entry in resume_draft.selected_experience_entries] == ["exp_001"]
    assert resume_draft.selected_education_entries
    assert resume_draft.selected_language_entries
    assert resume_draft.selected_certificate_entries

    assert any(item.startswith("Used experience:") for item in change_report.added_elements)
    assert (
        "No unsupported experience, technology, certificate or years of experience were added."
        in change_report.blocked_items
    )
