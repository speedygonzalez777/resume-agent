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
from app.services.openai_candidate_profile_understanding_service import (
    CandidateProfileUnderstanding,
    CandidateSourceSignal,
)
from app.services.openai_requirement_candidate_match_service import (
    RequirementCandidateMatchOutput,
)
from app.services.openai_requirement_priority_service import OpenAIRequirementPriorityItem
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


def _build_requirement_priority_item(
    requirement_id: str,
    priority_tier: str,
    *,
    confidence: str = "high",
    reasoning_note: str | None = None,
) -> OpenAIRequirementPriorityItem:
    """Build a compact AI requirement-priority item used in resume-generation tests."""

    return OpenAIRequirementPriorityItem(
        requirement_id=requirement_id,
        priority_tier=priority_tier,
        confidence=confidence,
        reasoning_note=reasoning_note or f"{requirement_id} is {priority_tier}.",
    )


def _build_candidate_profile_understanding() -> CandidateProfileUnderstanding:
    return CandidateProfileUnderstanding(
        source_signals=[
            CandidateSourceSignal(
                source_type="project",
                source_id="proj_001",
                source_title="Robotics Demo Platform",
                signal_label="control systems",
                signal_kind="technical_competency",
                evidence_class="hard_evidence",
                normalized_terms=["control systems"],
                supporting_snippets=["control systems"],
                confidence="high",
                reasoning_note="The project explicitly references control systems.",
            )
        ],
        profile_signals=[],
        language_normalizations=[],
        thematic_alignments=[],
    )


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
    assert resume_draft.header.professional_headline is None
    assert resume_draft.target_job_title == request.job_posting.title
    assert resume_draft.target_company_name == request.job_posting.company_name
    assert resume_draft.professional_summary == request.candidate_profile.professional_summary_base
    assert "PLC" in resume_draft.selected_skills
    assert "TIA Portal" not in resume_draft.selected_skills
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
    assert parsed_response.generation_debug is not None
    assert parsed_response.generation_debug["selected_skills"][0]["label"] == "PLC"
    assert parsed_response.generation_debug["professional_summary"]["summary_focus_terms"] == ["PLC"]
    assert sorted(change_report.detected_keywords) == sorted(
        [
            "PLC",
            "automation",
            "technical documentation",
            "commissioning",
            "English",
            "communication",
        ]
    )
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
            "electrical systems, embedded projects and technical documentation."
        )
    )
    assert resume_draft.header.professional_headline is None
    assert resume_draft.selected_skills == ["PLC"]
    assert resume_draft.selected_keywords == ["PLC"]
    assert resume_draft.selected_experience_entries[0].source_experience_id == "exp_001"
    assert resume_draft.selected_experience_entries[0].source_highlights == [
        "Assisted in PLC-related automation tasks",
    ]
    assert resume_draft.selected_experience_entries[0].bullet_points != [
        "Built 15 PLC systems with Python and SCADA leadership.",
    ]
    assert any("safer grounded summary" in note for note in parsed_response.generation_notes)
    assert any("source-grounded fallback content" in note for note in parsed_response.generation_notes)
    assert parsed_response.generation_debug is not None
    assert parsed_response.generation_debug["professional_summary"]["summary_focus_terms"] == ["PLC"]
    assert "Unverified technologies were omitted instead of guessed." in change_report.blocked_items
    assert "Deemphasized less relevant profile sections with weak keyword overlap." in change_report.omitted_elements
    assert sorted(change_report.detected_keywords) == sorted(
        [
            "PLC",
            "automation",
            "technical documentation",
            "commissioning",
            "English",
            "communication",
        ]
    )
    assert sorted(change_report.used_keywords) == sorted(resume_draft.keyword_usage)


