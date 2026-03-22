import json
from pathlib import Path

from app.api.routes_resume import ResumeGenerationResponse
from app.models.analysis import MatchAnalysisRequest
from app.models.resume import (
    ResumeFallbackReason,
    ResumeGenerationMode,
    ResumeMatchResultSource,
)
from app.services.match_service import analyze_match_basic
from app.services.openai_resume_tailoring_service import (
    OpenAIResumeTailoringOutput,
    ResumeTailoringOpenAIError,
)
from app.services.resume_generation_service import generate_resume_artifacts

_MATCH_PAYLOAD_FIXTURE = Path("data/match_analysis_test.json")


def _load_request() -> MatchAnalysisRequest:
    """Load the reusable match-analysis fixture as a validated request model."""
    payload = json.loads(_MATCH_PAYLOAD_FIXTURE.read_text(encoding="utf-8"))
    return MatchAnalysisRequest.model_validate(payload)


def test_generate_resume_artifacts_falls_back_when_openai_is_unavailable(monkeypatch) -> None:
    request = _load_request()
    match_result = analyze_match_basic(request)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    resume_draft = parsed_response.resume_draft
    change_report = parsed_response.change_report

    assert parsed_response.generation_mode is ResumeGenerationMode.RULE_BASED_FALLBACK
    assert parsed_response.match_result_source is ResumeMatchResultSource.PROVIDED
    assert parsed_response.fallback_reason is ResumeFallbackReason.MISSING_API_KEY
    assert parsed_response.generation_notes
    assert resume_draft.header.full_name == request.candidate_profile.personal_info.full_name
    assert resume_draft.header.professional_headline == request.job_posting.title
    assert resume_draft.target_job_title == request.job_posting.title
    assert resume_draft.target_company_name == request.job_posting.company_name
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
    assert any("falling back to deterministic resume generation" in item.lower() for item in change_report.warnings)
    assert change_report.detected_keywords == [
        "PLC",
        "automation",
        "technical documentation",
        "commissioning",
        "English",
        "communication",
    ]
    assert change_report.used_keywords == resume_draft.keyword_usage


def test_generate_resume_artifacts_uses_ai_output_when_available_with_conservative_guardrails(
    monkeypatch,
) -> None:
    request = _load_request()
    match_result = analyze_match_basic(request)

    monkeypatch.setattr(
        "app.services.resume_generation_service.generate_resume_tailoring_with_openai",
        lambda *_args, **_kwargs: OpenAIResumeTailoringOutput(
            fit_summary="Strong fit for PLC-oriented automation work with a few gaps to review.",
            professional_summary="Senior PLC architect with 10 years of Python leadership experience.",
            selected_skills=["PLC", "TIA Portal", "Invented Skill"],
            selected_keywords=["PLC", "commissioning", "Invented Keyword"],
            selected_experience_entries=[
                {
                    "source_experience_id": "exp_001",
                    "tailored_bullets": [
                        "Built 15 PLC systems with Python and SCADA leadership.",
                    ],
                    "highlighted_keywords": ["PLC", "commissioning"],
                    "relevance_note": "Most relevant industrial automation experience.",
                    "source_highlights": [
                        "Assisted in PLC-related automation tasks",
                    ],
                }
            ],
            selected_project_entries=[],
            selected_education_entries=[],
            selected_language_entries=[],
            selected_certificate_entries=[],
            warnings=["Match is not perfect, so the draft stays conservative."],
            truthfulness_notes=["Unverified technologies were omitted instead of guessed."],
            omitted_or_deemphasized_items=["Deemphasized less relevant profile sections with weak keyword overlap."],
        ),
    )

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    resume_draft = parsed_response.resume_draft
    change_report = parsed_response.change_report

    assert parsed_response.generation_mode is ResumeGenerationMode.OPENAI_STRUCTURED
    assert parsed_response.match_result_source is ResumeMatchResultSource.PROVIDED
    assert parsed_response.fallback_reason is None
    assert (
        resume_draft.professional_summary
        == (
            "Automation and robotics student with hands-on experience in industrial control, "
            "electrical systems, embedded projects and technical documentation. "
            "Most relevant for the Junior Automation Engineer role: PLC, TIA Portal."
        )
    )
    assert resume_draft.selected_skills == ["PLC", "TIA Portal"]
    assert resume_draft.selected_keywords == ["PLC", "commissioning"]
    assert resume_draft.selected_experience_entries[0].source_experience_id == "exp_001"
    assert resume_draft.selected_experience_entries[0].source_highlights == [
        "Assisted in PLC-related automation tasks",
    ]
    assert resume_draft.selected_experience_entries[0].bullet_points != [
        "Built 15 PLC systems with Python and SCADA leadership.",
    ]
    assert any("safer grounded summary" in note for note in parsed_response.generation_notes)
    assert any("source-grounded fallback content" in note for note in parsed_response.generation_notes)
    assert "Unverified technologies were omitted instead of guessed." in change_report.blocked_items
    assert "Deemphasized less relevant profile sections with weak keyword overlap." in change_report.omitted_elements
    assert change_report.detected_keywords == [
        "PLC",
        "automation",
        "technical documentation",
        "commissioning",
        "English",
        "communication",
    ]
    assert sorted(change_report.used_keywords) == sorted(resume_draft.keyword_usage)


