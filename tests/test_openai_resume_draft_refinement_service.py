from __future__ import annotations

import json

from app.models.resume import (
    ResumeDraft,
    ResumeDraftRefinementGuidance,
    ResumeDraftRefinementPatch,
)
from app.services.openai_resume_draft_refinement_service import (
    generate_resume_draft_refinement_patch_with_openai,
)
from app.services.resume_draft_refinement_service import (
    ResumeDraftRefinementMergeError,
    apply_resume_draft_refinement_patch,
)


def test_generate_resume_draft_refinement_patch_with_openai_uses_resume_draft_only_input(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_patch = ResumeDraftRefinementPatch(
        header={"professional_headline": "PLC Automation Engineer"},
        professional_summary="Automation engineer focused on PLC commissioning.",
        selected_skills=["PLC", "Python"],
        selected_keywords=["PLC", "commissioning"],
        keyword_usage=["PLC", "commissioning"],
        selected_experience_entries=[
            {
                "source_experience_id": "exp_1",
                "bullet_points": ["Commissioned PLC lines for production plants."],
                "highlighted_keywords": ["PLC"],
            }
        ],
    )

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_patch})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_RESUME_DRAFT_REFINEMENT_MODEL", "gpt-5-mini")
    monkeypatch.setattr(
        "app.services.openai_resume_draft_refinement_service.OpenAI",
        FakeOpenAI,
    )

    result = generate_resume_draft_refinement_patch_with_openai(
        _build_resume_draft(),
        ResumeDraftRefinementGuidance(
            must_include_terms=["PLC"],
            avoid_or_deemphasize_terms=["SAP"],
            forbidden_claims_or_phrases=["expert"],
            skills_allowlist=["PLC", "Python"],
            additional_instructions="Keep the language concise.",
        ),
    )

    assert result == expected_patch
    assert captured_kwargs["model"] == "gpt-5-mini"
    assert captured_kwargs["text_format"] is ResumeDraftRefinementPatch
    payload = str(captured_kwargs["input"])
    assert '"base_resume_draft"' in payload
    assert '"guidance"' in payload
    assert '"candidate_profile"' not in payload
    assert '"job_posting"' not in payload
    assert '"match_result"' not in payload
    assert '"matching_handoff"' not in payload


def test_apply_resume_draft_refinement_patch_only_updates_allowed_fields() -> None:
    base_draft = _build_resume_draft()
    refinement_patch = ResumeDraftRefinementPatch(
        header={"professional_headline": "PLC Automation Engineer"},
        professional_summary="Automation engineer focused on PLC commissioning.",
        selected_skills=["PLC", "Python"],
        selected_keywords=["PLC", "commissioning"],
        keyword_usage=["PLC", "commissioning"],
        selected_experience_entries=[
            {
                "source_experience_id": "exp_1",
                "bullet_points": ["Commissioned PLC lines for production plants."],
                "highlighted_keywords": ["PLC"],
            }
        ],
        selected_project_entries=[
            {
                "source_project_id": "proj_1",
                "bullet_points": ["Built internal tooling for PLC deployment support."],
                "highlighted_keywords": ["PLC", "tooling"],
            }
        ],
    )

    refined_draft = apply_resume_draft_refinement_patch(base_draft, refinement_patch)

    assert refined_draft.header.professional_headline == "PLC Automation Engineer"
    assert refined_draft.professional_summary == "Automation engineer focused on PLC commissioning."
    assert refined_draft.selected_skills == ["PLC", "Python"]
    assert refined_draft.selected_keywords == ["PLC", "commissioning"]
    assert refined_draft.keyword_usage == ["PLC", "commissioning"]
    assert refined_draft.selected_experience_entries[0].bullet_points == [
        "Commissioned PLC lines for production plants."
    ]
    assert refined_draft.selected_experience_entries[0].highlighted_keywords == ["PLC"]
    assert refined_draft.selected_project_entries[0].bullet_points == [
        "Built internal tooling for PLC deployment support."
    ]
    assert refined_draft.selected_project_entries[0].highlighted_keywords == ["PLC", "tooling"]
    assert refined_draft.header.full_name == "Jan Kowalski"
    assert refined_draft.selected_experience_entries[0].company_name == "Factory Systems"
    assert refined_draft.selected_project_entries[0].project_name == "MES Connector"
    assert refined_draft.selected_education_entries == ["BSc Automation and Robotics"]


