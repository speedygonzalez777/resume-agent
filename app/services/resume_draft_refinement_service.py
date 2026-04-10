"""Technical patch merge for AI refinement of an existing ResumeDraft."""

from __future__ import annotations

from app.models.resume import (
    ResumeDraft,
    ResumeDraftRefinementGuidance,
    ResumeDraftRefinementPatch,
)
from app.services.openai_resume_draft_refinement_service import (
    generate_resume_draft_refinement_patch_with_openai,
)


class ResumeDraftRefinementMergeError(ValueError):
    """Raised when the structured refinement patch cannot be merged safely."""


def refine_resume_draft(
    resume_draft: ResumeDraft,
    guidance: ResumeDraftRefinementGuidance,
) -> dict[str, ResumeDraft | ResumeDraftRefinementPatch]:
    """Generate a structured OpenAI patch and merge it into the existing draft."""

    refinement_patch = generate_resume_draft_refinement_patch_with_openai(
        resume_draft,
        guidance,
    )
    refined_resume_draft = apply_resume_draft_refinement_patch(
        resume_draft,
        refinement_patch,
    )
    return {
        "refined_resume_draft": refined_resume_draft,
        "refinement_patch": refinement_patch,
    }


def apply_resume_draft_refinement_patch(
    resume_draft: ResumeDraft,
    refinement_patch: ResumeDraftRefinementPatch,
) -> ResumeDraft:
    """Apply an allowed structured patch to an existing ResumeDraft."""

    refined_resume_draft = resume_draft.model_copy(deep=True)

    if (
        refinement_patch.header is not None
        and refinement_patch.header.professional_headline is not None
    ):
        refined_resume_draft.header.professional_headline = (
            refinement_patch.header.professional_headline
        )

    if refinement_patch.professional_summary is not None:
        refined_resume_draft.professional_summary = refinement_patch.professional_summary

    if refinement_patch.selected_skills is not None:
        refined_resume_draft.selected_skills = list(refinement_patch.selected_skills)

    if refinement_patch.selected_keywords is not None:
        refined_resume_draft.selected_keywords = list(refinement_patch.selected_keywords)

    if refinement_patch.keyword_usage is not None:
        refined_resume_draft.keyword_usage = list(refinement_patch.keyword_usage)

    experience_entries_by_id = {
        entry.source_experience_id: entry
        for entry in refined_resume_draft.selected_experience_entries
    }
    project_entries_by_id = {
        entry.source_project_id: entry
        for entry in refined_resume_draft.selected_project_entries
    }

    _assert_unique_ids(
        [patch.source_experience_id for patch in refinement_patch.selected_experience_entries],
        "selected_experience_entries",
    )
    _assert_unique_ids(
        [patch.source_project_id for patch in refinement_patch.selected_project_entries],
        "selected_project_entries",
    )

    for entry_patch in refinement_patch.selected_experience_entries:
        target_entry = experience_entries_by_id.get(entry_patch.source_experience_id)
        if target_entry is None:
            raise ResumeDraftRefinementMergeError(
                "Refinement patch references an unknown source_experience_id."
            )

        if entry_patch.bullet_points is not None:
            target_entry.bullet_points = list(entry_patch.bullet_points)

        if entry_patch.highlighted_keywords is not None:
            target_entry.highlighted_keywords = list(entry_patch.highlighted_keywords)

    for entry_patch in refinement_patch.selected_project_entries:
        target_entry = project_entries_by_id.get(entry_patch.source_project_id)
        if target_entry is None:
            raise ResumeDraftRefinementMergeError(
                "Refinement patch references an unknown source_project_id."
            )

        if entry_patch.bullet_points is not None:
            target_entry.bullet_points = list(entry_patch.bullet_points)

        if entry_patch.highlighted_keywords is not None:
            target_entry.highlighted_keywords = list(entry_patch.highlighted_keywords)

    return refined_resume_draft


def _assert_unique_ids(values: list[str], field_name: str) -> None:
    """Reject duplicated patch IDs for one refinement field family."""

    if len(values) != len(set(values)):
        raise ResumeDraftRefinementMergeError(
            f"Refinement patch contains duplicated IDs in {field_name}."
        )
