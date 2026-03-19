"""Rule-based truthful-first generation of ResumeDraft and ChangeReport."""

from __future__ import annotations

import re
from typing import Iterable

from app.models.candidate import CandidateProfile, ExperienceEntry, ProjectEntry
from app.models.job import JobPosting, Requirement
from app.models.match import MatchResult, RequirementMatch
from app.models.resume import (
    ChangeReport,
    ResumeDraft,
    ResumeExperienceEntry,
    ResumeHeader,
    ResumeProjectEntry,
)

_IMPORTANCE_RELEVANCE = {
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}
_MATCH_RELEVANCE = {
    "matched": 1.0,
    "partial": 0.6,
    "missing": 0.0,
}
_MAX_SELECTED_EXPERIENCES = 4
_MAX_SELECTED_PROJECTS = 3
_MAX_SELECTED_SKILLS = 10
_MAX_SELECTED_EDUCATION = 2
_MAX_SELECTED_LANGUAGES = 3
_MAX_SELECTED_CERTIFICATES = 3


def _normalize(value: str | None) -> str:
    """Normalize a string for case-insensitive comparisons."""
    if not value:
        return ""
    return value.strip().lower()


def _append_unique(target: list[str], value: str | None) -> None:
    """Append a non-empty string to a list while preserving uniqueness."""
    normalized_value = value.strip() if value else ""
    if normalized_value and normalized_value not in target:
        target.append(normalized_value)


def _tokenize(text: str | None) -> list[str]:
    """Extract lightweight searchable tokens from free text."""
    if not text:
        return []
    return re.findall(r"[a-z0-9][a-z0-9+.#-]*", text.lower())


def _collect_job_keywords(job_posting: JobPosting) -> list[str]:
    """Collect explicit and inferred job keywords used for relevance checks."""
    keywords: list[str] = []

    for keyword in job_posting.keywords:
        _append_unique(keywords, _normalize(keyword))

    for requirement in job_posting.requirements:
        for keyword in requirement.extracted_keywords:
            _append_unique(keywords, _normalize(keyword))

    for token in _tokenize(job_posting.title):
        if len(token) >= 3:
            _append_unique(keywords, token)

    for token in _tokenize(job_posting.role_summary or ""):
        if len(token) >= 4:
            _append_unique(keywords, token)

    return keywords


def _build_requirement_lookup(job_posting: JobPosting) -> dict[str, Requirement]:
    """Map requirement IDs to JobPosting requirements."""
    return {requirement.id: requirement for requirement in job_posting.requirements}


def _format_date_range(start_date: str, end_date: str | None, is_current: bool) -> str:
    """Format a compact date range for CV preview sections."""
    if is_current:
        return f"{start_date} - Present"
    if end_date:
        return f"{start_date} - {end_date}"
    return start_date


def _collect_text_values(values: Iterable[str | None]) -> list[str]:
    """Filter empty values from a string iterable."""
    return [value for value in values if value]


def _find_keyword_hits(keywords: Iterable[str], texts: Iterable[str]) -> list[str]:
    """Find keywords that are explicitly present in one or more texts."""
    searchable_texts = [_normalize(text) for text in texts if text]
    hits: list[str] = []

    for keyword in keywords:
        normalized_keyword = _normalize(keyword)
        if not normalized_keyword:
            continue
        if any(normalized_keyword in text for text in searchable_texts):
            _append_unique(hits, keyword)

    return hits


def _get_importance_weight(requirement: Requirement | None) -> float:
    """Return the relevance weight of a requirement."""
    if requirement is None:
        return _IMPORTANCE_RELEVANCE["medium"]
    return _IMPORTANCE_RELEVANCE.get(_normalize(requirement.importance), _IMPORTANCE_RELEVANCE["medium"])


def _get_match_weight(requirement_match: RequirementMatch) -> float:
    """Return the relevance weight of a requirement match status."""
    return _MATCH_RELEVANCE.get(_normalize(requirement_match.match_status), 0.0)


