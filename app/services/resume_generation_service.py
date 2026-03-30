"""Truthful-first generation of ResumeDraft and ChangeReport with safe AI fallback."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Iterable

from app.models.analysis import MatchAnalysisRequest
from app.models.candidate import CandidateProfile, ExperienceEntry, ProjectEntry
from app.models.job import JobPosting, Requirement
from app.models.match import MatchResult, RequirementMatch
from app.models.resume import (
    ChangeReport,
    ResumeDraft,
    ResumeExperienceEntry,
    ResumeFallbackReason,
    ResumeGenerationMode,
    ResumeHeader,
    ResumeMatchResultSource,
    ResumeProjectEntry,
)
from app.services.display_keyword_utils import build_display_keywords
from app.services.match_service import analyze_match_basic
from app.services.openai_candidate_profile_understanding_service import (
    CandidateProfileUnderstanding,
    get_candidate_profile_understanding,
)
from app.services.openai_requirement_priority_service import (
    OpenAIRequirementPriorityItem,
    get_requirement_priority_lookup,
)
from app.services.reportable_term_utils import (
    build_reportable_offer_terms_context,
)
from app.services.openai_resume_tailoring_service import (
    OpenAIResumeTailoringOutput,
    ResumeTailoringOpenAIError,
    generate_resume_tailoring_with_openai,
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
_MAX_REPORTABLE_JOB_KEYWORDS = 12
_MAX_HIGHLIGHTED_KEYWORDS = 6
_MAX_DECLARED_INTERESTS_IN_FIT_SUMMARY = 2
_CONTENT_TOKEN_STOPWORDS = {
    "about",
    "across",
    "activities",
    "and",
    "at",
    "before",
    "between",
    "built",
    "configured",
    "created",
    "delivered",
    "for",
    "from",
    "helped",
    "improved",
    "into",
    "maintained",
    "most",
    "or",
    "our",
    "role",
    "supported",
    "tasks",
    "that",
    "the",
    "their",
    "this",
    "through",
    "using",
    "with",
    "work",
}
_MIN_GROUNDED_TOKEN_OVERLAP_RATIO = 0.35

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResumeSemanticContext:
    """Curated semantic context reused across deterministic and AI-assisted resume generation."""

    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem]
    candidate_profile_understanding: CandidateProfileUnderstanding | None
    reportable_job_keywords: list[str]
    requirement_reportable_terms_lookup: dict[str, list[str]]
    source_signal_term_lookup: dict[tuple[str, str], list[str]]
    job_keyword_lookup: dict[str, str]


def _normalize(value: str | None) -> str:
    """Normalize a string for case-insensitive comparisons."""
    if not value:
        return ""
    return value.strip().lower()


def _has_configured_openai_api_key() -> bool:
    """Return whether a usable OpenAI API key is configured for optional AI helpers."""

    api_key = os.getenv("OPENAI_API_KEY")
    return bool(api_key and api_key != "tu_wkleisz_swoj_klucz")


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


def _extract_numeric_tokens(text: str | None) -> list[str]:
    """Extract numeric tokens that should not be invented in generated text."""
    if not text:
        return []
    return re.findall(r"\b\d+(?:[.,]\d+)?%?\b", text)


def _extract_content_tokens(text: str | None) -> list[str]:
    """Extract meaningful tokens for conservative grounding checks."""
    tokens: list[str] = []

    for token in _tokenize(text):
        if token in _CONTENT_TOKEN_STOPWORDS:
            continue
        if len(token) < 4 and not any(symbol in token for symbol in "+.#-"):
            continue
        _append_unique(tokens, token)

    return tokens


def _text_contains_unsupported_known_term(
    text: str,
    source_texts: Iterable[str | None],
    known_terms: Iterable[str | None],
) -> bool:
    """Check whether generated text mentions a known term that is absent from its source."""
    normalized_text = _normalize(text)
    normalized_source_blob = " ".join(_normalize(source_text) for source_text in source_texts if source_text)

    for known_term in known_terms:
        normalized_term = _normalize(known_term)
        if len(normalized_term) < 3:
            continue
        if normalized_term in normalized_text and normalized_term not in normalized_source_blob:
            return True

    return False


def _is_grounded_generated_text(
    text: str | None,
    *,
    source_texts: Iterable[str | None],
    known_terms: Iterable[str | None] = (),
) -> bool:
    """Conservatively validate that generated text stays close to grounded source text."""
    stripped_text = text.strip() if text else ""
    cleaned_source_texts = _collect_text_values(source_texts)

    if not stripped_text or not cleaned_source_texts:
        return False

    normalized_source_blob = " ".join(_normalize(source_text) for source_text in cleaned_source_texts)
    if any(number not in normalized_source_blob for number in _extract_numeric_tokens(stripped_text)):
        return False

    if _text_contains_unsupported_known_term(stripped_text, cleaned_source_texts, known_terms):
        return False

    generated_tokens = _extract_content_tokens(stripped_text)
    if not generated_tokens:
        return _normalize(stripped_text) in normalized_source_blob

    source_tokens: list[str] = []
    for source_text in cleaned_source_texts:
        for token in _extract_content_tokens(source_text):
            _append_unique(source_tokens, token)

    if not source_tokens:
        return _normalize(stripped_text) in normalized_source_blob

    overlap_count = sum(1 for token in generated_tokens if token in source_tokens)
    required_overlap = max(
        1,
        min(len(generated_tokens), int(len(generated_tokens) * _MIN_GROUNDED_TOKEN_OVERLAP_RATIO + 0.999)),
    )
    return overlap_count >= required_overlap


def _filter_grounded_generated_items(
    items: Iterable[str | None],
    *,
    source_texts: Iterable[str | None],
    known_terms: Iterable[str | None] = (),
    limit: int,
) -> list[str]:
    """Keep only generated strings that pass conservative grounding checks."""
    grounded_items: list[str] = []

    for item in items:
        stripped_item = item.strip() if item else ""
        if not stripped_item:
            continue
        if not _is_grounded_generated_text(
            stripped_item,
            source_texts=source_texts,
            known_terms=known_terms,
        ):
            continue
        _append_unique(grounded_items, stripped_item)
        if len(grounded_items) >= limit:
            break

    return grounded_items


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


def _filter_reportable_keyword_hits(
    keywords: Iterable[str],
    reportable_job_keywords: list[str],
    *,
    max_items: int | None = None,
) -> list[str]:
    """Keep only user-facing keyword hits that belong to the cleaned reportable keyword set."""
    allowed_keywords = {_normalize(keyword) for keyword in reportable_job_keywords}
    return build_display_keywords(
        [keyword for keyword in keywords if _normalize(keyword) in allowed_keywords],
        max_items=max_items,
    )


def _build_source_signal_term_lookup(
    candidate_profile_understanding: CandidateProfileUnderstanding | None,
) -> dict[tuple[str, str], list[str]]:
    """Collect cleaned source-level signal labels/terms from candidate understanding."""
    if candidate_profile_understanding is None:
        return {}

    lookup: dict[tuple[str, str], list[str]] = {}
    for signal in candidate_profile_understanding.source_signals:
        key = (signal.source_type, signal.source_id)
        terms = lookup.setdefault(key, [])
        for value in build_display_keywords([signal.signal_label, *signal.normalized_terms]):
            _append_unique(terms, value)
    return lookup


def _build_resume_semantic_context(
    job_posting: JobPosting,
    *,
    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem] | None = None,
    candidate_profile_understanding: CandidateProfileUnderstanding | None = None,
) -> ResumeSemanticContext:
    """Build one reusable semantic context so downstream steps do not recompute the same layers."""

    resolved_priority_lookup = requirement_priority_lookup or {}
    reportable_terms_context = build_reportable_offer_terms_context(
        job_posting,
        requirement_priority_lookup=resolved_priority_lookup,
    )
    reportable_job_keywords = build_display_keywords(
        reportable_terms_context.reportable_terms,
        max_items=_MAX_REPORTABLE_JOB_KEYWORDS,
    )

    return ResumeSemanticContext(
        requirement_priority_lookup=resolved_priority_lookup,
        candidate_profile_understanding=candidate_profile_understanding,
        reportable_job_keywords=reportable_job_keywords,
        requirement_reportable_terms_lookup=reportable_terms_context.requirement_terms_lookup,
        source_signal_term_lookup=_build_source_signal_term_lookup(candidate_profile_understanding),
        job_keyword_lookup=_build_allowed_value_lookup(reportable_job_keywords),
    )


def _source_signal_supports_term(term: str, source_signal_terms: list[str]) -> bool:
    """Return whether a reportable term is corroborated by source-level semantic signals."""
    normalized_term = _normalize(term)
    if not normalized_term:
        return False

    for source_term in source_signal_terms:
        normalized_source_term = _normalize(source_term)
        if not normalized_source_term:
            continue
        if normalized_term == normalized_source_term:
            return True
        if len(normalized_term) >= 4 and len(normalized_source_term) >= 4:
            if normalized_term in normalized_source_term or normalized_source_term in normalized_term:
                return True
    return False


def _collect_linked_requirement_ids_for_source(
    match_result: MatchResult,
    *,
    source_type: str,
    source_id: str,
) -> list[str]:
    """Collect requirement IDs grounded by a specific experience/project source."""
    linked_requirement_ids: list[str] = []

    for requirement_match in match_result.requirement_matches:
        if source_type == "experience" and source_id in requirement_match.matched_experience_ids:
            _append_unique(linked_requirement_ids, requirement_match.requirement_id)
        elif source_type == "project" and source_id in requirement_match.matched_project_ids:
            _append_unique(linked_requirement_ids, requirement_match.requirement_id)

    return linked_requirement_ids


def _build_source_reportable_term_candidates(
    *,
    source_type: str,
    source_id: str,
    linked_requirement_ids: list[str],
    requirement_reportable_terms_lookup: dict[str, list[str]],
    source_signal_term_lookup: dict[tuple[str, str], list[str]],
    reportable_job_keywords: list[str],
) -> list[str]:
    """Build the clean reportable-term candidate set relevant to one source entry."""
    allowed_keywords = {_normalize(keyword) for keyword in reportable_job_keywords}
    candidates: list[str] = []

    for requirement_id in linked_requirement_ids:
        for term in requirement_reportable_terms_lookup.get(requirement_id, []):
            if _normalize(term) in allowed_keywords:
                _append_unique(candidates, term)

    for term in source_signal_term_lookup.get((source_type, source_id), []):
        if _normalize(term) in allowed_keywords:
            _append_unique(candidates, term)

    return build_display_keywords(candidates)


def _build_source_highlighted_keywords(
    *,
    source_type: str,
    source_id: str,
    source_texts: list[str],
    linked_requirement_ids: list[str],
    requirement_reportable_terms_lookup: dict[str, list[str]],
    source_signal_term_lookup: dict[tuple[str, str], list[str]],
    reportable_job_keywords: list[str],
) -> list[str]:
    """Build grounded highlighted keywords for one experience/project source."""
    source_reportable_candidates = _build_source_reportable_term_candidates(
        source_type=source_type,
        source_id=source_id,
        linked_requirement_ids=linked_requirement_ids,
        requirement_reportable_terms_lookup=requirement_reportable_terms_lookup,
        source_signal_term_lookup=source_signal_term_lookup,
        reportable_job_keywords=reportable_job_keywords,
    )
    if not source_reportable_candidates:
        return []

    highlighted_keywords: list[str] = []
    source_signal_terms = source_signal_term_lookup.get((source_type, source_id), [])

    for keyword in _find_keyword_hits(source_reportable_candidates, source_texts):
        _append_unique(highlighted_keywords, keyword)

    for keyword in source_reportable_candidates:
        if _source_signal_supports_term(keyword, source_signal_terms):
            _append_unique(highlighted_keywords, keyword)

    if not highlighted_keywords:
        for requirement_id in linked_requirement_ids:
            requirement_terms = requirement_reportable_terms_lookup.get(requirement_id, [])
            if requirement_terms:
                _append_unique(highlighted_keywords, requirement_terms[0])

    return _filter_reportable_keyword_hits(
        highlighted_keywords,
        reportable_job_keywords,
        max_items=_MAX_HIGHLIGHTED_KEYWORDS,
    )


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
    reportable_job_keywords: list[str],
    requirement_reportable_terms_lookup: dict[str, list[str]],
    source_signal_term_lookup: dict[tuple[str, str], list[str]],
) -> tuple[float, list[str], list[str], list[str]]:
    """Score one experience entry using grounded match evidence and clean reportable terms."""
    score = 0.0
    experience_texts = _collect_text_values(
        [
            experience.position_title,
            *experience.technologies_used,
            *experience.keywords,
            *experience.responsibilities,
            *experience.achievements,
        ]
    )
    linked_requirement_ids = _collect_linked_requirement_ids_for_source(
        match_result,
        source_type="experience",
        source_id=experience.id,
    )

    for requirement_match in match_result.requirement_matches:
        if experience.id not in requirement_match.matched_experience_ids:
            continue

        requirement = requirement_lookup.get(requirement_match.requirement_id)
        weight = _get_importance_weight(requirement) * _get_match_weight(requirement_match)
        score += weight

    source_reportable_candidates = _build_source_reportable_term_candidates(
        source_type="experience",
        source_id=experience.id,
        linked_requirement_ids=linked_requirement_ids,
        requirement_reportable_terms_lookup=requirement_reportable_terms_lookup,
        source_signal_term_lookup=source_signal_term_lookup,
        reportable_job_keywords=reportable_job_keywords,
    )
    highlighted_keywords = _build_source_highlighted_keywords(
        source_type="experience",
        source_id=experience.id,
        source_texts=experience_texts,
        linked_requirement_ids=linked_requirement_ids,
        requirement_reportable_terms_lookup=requirement_reportable_terms_lookup,
        source_signal_term_lookup=source_signal_term_lookup,
        reportable_job_keywords=reportable_job_keywords,
    )
    score += len(highlighted_keywords) * 0.35
    score += len(source_reportable_candidates) * 0.15

    return (
        score,
        highlighted_keywords,
        source_reportable_candidates,
        linked_requirement_ids,
    )


def _score_project(
    project: ProjectEntry,
    match_result: MatchResult,
    requirement_lookup: dict[str, Requirement],
    reportable_job_keywords: list[str],
    requirement_reportable_terms_lookup: dict[str, list[str]],
    source_signal_term_lookup: dict[tuple[str, str], list[str]],
) -> tuple[float, list[str], list[str], list[str]]:
    """Score one project entry using grounded match evidence and clean reportable terms."""
    score = 0.0
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
    linked_requirement_ids = _collect_linked_requirement_ids_for_source(
        match_result,
        source_type="project",
        source_id=project.id,
    )

    for requirement_match in match_result.requirement_matches:
        if project.id not in requirement_match.matched_project_ids:
            continue

        requirement = requirement_lookup.get(requirement_match.requirement_id)
        weight = _get_importance_weight(requirement) * _get_match_weight(requirement_match)
        score += weight

    source_reportable_candidates = _build_source_reportable_term_candidates(
        source_type="project",
        source_id=project.id,
        linked_requirement_ids=linked_requirement_ids,
        requirement_reportable_terms_lookup=requirement_reportable_terms_lookup,
        source_signal_term_lookup=source_signal_term_lookup,
        reportable_job_keywords=reportable_job_keywords,
    )
    highlighted_keywords = _build_source_highlighted_keywords(
        source_type="project",
        source_id=project.id,
        source_texts=project_texts,
        linked_requirement_ids=linked_requirement_ids,
        requirement_reportable_terms_lookup=requirement_reportable_terms_lookup,
        source_signal_term_lookup=source_signal_term_lookup,
        reportable_job_keywords=reportable_job_keywords,
    )
    score += len(highlighted_keywords) * 0.3
    score += len(source_reportable_candidates) * 0.12

    return (
        score,
        highlighted_keywords,
        source_reportable_candidates,
        linked_requirement_ids,
    )


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
    reportable_job_keywords: list[str],
    requirement_reportable_terms_lookup: dict[str, list[str]],
    source_signal_term_lookup: dict[tuple[str, str], list[str]],
) -> tuple[list[ResumeExperienceEntry], dict[str, list[str]]]:
    """Select and format the most relevant experience entries for the draft CV."""
    scored_experiences: list[
        tuple[float, int, ExperienceEntry, list[str], list[str], list[str]]
    ] = []

    for index, experience in enumerate(candidate_profile.experience_entries):
        score, highlighted_keywords, source_reportable_candidates, linked_requirement_ids = _score_experience(
            experience,
            match_result,
            requirement_lookup,
            reportable_job_keywords,
            requirement_reportable_terms_lookup,
            source_signal_term_lookup,
        )
        if score <= 0:
            continue
        scored_experiences.append(
            (
                score,
                index,
                experience,
                highlighted_keywords,
                source_reportable_candidates,
                linked_requirement_ids,
            )
        )

    scored_experiences.sort(key=lambda item: (-item[0], item[1]))

    selected_entries: list[ResumeExperienceEntry] = []
    selection_meta: dict[str, list[str]] = {}

    for (
        _,
        _,
        experience,
        highlighted_keywords,
        source_reportable_candidates,
        linked_requirement_ids,
    ) in scored_experiences[:_MAX_SELECTED_EXPERIENCES]:
        bullet_candidates = [*experience.achievements, *experience.responsibilities]
        bullet_points = _select_top_bullets(
            bullet_candidates,
            highlighted_keywords or source_reportable_candidates,
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
                highlighted_keywords=highlighted_keywords,
            )
        )
        selection_meta[experience.id] = linked_requirement_ids

    return selected_entries, selection_meta


def _build_resume_project_entries(
    candidate_profile: CandidateProfile,
    match_result: MatchResult,
    requirement_lookup: dict[str, Requirement],
    reportable_job_keywords: list[str],
    requirement_reportable_terms_lookup: dict[str, list[str]],
    source_signal_term_lookup: dict[tuple[str, str], list[str]],
) -> tuple[list[ResumeProjectEntry], dict[str, list[str]]]:
    """Select and format the most relevant project entries for the draft CV."""
    scored_projects: list[
        tuple[float, int, ProjectEntry, list[str], list[str], list[str]]
    ] = []

    for index, project in enumerate(candidate_profile.project_entries):
        score, highlighted_keywords, source_reportable_candidates, linked_requirement_ids = _score_project(
            project,
            match_result,
            requirement_lookup,
            reportable_job_keywords,
            requirement_reportable_terms_lookup,
            source_signal_term_lookup,
        )
        if score <= 0:
            continue
        scored_projects.append(
            (
                score,
                index,
                project,
                highlighted_keywords,
                source_reportable_candidates,
                linked_requirement_ids,
            )
        )

    scored_projects.sort(key=lambda item: (-item[0], item[1]))

    selected_entries: list[ResumeProjectEntry] = []
    selection_meta: dict[str, list[str]] = {}

    for (
        _,
        _,
        project,
        highlighted_keywords,
        source_reportable_candidates,
        linked_requirement_ids,
    ) in scored_projects[:_MAX_SELECTED_PROJECTS]:
        bullet_candidates = [*project.outcomes, project.description]
        bullet_points = _select_top_bullets(
            bullet_candidates,
            highlighted_keywords or source_reportable_candidates,
            fallback_limit=3,
        )

        selected_entries.append(
            ResumeProjectEntry(
                source_project_id=project.id,
                project_name=project.project_name,
                role=project.role,
                bullet_points=bullet_points,
                highlighted_keywords=highlighted_keywords,
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
    reportable_job_keywords: list[str],
) -> list[str]:
    """Select the strongest grounded skills for the tailored draft CV."""
    skill_scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    normalized_reportable_keywords = {_normalize(keyword) for keyword in reportable_job_keywords}

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
        normalized_skill_names = {
            _normalize(skill_entry.name),
            *[_normalize(alias) for alias in skill_entry.aliases],
        }
        explicit_offer_alignment = any(
            normalized_skill_name in normalized_reportable_keywords
            for normalized_skill_name in normalized_skill_names
            if normalized_skill_name
        )
        evidence_bonus = 0.9 if selected_evidence_sources else 0.0
        offer_alignment_bonus = 0.6 if explicit_offer_alignment else 0.0
        if selected_evidence_sources or explicit_offer_alignment:
            register_skill(
                skill_entry.name,
                evidence_bonus + offer_alignment_bonus,
                index,
            )

    for experience in candidate_profile.experience_entries:
        if experience.id not in selected_experience_lookup:
            continue
        for technology in experience.technologies_used:
            normalized_technology = _normalize(technology)
            if normalized_technology in normalized_reportable_keywords:
                register_skill(technology, 0.7, len(first_seen))
    for project in candidate_profile.project_entries:
        if project.id not in selected_project_lookup:
            continue
        for technology in project.technologies_used:
            normalized_technology = _normalize(technology)
            if normalized_technology in normalized_reportable_keywords:
                register_skill(technology, 0.5, len(first_seen))

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


def _format_certificate_entry(entry: dict[str, str | None]) -> str:
    """Format one certificate entry into a readable single-line CV item."""
    details = [entry["certificate_name"]]
    if entry["issuer"]:
        details.append(entry["issuer"])
    if entry["issue_date"]:
        details.append(entry["issue_date"])
    return " - ".join(details)


def _select_certificates(candidate_profile: CandidateProfile) -> list[str]:
    """Select a compact certificate section."""
    selected_entries = candidate_profile.certificate_entries[:_MAX_SELECTED_CERTIFICATES]
    return [
        _format_certificate_entry(
            {
                "certificate_name": entry.certificate_name,
                "issuer": entry.issuer,
                "issue_date": entry.issue_date,
            }
        )
        for entry in selected_entries
    ]


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


def _collect_candidate_understanding_grounding_texts(
    candidate_profile_understanding: CandidateProfileUnderstanding | None,
) -> list[str]:
    """Collect grounded semantic profile texts without turning them into hard-selected skills."""

    if candidate_profile_understanding is None:
        return []

    return _collect_text_values(
        [
            *[
                value
                for signal in candidate_profile_understanding.source_signals
                for value in [signal.signal_label, *signal.normalized_terms, *signal.supporting_snippets]
            ],
            *[
                value
                for signal in candidate_profile_understanding.profile_signals
                for value in [signal.signal_label, *signal.normalized_terms]
            ],
            *[
                value
                for normalization in candidate_profile_understanding.language_normalizations
                for value in [
                    normalization.language_name,
                    normalization.source_level,
                    normalization.normalized_cefr.upper() if normalization.normalized_cefr else None,
                    *normalization.semantic_descriptors,
                ]
            ],
            *[
                value
                for alignment in candidate_profile_understanding.thematic_alignments
                for value in [alignment.theme_label, *alignment.normalized_terms]
            ],
        ]
    )


def _collect_candidate_understanding_known_terms(
    candidate_profile_understanding: CandidateProfileUnderstanding | None,
) -> list[str]:
    """Collect canonical profile-understanding terms used in grounding guardrails."""

    if candidate_profile_understanding is None:
        return []

    known_terms = _collect_text_values(
        [
            *[
                value
                for signal in candidate_profile_understanding.profile_signals
                for value in [signal.signal_label, *signal.normalized_terms]
            ],
            *[
                value
                for normalization in candidate_profile_understanding.language_normalizations
                for value in [
                    normalization.language_name,
                    normalization.normalized_cefr.upper() if normalization.normalized_cefr else None,
                    *normalization.semantic_descriptors,
                ]
            ],
            *[
                value
                for alignment in candidate_profile_understanding.thematic_alignments
                for value in [alignment.theme_label, *alignment.normalized_terms]
            ],
        ]
    )
    return list(dict.fromkeys(known_terms))


def _select_declared_interest_alignment(
    candidate_profile: CandidateProfile,
    reportable_job_keywords: list[str],
) -> list[str]:
    """Pick declared interests that align with the offer without turning them into hard evidence."""
    cleaned_interests = _clean_string_list(candidate_profile.interest_entries, limit=8)
    if not cleaned_interests:
        return []

    direct_hits = _filter_reportable_keyword_hits(
        cleaned_interests,
        reportable_job_keywords,
        max_items=_MAX_DECLARED_INTERESTS_IN_FIT_SUMMARY,
    )
    if direct_hits:
        return direct_hits

    thematic_hits: list[str] = []
    normalized_keywords = [_normalize(keyword) for keyword in reportable_job_keywords if keyword]
    for interest in cleaned_interests:
        normalized_interest = _normalize(interest)
        if len(normalized_interest) < 4:
            continue
        if any(
            len(normalized_keyword) >= 4
            and (normalized_interest in normalized_keyword or normalized_keyword in normalized_interest)
            for normalized_keyword in normalized_keywords
        ):
            _append_unique(thematic_hits, interest)

    return build_display_keywords(
        thematic_hits,
        max_items=_MAX_DECLARED_INTERESTS_IN_FIT_SUMMARY,
    )


def _build_fit_summary(
    candidate_profile: CandidateProfile,
    match_result: MatchResult,
    reportable_job_keywords: list[str],
) -> str:
    """Build a fit summary that may mention aligned declared interests without implying competence."""
    base_summary = match_result.final_summary.strip()
    aligned_interests = _select_declared_interest_alignment(candidate_profile, reportable_job_keywords)
    if not aligned_interests:
        return base_summary

    return (
        f"{base_summary} Declared interest alignment: {', '.join(aligned_interests)}."
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


def _build_allowed_value_lookup(values: Iterable[str | None]) -> dict[str, str]:
    """Create a normalized lookup used to filter AI output to known allowed values."""
    lookup: dict[str, str] = {}

    for value in values:
        stripped_value = value.strip() if value else ""
        normalized_value = _normalize(stripped_value)
        if stripped_value and normalized_value not in lookup:
            lookup[normalized_value] = stripped_value

    return lookup


def _filter_allowed_values(
    values: Iterable[str | None],
    allowed_lookup: dict[str, str],
    *,
    limit: int,
) -> list[str]:
    """Keep only values that match an allowed canonical lookup while preserving order."""
    filtered_values: list[str] = []

    for value in values:
        canonical_value = allowed_lookup.get(_normalize(value))
        if not canonical_value:
            continue
        _append_unique(filtered_values, canonical_value)
        if len(filtered_values) >= limit:
            break

    return filtered_values


def _clean_string_list(values: Iterable[str | None], *, limit: int | None = None) -> list[str]:
    """Trim, deduplicate and optionally cap a list of human-readable strings."""
    cleaned_values: list[str] = []

    for value in values:
        _append_unique(cleaned_values, value)
        if limit is not None and len(cleaned_values) >= limit:
            break

    return cleaned_values


def _list_all_education_entries(candidate_profile: CandidateProfile) -> list[str]:
    """Format all education entries for strict selection filtering."""
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
        for entry in candidate_profile.education_entries
    ]


def _list_all_language_entries(candidate_profile: CandidateProfile) -> list[str]:
    """Format all language entries for strict selection filtering."""
    return [
        f"{entry.language_name} - {entry.proficiency_level}"
        for entry in candidate_profile.language_entries
    ]


def _list_all_certificate_entries(candidate_profile: CandidateProfile) -> list[str]:
    """Format all certificate entries for strict selection filtering."""
    return [
        _format_certificate_entry(
            {
                "certificate_name": entry.certificate_name,
                "issuer": entry.issuer,
                "issue_date": entry.issue_date,
            }
        )
        for entry in candidate_profile.certificate_entries
    ]


def _build_candidate_skill_lookup(candidate_profile: CandidateProfile) -> dict[str, str]:
    """Create the canonical set of skills and technologies the AI is allowed to use."""
    lookup: dict[str, str] = {}

    def register(value: str | None, canonical_value: str | None = None) -> None:
        stripped_value = value.strip() if value else ""
        normalized_value = _normalize(stripped_value)
        canonical = canonical_value.strip() if canonical_value else stripped_value
        if stripped_value and normalized_value not in lookup:
            lookup[normalized_value] = canonical

    for skill_entry in candidate_profile.skill_entries:
        register(skill_entry.name, skill_entry.name)
        for alias in skill_entry.aliases:
            register(alias, skill_entry.name)

    for experience_entry in candidate_profile.experience_entries:
        for technology in experience_entry.technologies_used:
            register(technology)

    for project_entry in candidate_profile.project_entries:
        for technology in project_entry.technologies_used:
            register(technology)

    return lookup


def _build_selection_meta_from_match(
    match_result: MatchResult,
    resume_draft: ResumeDraft,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Link selected experience and project IDs back to requirement IDs using MatchResult evidence."""
    experience_selection_meta = {
        experience_entry.source_experience_id: []
        for experience_entry in resume_draft.selected_experience_entries
    }
    project_selection_meta = {
        project_entry.source_project_id: []
        for project_entry in resume_draft.selected_project_entries
    }

    for requirement_match in match_result.requirement_matches:
        for experience_id in requirement_match.matched_experience_ids:
            if experience_id in experience_selection_meta:
                _append_unique(
                    experience_selection_meta[experience_id],
                    requirement_match.requirement_id,
                )
        for project_id in requirement_match.matched_project_ids:
            if project_id in project_selection_meta:
                _append_unique(
                    project_selection_meta[project_id],
                    requirement_match.requirement_id,
                )

    return experience_selection_meta, project_selection_meta