def test_apply_resume_draft_refinement_patch_preserves_unpatched_entries_and_base_draft() -> None:
    base_draft = _build_resume_draft()
    base_draft.selected_experience_entries.append(
        base_draft.selected_experience_entries[0].model_copy(
            update={
                "source_experience_id": "exp_2",
                "company_name": "Second Factory",
                "bullet_points": ["Maintained test benches for automation systems."],
                "highlighted_keywords": ["testing"],
            }
        )
    )
    base_draft.selected_project_entries.append(
        base_draft.selected_project_entries[0].model_copy(
            update={
                "source_project_id": "proj_2",
                "project_name": "Robot Cell",
                "bullet_points": ["Prepared test scripts for cell validation."],
                "highlighted_keywords": ["validation"],
            }
        )
    )

    refinement_patch = ResumeDraftRefinementPatch(
        selected_experience_entries=[
            {
                "source_experience_id": "exp_1",
                "bullet_points": ["Commissioned PLC lines and prepared technical documentation."],
                "highlighted_keywords": ["PLC", "documentation"],
            }
        ],
        selected_project_entries=[
            {
                "source_project_id": "proj_1",
                "bullet_points": ["Built internal PLC deployment tooling."],
                "highlighted_keywords": ["PLC", "tooling"],
            }
        ],
    )

    refined_draft = apply_resume_draft_refinement_patch(base_draft, refinement_patch)

    assert len(base_draft.selected_experience_entries) == 2
    assert len(refined_draft.selected_experience_entries) == 2
    assert len(base_draft.selected_project_entries) == 2
    assert len(refined_draft.selected_project_entries) == 2
    assert base_draft.selected_experience_entries[0].bullet_points == [
        "Commissioned PLC lines for production plants.",
        "Led SAP rollout for reporting standardization.",
    ]
    assert refined_draft.selected_experience_entries[0].bullet_points == [
        "Commissioned PLC lines and prepared technical documentation."
    ]
    assert refined_draft.selected_experience_entries[1].company_name == "Second Factory"
    assert refined_draft.selected_experience_entries[1].bullet_points == [
        "Maintained test benches for automation systems."
    ]
    assert refined_draft.selected_project_entries[1].project_name == "Robot Cell"
    assert refined_draft.selected_project_entries[1].highlighted_keywords == ["validation"]


def test_apply_resume_draft_refinement_patch_rejects_unknown_entry_ids() -> None:
    base_draft = _build_resume_draft()
    refinement_patch = ResumeDraftRefinementPatch(
        selected_experience_entries=[
            {
                "source_experience_id": "missing_exp",
                "bullet_points": ["Should fail."],
            }
        ]
    )

    try:
        apply_resume_draft_refinement_patch(base_draft, refinement_patch)
    except ResumeDraftRefinementMergeError as exc:
        assert "unknown source_experience_id" in str(exc)
    else:
        raise AssertionError("Expected ResumeDraftRefinementMergeError for unknown source_experience_id")


def _build_resume_draft() -> ResumeDraft:
    payload = {
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
                    "Led SAP rollout for reporting standardization.",
                ],
                "highlighted_keywords": ["PLC", "SAP"],
                "relevance_note": "Strong factory automation fit.",
                "source_highlights": ["PLC commissioning", "SAP reporting"],
            }
        ],
        "selected_project_entries": [
            {
                "source_project_id": "proj_1",
                "project_name": "MES Connector",
                "role": "Developer",
                "bullet_points": [
                    "Built internal tooling for SAP and PLC deployment support."
                ],
                "highlighted_keywords": ["SAP", "PLC"],
                "relevance_note": "Relevant internal automation tooling project.",
                "source_highlights": ["deployment support", "tooling"],
            }
        ],
        "selected_education_entries": ["BSc Automation and Robotics"],
        "selected_language_entries": ["English - B2"],
        "selected_certificate_entries": ["Siemens PLC Certificate"],
        "selected_keywords": ["PLC", "SAP"],
        "keyword_usage": ["PLC", "SAP"],
    }
    return ResumeDraft.model_validate(json.loads(json.dumps(payload)))