def _score_experience(
    experience: ExperienceEntry,
    match_result: MatchResult,
    requirement_lookup: dict[str, Requirement],
    job_keywords: list[str],
) -> tuple[float, list[str], list[str]]:
    """Score one experience entry using match evidence and lightweight keyword overlap."""
    score = 0.0
    highlighted_keywords: list[str] = []
    linked_requirement_ids: list[str] = []
    experience_texts = _collect_text_values(
        [
            experience.position_title,
            *experience.technologies_used,
            *experience.keywords,
            *experience.responsibilities,
            *experience.achievements,
        ]
    )

    for requirement_match in match_result.requirement_matches:
        if experience.id not in requirement_match.matched_experience_ids:
            continue

        requirement = requirement_lookup.get(requirement_match.requirement_id)
        weight = _get_importance_weight(requirement) * _get_match_weight(requirement_match)
        score += weight
        _append_unique(linked_requirement_ids, requirement_match.requirement_id)

        if requirement is not None:
            for keyword in _find_keyword_hits(requirement.extracted_keywords, experience_texts):
                _append_unique(highlighted_keywords, keyword)

    overlap_hits = _find_keyword_hits(job_keywords, experience_texts)
    score += len(overlap_hits) * 0.3
    for keyword in overlap_hits:
        _append_unique(highlighted_keywords, keyword)

    return score, highlighted_keywords, linked_requirement_ids


def _score_project(
    project: ProjectEntry,
    match_result: MatchResult,
    requirement_lookup: dict[str, Requirement],
    job_keywords: list[str],
) -> tuple[float, list[str], list[str]]:
    """Score one project entry using match evidence and keyword overlap."""
    score = 0.0
    highlighted_keywords: list[str] = []
    linked_requirement_ids: list[str] = []
    project_texts = _collect_text_values(
        [
            project.project_name,
            project.role,
            project.description,
            *project.technologies_used,
            *project.keywords,
            *project.outcomes,
        ]
    )

    for requirement_match in match_result.requirement_matches:
        if project.id not in requirement_match.matched_project_ids:
            continue

        requirement = requirement_lookup.get(requirement_match.requirement_id)
        weight = _get_importance_weight(requirement) * _get_match_weight(requirement_match)
        score += weight
        _append_unique(linked_requirement_ids, requirement_match.requirement_id)

        if requirement is not None:
            for keyword in _find_keyword_hits(requirement.extracted_keywords, project_texts):
                _append_unique(highlighted_keywords, keyword)

    overlap_hits = _find_keyword_hits(job_keywords, project_texts)
    score += len(overlap_hits) * 0.25
    for keyword in overlap_hits:
        _append_unique(highlighted_keywords, keyword)

    return score, highlighted_keywords, linked_requirement_ids


def _select_top_bullets(
    bullet_candidates: list[str],
    relevant_keywords: list[str],
    *,
    fallback_limit: int,
) -> list[str]:
    """Choose the most relevant bullet points without rewriting source content."""
    scored_items: list[tuple[float, int, str]] = []

    for index, bullet in enumerate(bullet_candidates):
        if not bullet:
            continue
        keyword_hits = _find_keyword_hits(relevant_keywords, [bullet])
        score = float(len(keyword_hits))
        scored_items.append((score, index, bullet))

    relevant_items = [item for item in scored_items if item[0] > 0]
    if relevant_items:
        relevant_items.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in relevant_items[:fallback_limit]]

    return [bullet for bullet in bullet_candidates if bullet][:fallback_limit]


def _build_resume_experience_entries(
    candidate_profile: CandidateProfile,
    match_result: MatchResult,
    requirement_lookup: dict[str, Requirement],
    job_keywords: list[str],
) -> tuple[list[ResumeExperienceEntry], dict[str, list[str]]]:
    """Select and format the most relevant experience entries for the draft CV."""
    scored_experiences: list[tuple[float, int, ExperienceEntry, list[str], list[str]]] = []

    for index, experience in enumerate(candidate_profile.experience_entries):
        score, highlighted_keywords, linked_requirement_ids = _score_experience(
            experience,
            match_result,
            requirement_lookup,
            job_keywords,
        )
        if score <= 0:
            continue
        scored_experiences.append(
            (score, index, experience, highlighted_keywords, linked_requirement_ids)
        )

    scored_experiences.sort(key=lambda item: (-item[0], item[1]))

    selected_entries: list[ResumeExperienceEntry] = []
    selection_meta: dict[str, list[str]] = {}

    for _, _, experience, highlighted_keywords, linked_requirement_ids in scored_experiences[:_MAX_SELECTED_EXPERIENCES]:
        bullet_candidates = [*experience.achievements, *experience.responsibilities]
        bullet_points = _select_top_bullets(
            bullet_candidates,
            highlighted_keywords or job_keywords,
            fallback_limit=4,
        )

        selected_entries.append(
            ResumeExperienceEntry(
                source_experience_id=experience.id,
                company_name=experience.company_name,
                position_title=experience.position_title,
                date_range=_format_date_range(
                    experience.start_date,
                    experience.end_date,
                    experience.is_current,
                ),
                bullet_points=bullet_points,
                highlighted_keywords=highlighted_keywords[:6],
            )
        )
        selection_meta[experience.id] = linked_requirement_ids

    return selected_entries, selection_meta