def _build_change_report(
    candidate_profile: CandidateProfile,
    match_result: MatchResult,
    resume_draft: ResumeDraft,
    reportable_job_keywords: list[str],
    *,
    extra_warnings: Iterable[str] = (),
    extra_blocked_items: Iterable[str] = (),
    extra_omitted_items: Iterable[str] = (),
) -> ChangeReport:
    """Build a readable ChangeReport for either AI-assisted or fallback draft generation."""
    experience_selection_meta, project_selection_meta = _build_selection_meta_from_match(
        match_result,
        resume_draft,
    )

    added_elements, emphasized_elements = _build_used_elements(
        candidate_profile,
        resume_draft,
        experience_selection_meta,
        project_selection_meta,
    )
    omitted_elements, omission_reasons = _build_omissions(candidate_profile, resume_draft)
    blocked_items = _build_blocked_items(match_result)
    warnings = _build_warnings(match_result, resume_draft)

    for item in extra_omitted_items:
        _append_unique(omitted_elements, item)
    for item in extra_blocked_items:
        _append_unique(blocked_items, item)
    for item in extra_warnings:
        _append_unique(warnings, item)

    return ChangeReport(
        added_elements=added_elements,
        emphasized_elements=emphasized_elements,
        omitted_elements=omitted_elements,
        omission_reasons=omission_reasons,
        detected_keywords=reportable_job_keywords,
        used_keywords=resume_draft.keyword_usage,
        unused_keywords=[
            keyword for keyword in reportable_job_keywords if keyword not in resume_draft.keyword_usage
        ],
        blocked_items=blocked_items,
        warnings=warnings,
    )