def test_generate_resume_artifacts_uses_interest_entries_as_summary_grounding_context(monkeypatch) -> None:
    request = _load_request()
    request.candidate_profile.interest_entries = ["industrial automation", "human-centered design"]
    match_result = analyze_match_basic(request)

    monkeypatch.setattr(
        "app.services.resume_generation_service.generate_resume_tailoring_with_openai",
        lambda *_args, **_kwargs: OpenAIResumeTailoringOutput(
            fit_summary="Strong fit for PLC-oriented automation work with declared interest in industrial automation.",
            professional_summary="Automation and robotics student with a strong interest in industrial automation.",
            selected_skills=["PLC", "TIA Portal"],
            selected_keywords=["PLC", "commissioning"],
            selected_experience_entries=[
                {
                    "source_experience_id": "exp_001",
                    "tailored_bullets": [
                        "Assisted in PLC-related automation tasks",
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

    assert parsed_response.resume_draft.professional_summary == (
        "Automation and robotics student with a strong interest in industrial automation."
    )
    assert "industrial automation" not in parsed_response.resume_draft.selected_skills
    assert parsed_response.resume_draft.fit_summary == (
        "Strong fit for PLC-oriented automation work with declared interest in industrial automation."
    )



def test_generate_resume_artifacts_carries_soft_skills_interests_and_project_link_into_resume_draft(
    monkeypatch,
) -> None:
    request = _load_request()
    request.candidate_profile.soft_skill_entries = ["communication", "teamwork"]
    request.candidate_profile.interest_entries = ["industrial automation", "robotics"]
    match_result = analyze_match_basic(request)

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr(
        "app.services.resume_generation_service.get_requirement_priority_lookup",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.get_candidate_profile_understanding",
        lambda *_args, **_kwargs: CandidateProfileUnderstanding(),
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.generate_resume_tailoring_with_openai",
        lambda *_args, **_kwargs: OpenAIResumeTailoringOutput(
            fit_summary="Strong fit for PLC-oriented automation work.",
            professional_summary="Automation and robotics student with grounded PLC exposure.",
            selected_skills=["PLC"],
            selected_keywords=["PLC"],
            selected_experience_entries=[],
            selected_project_entries=[
                {
                    "source_project_id": "proj_001",
                    "tailored_bullets": [
                        "Built a functional robotic prototype",
                    ],
                    "highlighted_keywords": ["PLC"],
                    "relevance_note": "Project supports automation and robotics profile.",
                    "source_highlights": [
                        "Built a functional robotic prototype",
                    ],
                }
            ],
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

    assert parsed_response.resume_draft.selected_soft_skill_entries == ["communication", "teamwork"]
    assert parsed_response.resume_draft.selected_interest_entries == ["industrial automation", "robotics"]
    assert len(parsed_response.resume_draft.selected_project_entries) == 1
    assert parsed_response.resume_draft.selected_project_entries[0].source_project_id == "proj_001"
    assert (
        parsed_response.resume_draft.selected_project_entries[0].link
        == "https://github.com/alex-example/robotics-demo"
    )


def test_generate_resume_artifacts_adds_declared_interest_note_to_fallback_fit_summary(monkeypatch) -> None:
    request = _load_request()
    request.candidate_profile.interest_entries = ["industrial automation", "human-centered design"]
    match_result = analyze_match_basic(request)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    assert "Declared interest alignment: industrial automation." in parsed_response.resume_draft.fit_summary
    assert "industrial automation" not in parsed_response.resume_draft.selected_skills


def test_resume_generation_response_accepts_legacy_resume_draft_without_new_fields() -> None:
    legacy_response = ResumeGenerationResponse.model_validate(
        {
            "resume_draft": {
                "header": {
                    "full_name": "Jan Kowalski",
                    "professional_headline": None,
                    "email": "jan@example.com",
                    "phone": "+48 555 111 222",
                    "location": "Krakow",
                    "links": ["https://linkedin.com/in/jankowalski"],
                },
                "target_job_title": "Automation Engineer",
                "target_company_name": "Example Automation",
                "fit_summary": "Strong fit for PLC-heavy automation role.",
                "professional_summary": "Automation engineer focused on PLC commissioning.",
                "selected_skills": ["PLC"],
                "selected_experience_entries": [],
                "selected_project_entries": [
                    {
                        "source_project_id": "proj_001",
                        "project_name": "Robotics Demo Platform",
                        "role": "Designer and developer",
                        "bullet_points": ["Built a functional robotic prototype"],
                        "highlighted_keywords": ["PLC"],
                        "relevance_note": None,
                        "source_highlights": ["Built a functional robotic prototype"],
                    }
                ],
                "selected_education_entries": [],
                "selected_language_entries": [],
                "selected_certificate_entries": [],
                "selected_keywords": ["PLC"],
                "keyword_usage": ["PLC"],
            },
            "change_report": {
                "added_elements": [],
                "emphasized_elements": [],
                "omitted_elements": [],
                "omission_reasons": [],
                "detected_keywords": ["PLC"],
                "used_keywords": ["PLC"],
                "unused_keywords": [],
                "blocked_items": [],
                "warnings": [],
            },
            "generation_mode": "rule_based_fallback",
            "match_result_source": "provided",
            "fallback_reason": None,
            "generation_notes": [],
            "offer_signal_debug": None,
            "generation_debug": None,
            "resume_draft_record_id": None,
            "resume_draft_saved_at": None,
            "persistence_warning": None,
        }
    )

    assert legacy_response.resume_draft.selected_soft_skill_entries == []
    assert legacy_response.resume_draft.selected_interest_entries == []
    assert legacy_response.resume_draft.selected_project_entries[0].link is None


def test_generate_resume_artifacts_exposes_offer_signal_debug_breakdown(monkeypatch) -> None:
    request = _load_request()
    request.job_posting.keywords = [
        "Python",
        "Java",
        "SQL",
        "studia",
        "kierunki techniczne",
        "30 godzin tygodniowo",
        "6 miesięcy",
        "hybrydowa",
        "umowa zlecenie",
        "staż",
        "znajomość",
    ]
    match_result = analyze_match_basic(request)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    debug_breakdown = parsed_response.offer_signal_debug

    assert debug_breakdown is not None
    assert {"Python", "Java", "SQL"} <= set(debug_breakdown["generation_eligible_offer_terms"])
    assert "studia" not in debug_breakdown["generation_eligible_offer_terms"]
    assert "30 godzin tygodniowo" not in debug_breakdown["generation_eligible_offer_terms"]
    assert "Internship" not in debug_breakdown["generation_eligible_offer_terms"]
    assert {item["normalized_label"] for item in debug_breakdown["manual_confirmation_items"]} == {
        "30 godzin tygodniowo",
        "6 miesiecy",
    }
    assert {item["normalized_label"] for item in debug_breakdown["role_alignment_signals"]} == {
        "internship",
    }
    assert {item["normalized_label"] for item in debug_breakdown["suppressed_terms"]} == {
        "znajomosc",
    }


def test_generate_resume_artifacts_filters_noisy_detected_and_highlighted_keywords(monkeypatch) -> None:
    request = _load_request()
    request.job_posting.keywords = [
        "PLC",
        "sta",
        "program",
        "support",
        "projects",
        "engineering",
        "mile widziany",
        "znajomość",
        "frameworki",
        "min. 1 rok",
        "AI",
        "SQL",
    ]
    match_result = analyze_match_basic(request)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    detected_keywords = parsed_response.change_report.detected_keywords
    highlighted_keywords = [
        keyword
        for entry in parsed_response.resume_draft.selected_experience_entries
        for keyword in entry.highlighted_keywords
    ]

    assert "sta" not in detected_keywords
    assert "program" not in detected_keywords
    assert "support" not in detected_keywords
    assert "projects" not in detected_keywords
    assert "engineering" not in detected_keywords
    assert "mile widziany" not in detected_keywords
    assert "znajomość" not in detected_keywords
    assert "frameworki" not in detected_keywords
    assert "min. 1 rok" not in detected_keywords
    assert "AI" in detected_keywords
    assert "PLC" in detected_keywords
    assert "SQL" in detected_keywords
    assert "sta" not in highlighted_keywords
    assert "program" not in highlighted_keywords
    assert "support" not in highlighted_keywords
    assert "projects" not in highlighted_keywords
    assert "engineering" not in highlighted_keywords
    assert "mile widziany" not in highlighted_keywords
    assert "frameworki" not in highlighted_keywords
    assert "PLC" in highlighted_keywords


def test_generate_resume_artifacts_caps_reportable_keyword_universe(monkeypatch) -> None:
    request = _load_request()
    request.job_posting.keywords = [
        "PLC",
        "AI",
        "SQL",
        "commissioning",
        "technical documentation",
        "automation",
        "robotics",
        "testing",
        "SCADA",
        "HMI",
        "API",
        "MES",
        "support",
        "projects",
        "engineering",
    ]
    match_result = analyze_match_basic(request)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    detected_keywords = parsed_response.change_report.detected_keywords
    highlighted_keywords = [
        keyword
        for entry in parsed_response.resume_draft.selected_experience_entries
        for keyword in entry.highlighted_keywords
    ]

    assert detected_keywords == [
        "PLC",
        "automation",
        "English",
        "communication",
        "AI",
        "SQL",
        "commissioning",
        "technical documentation",
        "robotics",
        "testing",
        "SCADA",
        "HMI",
    ]
    assert len(detected_keywords) == 12
    assert all(keyword in detected_keywords for keyword in highlighted_keywords)


def test_generate_resume_artifacts_uses_requirement_prioritization_to_order_detected_keywords(
    monkeypatch,
) -> None:
    payload = json.loads(_MATCH_PAYLOAD_FIXTURE.read_text(encoding="utf-8"))
    payload["job_posting"]["requirements"] = [
        {
            "id": "req_fast_paced",
            "text": "Experience in a fast-paced environment",
            "category": "soft_skill",
            "requirement_type": "nice_to_have",
            "importance": "low",
            "extracted_keywords": ["fast-paced"],
        },
        {
            "id": "req_plc",
            "text": "Basic knowledge of PLC systems",
            "category": "technology",
            "requirement_type": "must_have",
            "importance": "high",
            "extracted_keywords": ["PLC"],
        },
        {
            "id": "req_interest",
            "text": "Interest in AI topics",
            "category": "soft_skill",
            "requirement_type": "nice_to_have",
            "importance": "medium",
            "extracted_keywords": ["AI"],
        },
        {
            "id": "req_communication",
            "text": "Strong communication skills",
            "category": "soft_skill",
            "requirement_type": "nice_to_have",
            "importance": "medium",
            "extracted_keywords": ["communication"],
        },
    ]
    payload["job_posting"]["keywords"] = ["communication", "fast-paced", "PLC", "AI"]
    request = MatchAnalysisRequest.model_validate(payload)
    request.candidate_profile.soft_skill_entries = ["communication"]
    priority_lookup = {
        "req_plc": _build_requirement_priority_item(
            "req_plc",
            "core",
            reasoning_note="PLC defines the role's technical core.",
        ),
        "req_interest": _build_requirement_priority_item(
            "req_interest",
            "supporting",
            reasoning_note="Interest in AI is relevant, but secondary to PLC capability.",
        ),
        "req_communication": _build_requirement_priority_item(
            "req_communication",
            "supporting",
            reasoning_note="Communication matters, but it does not define the role as strongly as PLC work.",
        ),
        "req_fast_paced": _build_requirement_priority_item(
            "req_fast_paced",
            "low_signal",
            reasoning_note="Fast-paced environment is weakly differentiating.",
        ),
    }
    match_result = analyze_match_basic(request, requirement_priority_lookup=priority_lookup)
    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr(
        "app.services.resume_generation_service.get_requirement_priority_lookup",
        lambda *_args, **_kwargs: priority_lookup,
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.get_candidate_profile_understanding",
        lambda *_args, **_kwargs: CandidateProfileUnderstanding(),
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.generate_resume_tailoring_with_openai",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ResumeTailoringOpenAIError(
                "OpenAI resume tailoring failed. Falling back to deterministic resume generation.",
                fallback_reason=ResumeFallbackReason.OPENAI_ERROR,
            )
        ),
    )

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        match_result,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    assert parsed_response.change_report.detected_keywords == [
        "PLC",
        "AI",
        "communication",
    ]


def test_generate_resume_artifacts_filters_ai_highlighted_keywords_to_grounded_reportable_terms(
    monkeypatch,
) -> None:
    request = _load_request()
    request.job_posting.title = "Automation Systems Engineer"
    request.job_posting.role_summary = "Build PLC systems and engineer automation workflows."
    match_result = analyze_match_basic(request)

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr(
        "app.services.resume_generation_service.get_requirement_priority_lookup",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.get_candidate_profile_understanding",
        lambda *_args, **_kwargs: CandidateProfileUnderstanding(),
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.generate_resume_tailoring_with_openai",
        lambda *_args, **_kwargs: OpenAIResumeTailoringOutput(
            fit_summary="Strong fit for PLC-oriented automation work.",
            professional_summary="Automation and robotics student with PLC exposure.",
            selected_skills=["PLC", "TIA Portal"],
            selected_keywords=["PLC"],
            selected_experience_entries=[
                {
                    "source_experience_id": "exp_001",
                    "tailored_bullets": [
                        "Assisted in PLC-related automation tasks",
                    ],
                    "highlighted_keywords": ["PLC", "engineer", "system", "dev"],
                    "relevance_note": "Most relevant PLC experience.",
                    "source_highlights": [
                        "Assisted in PLC-related automation tasks",
                    ],
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

    assert parsed_response.resume_draft.selected_experience_entries[0].highlighted_keywords == ["PLC"]
    assert "engineer" not in parsed_response.change_report.used_keywords
    assert "system" not in parsed_response.change_report.used_keywords


def test_generate_resume_artifacts_computes_candidate_understanding_once_and_reuses_it(monkeypatch) -> None:
    request = _load_request()
    understanding = _build_candidate_profile_understanding()
    captured_understanding_ids: list[int] = []

    def _fake_analyze_match_basic(*args, **kwargs):
        captured_understanding_ids.append(id(kwargs["candidate_profile_understanding"]))
        return analyze_match_basic(
            args[0],
            requirement_priority_lookup=kwargs.get("requirement_priority_lookup"),
            candidate_profile_understanding=kwargs.get("candidate_profile_understanding"),
        )

    def _raise_openai_error(*args, **kwargs):
        captured_understanding_ids.append(id(kwargs["candidate_profile_understanding"]))
        raise ResumeTailoringOpenAIError(
            "OpenAI resume tailoring failed. Falling back to deterministic resume generation.",
            fallback_reason=ResumeFallbackReason.OPENAI_ERROR,
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr(
        "app.services.resume_generation_service.get_requirement_priority_lookup",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.get_candidate_profile_understanding",
        lambda *_args, **_kwargs: understanding,
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.analyze_match_basic",
        _fake_analyze_match_basic,
    )
    monkeypatch.setattr(
        "app.services.match_service.evaluate_requirement_candidate_block_with_openai",
        lambda *_args, **_kwargs: RequirementCandidateMatchOutput(),
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.generate_resume_tailoring_with_openai",
        _raise_openai_error,
    )

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        None,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    assert parsed_response.match_result_source is ResumeMatchResultSource.COMPUTED
    assert parsed_response.generation_mode is ResumeGenerationMode.RULE_BASED_FALLBACK
    assert len(captured_understanding_ids) == 2
    assert captured_understanding_ids[0] == captured_understanding_ids[1] == id(understanding)


def test_generate_resume_artifacts_reuses_supplied_semantic_context_without_recomputing(monkeypatch) -> None:
    request = _load_request()
    match_result = analyze_match_basic(request)
    understanding = _build_candidate_profile_understanding()
    priority_lookup = {
        "req_001": _build_requirement_priority_item("req_001", "core"),
        "req_002": _build_requirement_priority_item("req_002", "supporting"),
    }

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr(
        "app.services.resume_generation_service.get_requirement_priority_lookup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("priority recompute should not happen")),
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.get_candidate_profile_understanding",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("profile understanding recompute should not happen")),
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.generate_resume_tailoring_with_openai",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ResumeTailoringOpenAIError(
                "OpenAI resume tailoring failed. Falling back to deterministic resume generation.",
                fallback_reason=ResumeFallbackReason.OPENAI_ERROR,
            )
        ),
    )

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        match_result,
        requirement_priority_lookup=priority_lookup,
        candidate_profile_understanding=understanding,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    assert parsed_response.generation_mode is ResumeGenerationMode.RULE_BASED_FALLBACK
    assert parsed_response.change_report.detected_keywords


def test_generate_resume_artifacts_reuses_matching_handoff_without_recomputing(monkeypatch) -> None:
    request = _load_request()
    match_result = analyze_match_basic(request)
    understanding = _build_candidate_profile_understanding()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setattr(
        "app.services.resume_generation_service.get_requirement_priority_lookup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("priority recompute should not happen")
        ),
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.get_candidate_profile_understanding",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("profile understanding recompute should not happen")
        ),
    )
    monkeypatch.setattr(
        "app.services.resume_generation_service.generate_resume_tailoring_with_openai",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ResumeTailoringOpenAIError(
                "OpenAI resume tailoring failed. Falling back to deterministic resume generation.",
                fallback_reason=ResumeFallbackReason.OPENAI_ERROR,
            )
        ),
    )

    artifacts = generate_resume_artifacts(
        request.candidate_profile,
        request.job_posting,
        match_result,
        requirement_priority_lookup={},
        candidate_profile_understanding=understanding,
        requirement_priority_lookup_provided=True,
        candidate_profile_understanding_provided=True,
        matching_handoff_supplied=True,
    )
    parsed_response = ResumeGenerationResponse.model_validate(artifacts)

    assert parsed_response.generation_mode is ResumeGenerationMode.RULE_BASED_FALLBACK
    assert parsed_response.generation_debug is not None
    assert parsed_response.generation_debug["semantic_handoff"] == {
        "matching_handoff_supplied": True,
        "reused_sidecars": [
            "requirement_priority_lookup",
            "candidate_profile_understanding",
        ],
        "locally_computed_sidecars": [],
    }


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