def _build_resume_project_entries(
    candidate_profile: CandidateProfile,
    match_result: MatchResult,
    requirement_lookup: dict[str, Requirement],
    job_keywords: list[str],
) -> tuple[list[ResumeProjectEntry], dict[str, list[str]]]:
    """Select and format the most relevant project entries for the draft CV."""
    scored_projects: list[tuple[float, int, ProjectEntry, list[str], list[str]]] = []

    for index, project in enumerate(candidate_profile.project_entries):
        score, highlighted_keywords, linked_requirement_ids = _score_project(
            project,
            match_result,
            requirement_lookup,
            job_keywords,
        )
        if score <= 0:
            continue
        scored_projects.append((score, index, project, highlighted_keywords, linked_requirement_ids))

    scored_projects.sort(key=lambda item: (-item[0], item[1]))

    selected_entries: list[ResumeProjectEntry] = []
    selection_meta: dict[str, list[str]] = {}

    for _, _, project, highlighted_keywords, linked_requirement_ids in scored_projects[:_MAX_SELECTED_PROJECTS]:
        bullet_candidates = [*project.outcomes, project.description]
        bullet_points = _select_top_bullets(
            bullet_candidates,
            highlighted_keywords or job_keywords,
            fallback_limit=3,
        )

        selected_entries.append(
            ResumeProjectEntry(
                source_project_id=project.id,
                project_name=project.project_name,
                role=project.role,
                bullet_points=bullet_points,
                highlighted_keywords=highlighted_keywords[:6],
            )
        )
        selection_meta[project.id] = linked_requirement_ids

    return selected_entries, selection_meta


def _build_selected_skills(
    candidate_profile: CandidateProfile,
    selected_experience_entries: list[ResumeExperienceEntry],
    selected_project_entries: list[ResumeProjectEntry],
    match_result: MatchResult,
    requirement_lookup: dict[str, Requirement],
    job_keywords: list[str],
) -> list[str]:
    """Select the strongest grounded skills for the tailored draft CV."""
    skill_scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}

    def register_skill(skill_name: str, weight: float, order: int) -> None:
        normalized_skill = _normalize(skill_name)
        if not normalized_skill:
            return
        skill_scores[skill_name] = skill_scores.get(skill_name, 0.0) + weight
        first_seen.setdefault(skill_name, order)

    for requirement_match in match_result.requirement_matches:
        requirement = requirement_lookup.get(requirement_match.requirement_id)
        weight = _get_importance_weight(requirement) * _get_match_weight(requirement_match)
        for skill_name in requirement_match.matched_skill_names:
            register_skill(skill_name, weight + 1.0, len(first_seen))

    selected_experience_lookup = {
        experience_entry.source_experience_id for experience_entry in selected_experience_entries
    }
    selected_project_lookup = {
        project_entry.source_project_id for project_entry in selected_project_entries
    }
    for index, skill_entry in enumerate(candidate_profile.skill_entries):
        selected_evidence_sources = {
            evidence_source
            for evidence_source in skill_entry.evidence_sources
            if evidence_source in selected_experience_lookup or evidence_source in selected_project_lookup
        }
        keyword_hits = _find_keyword_hits(
            job_keywords,
            [skill_entry.name, *skill_entry.aliases],
        )
        evidence_bonus = 0.8 if selected_evidence_sources else 0.0
        if keyword_hits or selected_evidence_sources:
            register_skill(skill_entry.name, len(keyword_hits) + evidence_bonus, index)

    for experience in candidate_profile.experience_entries:
        if experience.id not in selected_experience_lookup:
            continue
        for technology in experience.technologies_used:
            keyword_hits = _find_keyword_hits(job_keywords, [technology])
            if keyword_hits:
                register_skill(technology, len(keyword_hits) + 0.5, len(first_seen))
    for project in candidate_profile.project_entries:
        if project.id not in selected_project_lookup:
            continue
        for technology in project.technologies_used:
            keyword_hits = _find_keyword_hits(job_keywords, [technology])
            if keyword_hits:
                register_skill(technology, len(keyword_hits) + 0.3, len(first_seen))

    ordered_skills = sorted(
        skill_scores.items(),
        key=lambda item: (-item[1], first_seen[item[0]]),
    )
    return [skill_name for skill_name, _ in ordered_skills[:_MAX_SELECTED_SKILLS]]