def _build_rule_based_resume_draft(
    candidate_profile: CandidateProfile,
    job_posting: JobPosting,
    match_result: MatchResult,
    semantic_context: ResumeSemanticContext,
) -> ResumeDraft:
    """Build the existing deterministic ResumeDraft used as a safe fallback."""
    requirement_lookup = _build_requirement_lookup(job_posting)

    selected_experience_entries, _ = _build_resume_experience_entries(
        candidate_profile,
        match_result,
        requirement_lookup,
        semantic_context.reportable_job_keywords,
        semantic_context.requirement_reportable_terms_lookup,
        semantic_context.source_signal_term_lookup,
    )
    selected_project_entries, _ = _build_resume_project_entries(
        candidate_profile,
        match_result,
        requirement_lookup,
        semantic_context.reportable_job_keywords,
        semantic_context.requirement_reportable_terms_lookup,
        semantic_context.source_signal_term_lookup,
    )
    selected_skills = _build_selected_skills(
        candidate_profile,
        selected_experience_entries,
        selected_project_entries,
        match_result,
        requirement_lookup,
        semantic_context.reportable_job_keywords,
    )
    keyword_usage = _build_keyword_usage(
        semantic_context.reportable_job_keywords,
        selected_skills,
        selected_experience_entries,
        selected_project_entries,
    )

    return ResumeDraft(
        header=_build_resume_header(candidate_profile, job_posting),
        target_job_title=job_posting.title,
        target_company_name=job_posting.company_name,
        fit_summary=_build_fit_summary(
            candidate_profile,
            match_result,
            semantic_context.reportable_job_keywords,
        ),
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
        selected_keywords=keyword_usage,
        keyword_usage=keyword_usage,
    )