def test_generate_resume_artifacts_falls_back_when_openai_errors(monkeypatch) -> None:
    request = _load_request()
    match_result = analyze_match_basic(request)

    def _raise_openai_error(*_args, **_kwargs):
        raise ResumeTailoringOpenAIError(
            "OpenAI resume tailoring failed. Falling back to deterministic resume generation.",
            fallback_reason=ResumeFallbackReason.OPENAI_ERROR,
        )

    monkeypatch.setattr(
        "app.services.resume_generation_service.generate_resume_tailoring_with_openai",
        _raise_openai_error,
    )

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    assert parsed_response.generation_mode is ResumeGenerationMode.RULE_BASED_FALLBACK
    assert parsed_response.fallback_reason is ResumeFallbackReason.OPENAI_ERROR
    assert any("OpenAI resume tailoring failed" in item for item in parsed_response.generation_notes)
    assert any("OpenAI resume tailoring failed" in item for item in parsed_response.change_report.warnings)


def test_generate_resume_artifacts_computes_match_result_when_not_supplied(monkeypatch) -> None:
    request = _load_request()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        None,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    assert parsed_response.generation_mode is ResumeGenerationMode.RULE_BASED_FALLBACK
    assert parsed_response.match_result_source is ResumeMatchResultSource.COMPUTED
    assert parsed_response.fallback_reason is ResumeFallbackReason.MISSING_API_KEY


def test_generate_resume_artifacts_falls_back_when_ai_output_loses_all_grounded_evidence(
    monkeypatch,
) -> None:
    request = _load_request()
    match_result = analyze_match_basic(request)

    monkeypatch.setattr(
        "app.services.resume_generation_service.generate_resume_tailoring_with_openai",
        lambda *_args, **_kwargs: OpenAIResumeTailoringOutput(
            fit_summary="Strong fit.",
            professional_summary="Groundless summary.",
            selected_skills=["PLC"],
            selected_keywords=["PLC"],
            selected_experience_entries=[
                {
                    "source_experience_id": "missing-exp",
                    "tailored_bullets": ["Invented bullet."],
                    "highlighted_keywords": ["PLC"],
                    "source_highlights": ["Invented highlight."],
                }
            ],
            selected_project_entries=[],
            selected_education_entries=[],
            selected_language_entries=[],
            selected_certificate_entries=[],
            warnings=[],
            truthfulness_notes=[],
            omitted_or_deemphasized_items=[],
        ),
    )

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    assert parsed_response.generation_mode is ResumeGenerationMode.RULE_BASED_FALLBACK
    assert parsed_response.fallback_reason is ResumeFallbackReason.INVALID_AI_OUTPUT
    assert any("empty or unusable resume draft" in note for note in parsed_response.generation_notes)