def _format_education_entry(entry: dict[str, str | bool | None]) -> str:
    """Format one education entry into a readable single-line CV item."""
    end_label = "Present" if entry["is_current"] else (entry["end_date"] or "")
    if end_label:
        date_range = f"{entry['start_date']} - {end_label}"
    else:
        date_range = str(entry["start_date"])

    return (
        f"{entry['degree']} in {entry['field_of_study']} - "
        f"{entry['institution_name']} ({date_range})"
    )


def _select_education(candidate_profile: CandidateProfile) -> list[str]:
    """Select a compact education section without copying an unbounded history."""
    selected_entries = candidate_profile.education_entries[:_MAX_SELECTED_EDUCATION]
    return [
        _format_education_entry(
            {
                "degree": entry.degree,
                "field_of_study": entry.field_of_study,
                "institution_name": entry.institution_name,
                "start_date": entry.start_date,
                "end_date": entry.end_date,
                "is_current": entry.is_current,
            }
        )
        for entry in selected_entries
    ]


def _select_languages(candidate_profile: CandidateProfile) -> list[str]:
    """Select a compact language section."""
    return [
        f"{entry.language_name} - {entry.proficiency_level}"
        for entry in candidate_profile.language_entries[:_MAX_SELECTED_LANGUAGES]
    ]


def _select_certificates(candidate_profile: CandidateProfile) -> list[str]:
    """Select a compact certificate section."""
    selected_entries = candidate_profile.certificate_entries[:_MAX_SELECTED_CERTIFICATES]
    formatted_entries: list[str] = []

    for entry in selected_entries:
        details = [entry.certificate_name]
        if entry.issuer:
            details.append(entry.issuer)
        if entry.issue_date:
            details.append(entry.issue_date)
        formatted_entries.append(" - ".join(details))

    return formatted_entries


def _build_professional_summary(
    candidate_profile: CandidateProfile,
    job_posting: JobPosting,
    selected_skills: list[str],
) -> str | None:
    """Build a grounded, minimally tailored summary from trusted profile content."""
    base_summary = candidate_profile.professional_summary_base.strip()
    if not base_summary:
        return None

    relevant_skills = ", ".join(selected_skills[:4])
    if not relevant_skills:
        return base_summary

    return (
        f"{base_summary} Most relevant for the {job_posting.title} role: {relevant_skills}."
    )


def _build_resume_header(candidate_profile: CandidateProfile, job_posting: JobPosting) -> ResumeHeader:
    """Build the CV header from trusted candidate data."""
    personal_info = candidate_profile.personal_info
    links: list[str] = []

    if personal_info.linkedin_url:
        _append_unique(links, str(personal_info.linkedin_url))
    if personal_info.github_url:
        _append_unique(links, str(personal_info.github_url))
    if personal_info.portfolio_url:
        _append_unique(links, str(personal_info.portfolio_url))

    return ResumeHeader(
        full_name=personal_info.full_name,
        professional_headline=job_posting.title,
        email=personal_info.email,
        phone=personal_info.phone,
        location=personal_info.location,
        links=links,
    )