def _build_ai_assisted_resume_draft(
    candidate_profile: CandidateProfile,
    job_posting: JobPosting,
    match_result: MatchResult,
    ai_output: OpenAIResumeTailoringOutput,
    semantic_context: ResumeSemanticContext,
) -> tuple[ResumeDraft, dict[str, list[str]]]:
    """Hydrate, validate and constrain the AI output into the public ResumeDraft contract."""
    requirement_lookup = _build_requirement_lookup(job_posting)
    candidate_skill_lookup = _build_candidate_skill_lookup(candidate_profile)
    candidate_understanding_grounding_texts = _collect_candidate_understanding_grounding_texts(
        semantic_context.candidate_profile_understanding,
    )
    candidate_understanding_known_terms = _collect_candidate_understanding_known_terms(
        semantic_context.candidate_profile_understanding,
    )
    candidate_known_terms = list(
        dict.fromkeys([*candidate_skill_lookup.values(), *candidate_understanding_known_terms])
    )
    experience_lookup = {
        experience_entry.id: experience_entry for experience_entry in candidate_profile.experience_entries
    }
    project_lookup = {
        project_entry.id: project_entry for project_entry in candidate_profile.project_entries
    }

    ignored_unknown_references = False
    filtered_unknown_skills = False
    filtered_unknown_keywords = False
    used_guardrail_bullet_fallback = False
    used_guardrail_summary_fallback = False
    used_guardrail_fit_summary_fallback = False

    selected_experience_entries: list[ResumeExperienceEntry] = []
    for selection in ai_output.selected_experience_entries[:_MAX_SELECTED_EXPERIENCES]:
        source_entry = experience_lookup.get(selection.source_experience_id)
        if source_entry is None:
            ignored_unknown_references = True
            continue

        source_lines = [*source_entry.achievements, *source_entry.responsibilities]
        source_highlights = _filter_allowed_values(
            selection.source_highlights,
            _build_allowed_value_lookup(source_lines),
            limit=3,
        )
        grounding_texts = [
            source_entry.position_title,
            *source_entry.technologies_used,
            *source_entry.keywords,
            *source_lines,
            *source_highlights,
        ]
        linked_requirement_ids = _collect_linked_requirement_ids_for_source(
            match_result,
            source_type="experience",
            source_id=source_entry.id,
        )
        source_reportable_candidates = _build_source_reportable_term_candidates(
            source_type="experience",
            source_id=source_entry.id,
            linked_requirement_ids=linked_requirement_ids,
            requirement_reportable_terms_lookup=semantic_context.requirement_reportable_terms_lookup,
            source_signal_term_lookup=semantic_context.source_signal_term_lookup,
            reportable_job_keywords=semantic_context.reportable_job_keywords,
        )
        source_highlighted_fallback = _build_source_highlighted_keywords(
            source_type="experience",
            source_id=source_entry.id,
            source_texts=[
                source_entry.position_title,
                *source_entry.technologies_used,
                *source_entry.keywords,
                *source_entry.responsibilities,
                *source_entry.achievements,
            ],
            linked_requirement_ids=linked_requirement_ids,
            requirement_reportable_terms_lookup=semantic_context.requirement_reportable_terms_lookup,
            source_signal_term_lookup=semantic_context.source_signal_term_lookup,
            reportable_job_keywords=semantic_context.reportable_job_keywords,
        )
        highlighted_keywords = _filter_allowed_values(
            selection.highlighted_keywords,
            _build_allowed_value_lookup(source_reportable_candidates),
            limit=6,
        )
        bullet_points = _filter_grounded_generated_items(
            selection.tailored_bullets,
            source_texts=grounding_texts,
            known_terms=candidate_known_terms,
            limit=4,
        )
        if not bullet_points or not source_highlights:
            bullet_points = _select_top_bullets(
                source_lines,
                highlighted_keywords
                or source_highlighted_fallback
                or source_reportable_candidates,
                fallback_limit=4,
            )
            source_highlights = source_highlights or _clean_string_list(bullet_points, limit=3)
            used_guardrail_bullet_fallback = True

        selected_experience_entries.append(
            ResumeExperienceEntry(
                source_experience_id=source_entry.id,
                company_name=source_entry.company_name,
                position_title=source_entry.position_title,
                date_range=_format_date_range(
                    source_entry.start_date,
                    source_entry.end_date,
                    source_entry.is_current,
                ),
                bullet_points=bullet_points,
                highlighted_keywords=(
                    highlighted_keywords
                    or source_highlighted_fallback
                    or source_reportable_candidates[:_MAX_HIGHLIGHTED_KEYWORDS]
                ),
                relevance_note=(selection.relevance_note or "").strip() or None,
                source_highlights=source_highlights,
            )
        )

    selected_project_entries: list[ResumeProjectEntry] = []
    for selection in ai_output.selected_project_entries[:_MAX_SELECTED_PROJECTS]:
        source_entry = project_lookup.get(selection.source_project_id)
        if source_entry is None:
            ignored_unknown_references = True
            continue

        source_lines = [*source_entry.outcomes, source_entry.description]
        source_highlights = _filter_allowed_values(
            selection.source_highlights,
            _build_allowed_value_lookup(source_lines),
            limit=3,
        )
        grounding_texts = [
            source_entry.project_name,
            source_entry.role,
            *source_entry.technologies_used,
            *source_entry.keywords,
            *source_lines,
            *source_highlights,
        ]
        linked_requirement_ids = _collect_linked_requirement_ids_for_source(
            match_result,
            source_type="project",
            source_id=source_entry.id,
        )
        source_reportable_candidates = _build_source_reportable_term_candidates(
            source_type="project",
            source_id=source_entry.id,
            linked_requirement_ids=linked_requirement_ids,
            requirement_reportable_terms_lookup=semantic_context.requirement_reportable_terms_lookup,
            source_signal_term_lookup=semantic_context.source_signal_term_lookup,
            reportable_job_keywords=semantic_context.reportable_job_keywords,
        )
        source_highlighted_fallback = _build_source_highlighted_keywords(
            source_type="project",
            source_id=source_entry.id,
            source_texts=[
                source_entry.project_name,
                source_entry.role,
                source_entry.description,
                *source_entry.technologies_used,
                *source_entry.keywords,
                *source_entry.outcomes,
            ],
            linked_requirement_ids=linked_requirement_ids,
            requirement_reportable_terms_lookup=semantic_context.requirement_reportable_terms_lookup,
            source_signal_term_lookup=semantic_context.source_signal_term_lookup,
            reportable_job_keywords=semantic_context.reportable_job_keywords,
        )
        highlighted_keywords = _filter_allowed_values(
            selection.highlighted_keywords,
            _build_allowed_value_lookup(source_reportable_candidates),
            limit=6,
        )
        bullet_points = _filter_grounded_generated_items(
            selection.tailored_bullets,
            source_texts=grounding_texts,
            known_terms=candidate_known_terms,
            limit=3,
        )
        if not bullet_points or not source_highlights:
            bullet_points = _select_top_bullets(
                [item for item in source_lines if item],
                highlighted_keywords
                or source_highlighted_fallback
                or source_reportable_candidates,
                fallback_limit=3,
            )
            source_highlights = source_highlights or _clean_string_list(bullet_points, limit=3)
            used_guardrail_bullet_fallback = True

        selected_project_entries.append(
            ResumeProjectEntry(
                source_project_id=source_entry.id,
                project_name=source_entry.project_name,
                role=source_entry.role,
                bullet_points=bullet_points,
                highlighted_keywords=(
                    highlighted_keywords
                    or source_highlighted_fallback
                    or source_reportable_candidates[:_MAX_HIGHLIGHTED_KEYWORDS]
                ),
                relevance_note=(selection.relevance_note or "").strip() or None,
                source_highlights=source_highlights,
            )
        )

    selected_skills = _filter_allowed_values(
        ai_output.selected_skills,
        candidate_skill_lookup,
        limit=_MAX_SELECTED_SKILLS,
    )
    if len(selected_skills) < len(_clean_string_list(ai_output.selected_skills)):
        filtered_unknown_skills = True
    if not selected_skills:
        selected_skills = _build_selected_skills(
            candidate_profile,
            selected_experience_entries,
            selected_project_entries,
            match_result,
            requirement_lookup,
            semantic_context.reportable_job_keywords,
        )

    selected_keywords = _filter_allowed_values(
        ai_output.selected_keywords,
        semantic_context.job_keyword_lookup,
        limit=10,
    )
    if len(selected_keywords) < len(_clean_string_list(ai_output.selected_keywords)):
        filtered_unknown_keywords = True

    selected_education_entries = _filter_allowed_values(
        ai_output.selected_education_entries,
        _build_allowed_value_lookup(_list_all_education_entries(candidate_profile)),
        limit=_MAX_SELECTED_EDUCATION,
    )
    selected_language_entries = _filter_allowed_values(
        ai_output.selected_language_entries,
        _build_allowed_value_lookup(_list_all_language_entries(candidate_profile)),
        limit=_MAX_SELECTED_LANGUAGES,
    )
    selected_certificate_entries = _filter_allowed_values(
        ai_output.selected_certificate_entries,
        _build_allowed_value_lookup(_list_all_certificate_entries(candidate_profile)),
        limit=_MAX_SELECTED_CERTIFICATES,
    )

    if not selected_education_entries:
        selected_education_entries = _select_education(candidate_profile)
    if not selected_language_entries:
        selected_language_entries = _select_languages(candidate_profile)
    if not selected_certificate_entries:
        selected_certificate_entries = _select_certificates(candidate_profile)

    keyword_usage = _build_keyword_usage(
        semantic_context.reportable_job_keywords,
        selected_skills,
        selected_experience_entries,
        selected_project_entries,
    )
    if not selected_keywords:
        selected_keywords = keyword_usage

    fallback_professional_summary = _build_professional_summary(
        candidate_profile,
        job_posting,
        selected_skills,
    )
    fallback_fit_summary = _build_fit_summary(
        candidate_profile,
        match_result,
        semantic_context.reportable_job_keywords,
    )
    aligned_interest_entries = _select_declared_interest_alignment(
        candidate_profile,
        semantic_context.reportable_job_keywords,
    )
    summary_grounding_texts = [
        candidate_profile.professional_summary_base,
        *candidate_profile.target_roles,
        *candidate_profile.interest_entries,
        *selected_skills,
        *candidate_understanding_grounding_texts,
        *[
            highlight
            for experience_entry in selected_experience_entries
            for highlight in experience_entry.source_highlights
        ],
        *[
            bullet
            for experience_entry in selected_experience_entries
            for bullet in experience_entry.bullet_points
        ],
        *[
            highlight
            for project_entry in selected_project_entries
            for highlight in project_entry.source_highlights
        ],
        *[
            bullet
            for project_entry in selected_project_entries
            for bullet in project_entry.bullet_points
        ],
    ]
    professional_summary = (ai_output.professional_summary or "").strip()
    if professional_summary and not _is_grounded_generated_text(
        professional_summary,
        source_texts=summary_grounding_texts,
        known_terms=[*candidate_known_terms, *semantic_context.reportable_job_keywords],
    ):
        professional_summary = ""
        used_guardrail_summary_fallback = True
    professional_summary = professional_summary or fallback_professional_summary

    fit_summary = (ai_output.fit_summary or "").strip()
    if fit_summary and not _is_grounded_generated_text(
        fit_summary,
        source_texts=[
            match_result.final_summary,
            fallback_fit_summary,
            *aligned_interest_entries,
            *candidate_understanding_grounding_texts,
            *selected_keywords,
            *selected_skills,
        ],
        known_terms=[*candidate_known_terms, *semantic_context.reportable_job_keywords],
    ):
        fit_summary = ""
        used_guardrail_fit_summary_fallback = True
    fit_summary = fit_summary or fallback_fit_summary

    if not selected_experience_entries and not selected_project_entries:
        raise ResumeTailoringOpenAIError(
            "OpenAI returned an empty or unusable resume draft. Falling back to deterministic resume generation.",
            fallback_reason=ResumeFallbackReason.INVALID_AI_OUTPUT,
        )

    notes: dict[str, list[str]] = {
        "warnings": _clean_string_list(ai_output.warnings, limit=8),
        "truthfulness_notes": _clean_string_list(ai_output.truthfulness_notes, limit=8),
        "omitted_or_deemphasized_items": _clean_string_list(
            ai_output.omitted_or_deemphasized_items,
            limit=12,
        ),
        "generation_notes": [],
    }
    if ignored_unknown_references:
        notes["generation_notes"].append(
            "Some AI-selected source references were ignored because they did not exist in the supplied profile.",
        )
    if filtered_unknown_skills:
        notes["generation_notes"].append(
            "Some AI-selected skills were dropped because they were not explicitly present in the candidate profile.",
        )
    if filtered_unknown_keywords:
        notes["generation_notes"].append(
            "Some AI-selected keywords were dropped because they were not explicitly present in the job posting.",
        )
    if used_guardrail_bullet_fallback:
        notes["generation_notes"].append(
            "Some tailored bullets were replaced with source-grounded fallback content because explicit provenance was incomplete.",
        )
    if used_guardrail_summary_fallback:
        notes["generation_notes"].append(
            "The AI professional summary was replaced with a safer grounded summary because it overreached beyond the supplied evidence.",
        )
    if used_guardrail_fit_summary_fallback:
        notes["generation_notes"].append(
            "The AI fit summary was replaced with a safer grounded summary because it was not sufficiently supported by the available evidence.",
        )

    resume_draft = ResumeDraft(
        header=_build_resume_header(candidate_profile, job_posting),
        target_job_title=job_posting.title,
        target_company_name=job_posting.company_name,
        fit_summary=fit_summary,
        professional_summary=professional_summary,
        selected_skills=selected_skills,
        selected_experience_entries=selected_experience_entries,
        selected_project_entries=selected_project_entries,
        selected_education_entries=selected_education_entries,
        selected_language_entries=selected_language_entries,
        selected_certificate_entries=selected_certificate_entries,
        selected_keywords=selected_keywords,
        keyword_usage=keyword_usage,
    )

    return resume_draft, notes


def generate_resume_artifacts(
    candidate_profile: CandidateProfile,
    job_posting: JobPosting,
    match_result: MatchResult | None,
    *,
    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem] | None = None,
    candidate_profile_understanding: CandidateProfileUnderstanding | None = None,
) -> dict[str, object]:
    """Generate a truthful-first ResumeDraft and ChangeReport from saved inputs."""
    resolved_requirement_priority_lookup = requirement_priority_lookup or {}
    resolved_candidate_profile_understanding = candidate_profile_understanding

    if _has_configured_openai_api_key():
        if not resolved_requirement_priority_lookup:
            resolved_requirement_priority_lookup = get_requirement_priority_lookup(job_posting)
        if resolved_candidate_profile_understanding is None:
            resolved_candidate_profile_understanding = get_candidate_profile_understanding(candidate_profile)

    semantic_context = _build_resume_semantic_context(
        job_posting,
        requirement_priority_lookup=resolved_requirement_priority_lookup,
        candidate_profile_understanding=resolved_candidate_profile_understanding,
    )
    match_result_source = (
        ResumeMatchResultSource.PROVIDED
        if match_result is not None
        else ResumeMatchResultSource.COMPUTED
    )
    effective_match_result = match_result or analyze_match_basic(
        MatchAnalysisRequest(
            candidate_profile=candidate_profile,
            job_posting=job_posting,
        ),
        requirement_priority_lookup=semantic_context.requirement_priority_lookup,
        candidate_profile_understanding=semantic_context.candidate_profile_understanding,
    )

    generation_notes: list[str] = []
    fallback_reason: ResumeFallbackReason | None = None

    try:
        ai_output = generate_resume_tailoring_with_openai(
            candidate_profile,
            job_posting,
            effective_match_result,
            candidate_profile_understanding=semantic_context.candidate_profile_understanding,
            reportable_offer_terms=semantic_context.reportable_job_keywords,
            requirement_reportable_terms_lookup=semantic_context.requirement_reportable_terms_lookup,
        )
        resume_draft, ai_notes = _build_ai_assisted_resume_draft(
            candidate_profile,
            job_posting,
            effective_match_result,
            ai_output,
            semantic_context,
        )
        generation_mode = ResumeGenerationMode.OPENAI_STRUCTURED
        for note in ai_notes["generation_notes"]:
            _append_unique(generation_notes, note)
        logger.info(
            "Resume generation completed with structured OpenAI output.",
            extra={
                "generation_mode": generation_mode.value,
                "match_result_source": match_result_source.value,
                "selected_experience_entries": len(resume_draft.selected_experience_entries),
                "selected_project_entries": len(resume_draft.selected_project_entries),
            },
        )
        change_report = _build_change_report(
            candidate_profile,
            effective_match_result,
            resume_draft,
            semantic_context.reportable_job_keywords,
            extra_warnings=[*ai_notes["warnings"], *generation_notes],
            extra_blocked_items=ai_notes["truthfulness_notes"],
            extra_omitted_items=ai_notes["omitted_or_deemphasized_items"],
        )
    except ResumeTailoringOpenAIError as exc:
        fallback_reason = exc.fallback_reason
        _append_unique(generation_notes, exc.message)
        resume_draft = _build_rule_based_resume_draft(
            candidate_profile,
            job_posting,
            effective_match_result,
            semantic_context,
        )
        generation_mode = ResumeGenerationMode.RULE_BASED_FALLBACK
        logger.warning(
            "Resume generation fell back to deterministic mode.",
            extra={
                "generation_mode": generation_mode.value,
                "match_result_source": match_result_source.value,
                "fallback_reason": fallback_reason.value,
                "details": exc.details,
            },
        )
        change_report = _build_change_report(
            candidate_profile,
            effective_match_result,
            resume_draft,
            semantic_context.reportable_job_keywords,
            extra_warnings=generation_notes,
        )

    return {
        "resume_draft": resume_draft,
        "change_report": change_report,
        "generation_mode": generation_mode,
        "match_result_source": match_result_source,
        "fallback_reason": fallback_reason,
        "generation_notes": generation_notes,
    }