def _build_keyword_usage(
    job_keywords: list[str],
    selected_skills: list[str],
    selected_experience_entries: list[ResumeExperienceEntry],
    selected_project_entries: list[ResumeProjectEntry],
) -> list[str]:
    """Track job keywords that are visibly present in the generated draft."""
    searchable_texts = [
        *selected_skills,
        *[
            keyword
            for experience_entry in selected_experience_entries
            for keyword in experience_entry.highlighted_keywords
        ],
        *[
            bullet
            for experience_entry in selected_experience_entries
            for bullet in experience_entry.bullet_points
        ],
        *[
            keyword
            for project_entry in selected_project_entries
            for keyword in project_entry.highlighted_keywords
        ],
        *[
            bullet
            for project_entry in selected_project_entries
            for bullet in project_entry.bullet_points
        ],
    ]
    return _find_keyword_hits(job_keywords, searchable_texts)


def _build_used_elements(
    candidate_profile: CandidateProfile,
    resume_draft: ResumeDraft,
    experience_selection_meta: dict[str, list[str]],
    project_selection_meta: dict[str, list[str]],
) -> tuple[list[str], list[str]]:
    """Build readable report lines for content used in the final draft."""
    used_elements: list[str] = []
    emphasized_elements: list[str] = []

    experience_lookup = {
        experience.id: experience for experience in candidate_profile.experience_entries
    }
    project_lookup = {project.id: project for project in candidate_profile.project_entries}

    for experience_entry in resume_draft.selected_experience_entries:
        source_experience = experience_lookup[experience_entry.source_experience_id]
        _append_unique(
            used_elements,
            f"Used experience: {source_experience.position_title} at {source_experience.company_name}.",
        )
        linked_requirements = experience_selection_meta.get(experience_entry.source_experience_id, [])
        if linked_requirements:
            _append_unique(
                emphasized_elements,
                (
                    f"Experience {source_experience.position_title} was emphasized for "
                    f"requirements: {', '.join(linked_requirements)}."
                ),
            )

    for project_entry in resume_draft.selected_project_entries:
        source_project = project_lookup[project_entry.source_project_id]
        _append_unique(
            used_elements,
            f"Used project: {source_project.project_name}.",
        )
        linked_requirements = project_selection_meta.get(project_entry.source_project_id, [])
        if linked_requirements:
            _append_unique(
                emphasized_elements,
                (
                    f"Project {source_project.project_name} supports requirements: "
                    f"{', '.join(linked_requirements)}."
                ),
            )

    if resume_draft.selected_skills:
        _append_unique(
            emphasized_elements,
            f"Highlighted skills: {', '.join(resume_draft.selected_skills)}.",
        )

    return used_elements, emphasized_elements


def _build_omissions(
    candidate_profile: CandidateProfile,
    resume_draft: ResumeDraft,
) -> tuple[list[str], list[str]]:
    """Build readable omission lines for profile content not used in the draft."""
    omitted_elements: list[str] = []
    omission_reasons: list[str] = []

    selected_experience_ids = {
        experience_entry.source_experience_id
        for experience_entry in resume_draft.selected_experience_entries
    }
    for experience in candidate_profile.experience_entries:
        if experience.id in selected_experience_ids:
            continue
        _append_unique(
            omitted_elements,
            f"Experience omitted: {experience.position_title} at {experience.company_name}.",
        )
        _append_unique(
            omission_reasons,
            (
                f"{experience.position_title} at {experience.company_name} was not used because "
                "it was not strongly supported by the selected job requirements or keywords."
            ),
        )

    selected_project_ids = {
        project_entry.source_project_id for project_entry in resume_draft.selected_project_entries
    }
    for project in candidate_profile.project_entries:
        if project.id in selected_project_ids:
            continue
        _append_unique(omitted_elements, f"Project omitted: {project.project_name}.")
        _append_unique(
            omission_reasons,
            (
                f"Project {project.project_name} was not used because it did not provide "
                "stronger evidence than the selected experience or project items."
            ),
        )

    selected_skill_names = {_normalize(skill_name) for skill_name in resume_draft.selected_skills}
    for skill_entry in candidate_profile.skill_entries:
        if _normalize(skill_entry.name) in selected_skill_names:
            continue
        _append_unique(omitted_elements, f"Skill omitted: {skill_entry.name}.")
        _append_unique(
            omission_reasons,
            f"Skill {skill_entry.name} was not highlighted because it was less relevant to this offer.",
        )

    if not resume_draft.selected_project_entries and candidate_profile.project_entries:
        _append_unique(
            omission_reasons,
            "No project section was highlighted because no project had strong evidence for this offer.",
        )

    return omitted_elements, omission_reasons


def _build_blocked_items(match_result: MatchResult) -> list[str]:
    """Build report lines describing what the generator did not fabricate."""
    blocked_items: list[str] = [
        "No unsupported experience, technology, certificate or years of experience were added.",
    ]

    unsupported_keywords: list[str] = []
    for requirement_match in match_result.requirement_matches:
        if requirement_match.match_status == "missing":
            for item in requirement_match.missing_elements:
                _append_unique(unsupported_keywords, item)

    if unsupported_keywords:
        _append_unique(
            blocked_items,
            f"Unsupported job requirements were not added to the draft: {', '.join(unsupported_keywords)}.",
        )

    return blocked_items


def _build_warnings(match_result: MatchResult, resume_draft: ResumeDraft) -> list[str]:
    """Build high-signal warnings for the report."""
    warnings: list[str] = []

    if match_result.recommendation != "generate":
        _append_unique(
            warnings,
            (
                f"Matching recommendation is {match_result.recommendation}; "
                "review the draft carefully before using it."
            ),
        )

    missing_requirements = [
        requirement_match.requirement_id
        for requirement_match in match_result.requirement_matches
        if requirement_match.match_status == "missing"
    ]
    if missing_requirements:
        _append_unique(
            warnings,
            f"Some requirements remain missing: {', '.join(missing_requirements)}.",
        )

    if not resume_draft.selected_experience_entries:
        _append_unique(
            warnings,
            "No directly relevant experience entry was selected for this draft.",
        )

    return warnings


def generate_resume_artifacts(
    candidate_profile: CandidateProfile,
    job_posting: JobPosting,
    match_result: MatchResult,
) -> dict[str, ResumeDraft | ChangeReport]:
    """Generate a truthful-first ResumeDraft and ChangeReport from saved inputs."""
    requirement_lookup = _build_requirement_lookup(job_posting)
    job_keywords = _collect_job_keywords(job_posting)

    selected_experience_entries, experience_selection_meta = _build_resume_experience_entries(
        candidate_profile,
        match_result,
        requirement_lookup,
        job_keywords,
    )
    selected_project_entries, project_selection_meta = _build_resume_project_entries(
        candidate_profile,
        match_result,
        requirement_lookup,
        job_keywords,
    )
    selected_skills = _build_selected_skills(
        candidate_profile,
        selected_experience_entries,
        selected_project_entries,
        match_result,
        requirement_lookup,
        job_keywords,
    )

    resume_draft = ResumeDraft(
        header=_build_resume_header(candidate_profile, job_posting),
        professional_summary=_build_professional_summary(
            candidate_profile,
            job_posting,
            selected_skills,
        ),
        selected_skills=selected_skills,
        selected_experience_entries=selected_experience_entries,
        selected_project_entries=selected_project_entries,
        selected_education_entries=_select_education(candidate_profile),
        selected_language_entries=_select_languages(candidate_profile),
        selected_certificate_entries=_select_certificates(candidate_profile),
        keyword_usage=_build_keyword_usage(
            job_keywords,
            selected_skills,
            selected_experience_entries,
            selected_project_entries,
        ),
    )

    added_elements, emphasized_elements = _build_used_elements(
        candidate_profile,
        resume_draft,
        experience_selection_meta,
        project_selection_meta,
    )
    omitted_elements, omission_reasons = _build_omissions(candidate_profile, resume_draft)

    change_report = ChangeReport(
        added_elements=added_elements,
        emphasized_elements=emphasized_elements,
        omitted_elements=omitted_elements,
        omission_reasons=omission_reasons,
        detected_keywords=job_posting.keywords,
        used_keywords=resume_draft.keyword_usage,
        unused_keywords=[
            keyword for keyword in job_posting.keywords if keyword not in resume_draft.keyword_usage
        ],
        blocked_items=_build_blocked_items(match_result),
        warnings=_build_warnings(match_result, resume_draft),
    )

    return {
        "resume_draft": resume_draft,
        "change_report": change_report,
    }
