"""Keyword-based matching service that builds MatchResult and RequirementMatch."""

from __future__ import annotations

from app.models.analysis import MatchAnalysisRequest
from app.models.job import Requirement
from app.models.match import MatchResult, RequirementMatch

_IMPORTANCE_WEIGHTS = {
    "high": 1.0,
    "medium": 0.7,
    "low": 0.4,
}
_REQUIREMENT_TYPE_MULTIPLIERS = {
    "must_have": 1.4,
    "nice_to_have": 1.0,
}
_MATCH_STATUS_SCORES = {
    "matched": 1.0,
    "partial": 0.5,
    "missing": 0.0,
}
_HIGH_FIT_THRESHOLD = 0.75
_MEDIUM_FIT_THRESHOLD = 0.4


def _normalize(value: str) -> str:
    """Normalize a keyword-like string for case-insensitive matching."""
    return value.strip().lower()


def _append_unique(target: list[str], value: str) -> None:
    """Append a string to a list only when it is non-empty and not duplicated."""
    if value and value not in target:
        target.append(value)


def _extend_unique(target: list[str], values: list[str]) -> None:
    """Extend a list with unique string values while preserving original order."""
    for value in values:
        _append_unique(target, value)


def _create_evidence_entry() -> dict[str, list[str]]:
    """Create the empty evidence bucket used for a single normalized keyword."""
    return {
        "matched_skill_names": [],
        "matched_experience_ids": [],
        "matched_project_ids": [],
        "evidence_texts": [],
    }


def _register_keyword_evidence(
    evidence_index: dict[str, dict[str, list[str]]],
    candidate_keywords: set[str],
    keyword: str,
    *,
    skill_name: str | None = None,
    experience_id: str | None = None,
    project_id: str | None = None,
    evidence_text: str | None = None,
) -> None:
    """Attach evidence for a candidate keyword found in skills, jobs or projects."""
    normalized_keyword = _normalize(keyword)
    if not normalized_keyword:
        return

    candidate_keywords.add(normalized_keyword)
    entry = evidence_index.setdefault(normalized_keyword, _create_evidence_entry())

    if skill_name:
        _append_unique(entry["matched_skill_names"], skill_name)
    if experience_id:
        _append_unique(entry["matched_experience_ids"], experience_id)
    if project_id:
        _append_unique(entry["matched_project_ids"], project_id)
    if evidence_text:
        _append_unique(entry["evidence_texts"], evidence_text)


def _build_candidate_evidence_index(payload: MatchAnalysisRequest) -> tuple[set[str], dict[str, dict[str, list[str]]]]:
    """Index candidate evidence by normalized keywords for later requirement matching."""
    candidate = payload.candidate_profile
    experience_ids = {experience.id for experience in candidate.experience_entries}
    project_ids = {project.id for project in candidate.project_entries}

    candidate_keywords: set[str] = set()
    evidence_index: dict[str, dict[str, list[str]]] = {}

    for skill in candidate.skill_entries:
        skill_evidence_text = f"Skill '{skill.name}' is listed in the candidate profile."
        _register_keyword_evidence(
            evidence_index,
            candidate_keywords,
            skill.name,
            skill_name=skill.name,
            evidence_text=skill_evidence_text,
        )
        for alias in skill.aliases:
            _register_keyword_evidence(
                evidence_index,
                candidate_keywords,
                alias,
                skill_name=skill.name,
                evidence_text=f"Skill alias '{alias}' points to '{skill.name}'.",
            )
        for evidence_source in skill.evidence_sources:
            if evidence_source in experience_ids:
                _register_keyword_evidence(
                    evidence_index,
                    candidate_keywords,
                    skill.name,
                    skill_name=skill.name,
                    experience_id=evidence_source,
                    evidence_text=skill_evidence_text,
                )
            elif evidence_source in project_ids:
                _register_keyword_evidence(
                    evidence_index,
                    candidate_keywords,
                    skill.name,
                    skill_name=skill.name,
                    project_id=evidence_source,
                    evidence_text=skill_evidence_text,
                )

    for experience in candidate.experience_entries:
        for technology in experience.technologies_used:
            _register_keyword_evidence(
                evidence_index,
                candidate_keywords,
                technology,
                experience_id=experience.id,
                evidence_text=(
                    f"Experience '{experience.position_title}' at "
                    f"'{experience.company_name}' includes '{technology}'."
                ),
            )
        for keyword in experience.keywords:
            _register_keyword_evidence(
                evidence_index,
                candidate_keywords,
                keyword,
                experience_id=experience.id,
                evidence_text=(
                    f"Experience '{experience.position_title}' at "
                    f"'{experience.company_name}' includes keyword '{keyword}'."
                ),
            )

    for project in candidate.project_entries:
        for technology in project.technologies_used:
            _register_keyword_evidence(
                evidence_index,
                candidate_keywords,
                technology,
                project_id=project.id,
                evidence_text=f"Project '{project.project_name}' uses '{technology}'.",
            )
        for keyword in project.keywords:
            _register_keyword_evidence(
                evidence_index,
                candidate_keywords,
                keyword,
                project_id=project.id,
                evidence_text=f"Project '{project.project_name}' includes keyword '{keyword}'.",
            )

    for language in candidate.language_entries:
        _register_keyword_evidence(
            evidence_index,
            candidate_keywords,
            language.language_name,
            evidence_text=(
                f"Language '{language.language_name}' is listed with level "
                f"'{language.proficiency_level}'."
            ),
        )
        _register_keyword_evidence(
            evidence_index,
            candidate_keywords,
            language.proficiency_level,
            evidence_text=(
                f"Language proficiency '{language.proficiency_level}' is listed "
                f"for '{language.language_name}'."
            ),
        )

    return candidate_keywords, evidence_index


def _build_explanation(
    requirement_text: str,
    status: str,
    matched_keywords: list[str],
    missing_keywords: list[str],
    evidence_texts: list[str],
) -> str:
    """Generate a short human-readable explanation for a requirement match."""
    evidence_preview = "; ".join(evidence_texts[:2])

    if status == "matched":
        explanation = (
            f"Status matched because all extracted keywords from requirement "
            f"'{requirement_text}' were found in the candidate profile: "
            f"{', '.join(matched_keywords)}."
        )
    elif status == "partial":
        explanation = (
            f"Status partial because requirement '{requirement_text}' is only "
            f"partially covered. Matched keywords: {', '.join(matched_keywords)}. "
            f"Missing keywords: {', '.join(missing_keywords)}."
        )
    else:
        if missing_keywords:
            explanation = (
                f"Status missing because requirement '{requirement_text}' has no "
                f"keyword evidence in the candidate profile. Missing keywords: "
                f"{', '.join(missing_keywords)}."
            )
        else:
            explanation = (
                f"Status missing because requirement '{requirement_text}' has no "
                f"extracted keywords, so the current keyword matcher cannot verify it."
            )

    if evidence_preview:
        explanation = f"{explanation} Evidence: {evidence_preview}"

    return explanation


def _build_requirement_match(
    requirement: Requirement,
    evidence_index: dict[str, dict[str, list[str]]],
) -> RequirementMatch:
    """Build a single requirement-level match with evidence and explainability."""
    raw_keywords: list[str] = []
    normalized_keywords: list[str] = []

    for keyword in requirement.extracted_keywords:
        stripped_keyword = keyword.strip()
        normalized_keyword = _normalize(keyword)
        if stripped_keyword and normalized_keyword not in normalized_keywords:
            raw_keywords.append(stripped_keyword)
            normalized_keywords.append(normalized_keyword)

    matched_keywords_normalized: list[str] = []
    matched_skill_names: list[str] = []
    matched_experience_ids: list[str] = []
    matched_project_ids: list[str] = []
    evidence_texts: list[str] = []

    for normalized_keyword in normalized_keywords:
        evidence = evidence_index.get(normalized_keyword)
        if not evidence:
            continue
        matched_keywords_normalized.append(normalized_keyword)
        _extend_unique(matched_skill_names, evidence["matched_skill_names"])
        _extend_unique(matched_experience_ids, evidence["matched_experience_ids"])
        _extend_unique(matched_project_ids, evidence["matched_project_ids"])
        _extend_unique(evidence_texts, evidence["evidence_texts"])

    matched_keywords = [
        keyword for keyword in raw_keywords if _normalize(keyword) in matched_keywords_normalized
    ]
    missing_keywords = [
        keyword for keyword in raw_keywords if _normalize(keyword) not in matched_keywords_normalized
    ]

    if not normalized_keywords:
        status = "missing"
    elif len(matched_keywords_normalized) == len(normalized_keywords):
        status = "matched"
    elif matched_keywords_normalized:
        status = "partial"
    else:
        status = "missing"

    return RequirementMatch(
        requirement_id=requirement.id,
        match_status=status,
        matched_experience_ids=matched_experience_ids,
        matched_project_ids=matched_project_ids,
        matched_skill_names=matched_skill_names,
        evidence_texts=evidence_texts,
        explanation=_build_explanation(
            requirement.text,
            status,
            matched_keywords,
            missing_keywords,
            evidence_texts,
        ),
        missing_elements=missing_keywords,
    )


def _get_importance_weight(importance: str) -> float:
    """Return the score weight for requirement importance.

    Args:
        importance: Raw requirement importance value.

    Returns:
        Float weight used in the weighted score. Unknown values fall back to medium.
    """
    normalized_importance = _normalize(importance) if importance else ""
    return _IMPORTANCE_WEIGHTS.get(normalized_importance, _IMPORTANCE_WEIGHTS["medium"])


def _get_requirement_type_multiplier(requirement_type: str) -> float:
    """Return the score multiplier for requirement type.

    Args:
        requirement_type: Raw requirement type value.

    Returns:
        Float multiplier used in the weighted score. Unknown values fall back to nice-to-have.
    """
    normalized_requirement_type = _normalize(requirement_type) if requirement_type else ""
    return _REQUIREMENT_TYPE_MULTIPLIERS.get(
        normalized_requirement_type,
        _REQUIREMENT_TYPE_MULTIPLIERS["nice_to_have"],
    )


def _get_match_status_score(match_status: str) -> float:
    """Return the numeric score for a requirement match status.

    Args:
        match_status: Match status such as matched, partial or missing.

    Returns:
        Float score contribution for the matched status. Unknown values fall back to missing.
    """
    normalized_match_status = _normalize(match_status) if match_status else ""
    return _MATCH_STATUS_SCORES.get(normalized_match_status, _MATCH_STATUS_SCORES["missing"])


def _calculate_requirement_weight(requirement: Requirement) -> float:
    """Calculate the weighted-score importance of a single requirement.

    Args:
        requirement: Requirement being scored.

    Returns:
        Combined weight derived from requirement importance and requirement type.
    """
    return (
        _get_importance_weight(requirement.importance)
        * _get_requirement_type_multiplier(requirement.requirement_type)
    )


def _calculate_weighted_score(
    requirements: list[Requirement],
    requirement_matches: list[RequirementMatch],
) -> float:
    """Calculate the weighted overall score across all requirements.

    Args:
        requirements: Job requirements used to derive weights.
        requirement_matches: Requirement-level match results.

    Returns:
        Weighted score in the 0.0-1.0 range.
    """
    weighted_score_sum = 0.0
    total_weight = 0.0

    for requirement, requirement_match in zip(requirements, requirement_matches):
        requirement_weight = _calculate_requirement_weight(requirement)
        total_weight += requirement_weight
        weighted_score_sum += requirement_weight * _get_match_status_score(
            requirement_match.match_status
        )

    if total_weight == 0:
        return 0.0

    return weighted_score_sum / total_weight


def _calculate_fit_classification(overall_score: float) -> str:
    """Classify the overall score using explicit high and medium thresholds.

    Args:
        overall_score: Rounded weighted score in the 0.0-1.0 range.

    Returns:
        Fit classification string: high, medium or low.
    """
    if overall_score >= _HIGH_FIT_THRESHOLD:
        return "high"
    if overall_score >= _MEDIUM_FIT_THRESHOLD:
        return "medium"
    return "low"


def _build_recommendation(fit_classification: str) -> str:
    """Map fit classification to the base recommendation.

    Args:
        fit_classification: Final or pre-gated fit classification.

    Returns:
        Recommendation string aligned with the fit classification.
    """
    recommendation_by_fit = {
        "high": "generate",
        "medium": "generate_with_caution",
        "low": "do_not_recommend",
    }
    return recommendation_by_fit[fit_classification]


def _count_missing_must_have_requirements(
    requirements: list[Requirement],
    requirement_matches: list[RequirementMatch],
) -> int:
    """Count must-have requirements that remain completely missing.

    Args:
        requirements: Source job requirements.
        requirement_matches: Requirement-level match results.

    Returns:
        Number of must-have requirements with status missing.
    """
    return sum(
        1
        for requirement, requirement_match in zip(requirements, requirement_matches)
        if _normalize(requirement.requirement_type) == "must_have"
        and requirement_match.match_status == "missing"
    )


def _has_missing_high_importance_must_have(
    requirements: list[Requirement],
    requirement_matches: list[RequirementMatch],
) -> bool:
    """Check whether any critical must-have requirement is fully missing.

    Args:
        requirements: Source job requirements.
        requirement_matches: Requirement-level match results.

    Returns:
        True when at least one high-importance must-have is missing.
    """
    return any(
        _normalize(requirement.requirement_type) == "must_have"
        and _normalize(requirement.importance) == "high"
        and requirement_match.match_status == "missing"
        for requirement, requirement_match in zip(requirements, requirement_matches)
    )


def _apply_fit_classification_gating(
    fit_classification: str,
    requirements: list[Requirement],
    requirement_matches: list[RequirementMatch],
) -> str:
    """Apply simple gating rules that cap misleadingly optimistic fit labels.

    Args:
        fit_classification: Score-based fit classification before gating.
        requirements: Source job requirements.
        requirement_matches: Requirement-level match results.

    Returns:
        Possibly downgraded fit classification after applying critical-missing rules.
    """
    if (
        fit_classification == "high"
        and _has_missing_high_importance_must_have(requirements, requirement_matches)
    ):
        return "medium"

    return fit_classification


def _apply_recommendation_gating(
    recommendation: str,
    requirements: list[Requirement],
    requirement_matches: list[RequirementMatch],
) -> str:
    """Apply must-have gating so critical gaps cannot keep an optimistic recommendation.

    Args:
        recommendation: Base recommendation derived from fit classification.
        requirements: Source job requirements.
        requirement_matches: Requirement-level match results.

    Returns:
        Recommendation limited by the number of missing must-have requirements.
    """
    missing_must_have_count = _count_missing_must_have_requirements(
        requirements,
        requirement_matches,
    )

    if missing_must_have_count >= 2:
        return "do_not_recommend"
    if missing_must_have_count >= 1 and recommendation == "generate":
        return "generate_with_caution"

    return recommendation


def _build_strengths(
    payload: MatchAnalysisRequest,
    requirement_matches: list[RequirementMatch],
    keyword_coverage: list[str],
) -> list[str]:
    """Build a short list of candidate strengths relative to the job posting."""
    strengths: list[str] = []

    for requirement, requirement_match in zip(payload.job_posting.requirements, requirement_matches):
        if requirement_match.match_status == "matched":
            _append_unique(strengths, f"Matched requirement: {requirement.text}")

    if keyword_coverage:
        _append_unique(
            strengths,
            f"Covered job keywords: {', '.join(keyword_coverage)}",
        )

    return strengths


def _build_gaps(
    payload: MatchAnalysisRequest,
    requirement_matches: list[RequirementMatch],
) -> list[str]:
    """Build a short list of requirement gaps and partial misses."""
    gaps: list[str] = []

    for requirement, requirement_match in zip(payload.job_posting.requirements, requirement_matches):
        if requirement_match.match_status == "partial":
            _append_unique(
                gaps,
                (
                    f"Partially matched requirement: {requirement.text}. "
                    f"Missing: {', '.join(requirement_match.missing_elements)}"
                ),
            )
        elif requirement_match.match_status == "missing":
            if requirement_match.missing_elements:
                _append_unique(
                    gaps,
                    (
                        f"Missing requirement: {requirement.text}. "
                        f"Missing: {', '.join(requirement_match.missing_elements)}"
                    ),
                )
            else:
                _append_unique(
                    gaps,
                    f"Missing requirement: {requirement.text}. No extracted keywords available.",
                )

    return gaps


def _build_final_summary(
    job_title: str,
    overall_score: float,
    fit_classification: str,
    recommendation: str,
    matched_requirements_count: int,
    partial_requirements_count: int,
    missing_requirements_count: int,
    total_requirements: int,
    keyword_coverage: list[str],
) -> str:
    """Build the final user-facing summary of the matching result."""
    covered_keywords = ", ".join(keyword_coverage) if keyword_coverage else "none"
    return (
        f"Profile fit for '{job_title}' is {fit_classification} with score "
        f"{overall_score:.2f}. Requirements summary: {matched_requirements_count} matched, "
        f"{partial_requirements_count} partial, {missing_requirements_count} missing out of "
        f"{total_requirements}. Recommendation: {recommendation}. Covered job keywords: "
        f"{covered_keywords}."
    )


def analyze_match_basic(payload: MatchAnalysisRequest) -> MatchResult:
    """Analyze candidate-vs-job fit using keyword evidence, weighted scoring and gating.

    Args:
        payload: Candidate profile and job posting used for the analysis.

    Returns:
        MatchResult with requirement-level evidence, weighted score and final recommendation.
    """
    candidate_keywords, evidence_index = _build_candidate_evidence_index(payload)
    requirement_matches = [
        _build_requirement_match(requirement, evidence_index)
        for requirement in payload.job_posting.requirements
    ]

    matched_requirements_count = sum(
        1 for requirement_match in requirement_matches if requirement_match.match_status == "matched"
    )
    partial_requirements_count = sum(
        1 for requirement_match in requirement_matches if requirement_match.match_status == "partial"
    )
    missing_requirements_count = sum(
        1 for requirement_match in requirement_matches if requirement_match.match_status == "missing"
    )

    total_requirements = len(payload.job_posting.requirements)
    overall_score = _calculate_weighted_score(
        payload.job_posting.requirements,
        requirement_matches,
    )
    rounded_score = round(overall_score, 2)
    fit_classification = _apply_fit_classification_gating(
        _calculate_fit_classification(rounded_score),
        payload.job_posting.requirements,
        requirement_matches,
    )

    recommendation = _apply_recommendation_gating(
        _build_recommendation(fit_classification),
        payload.job_posting.requirements,
        requirement_matches,
    )

    keyword_coverage = [
        keyword
        for keyword in payload.job_posting.keywords
        if _normalize(keyword) in candidate_keywords
    ]

    strengths = _build_strengths(payload, requirement_matches, keyword_coverage)
    gaps = _build_gaps(payload, requirement_matches)

    return MatchResult(
        overall_score=rounded_score,
        fit_classification=fit_classification,
        recommendation=recommendation,
        requirement_matches=requirement_matches,
        strengths=strengths,
        gaps=gaps,
        keyword_coverage=keyword_coverage,
        final_summary=_build_final_summary(
            payload.job_posting.title,
            rounded_score,
            fit_classification,
            recommendation,
            matched_requirements_count,
            partial_requirements_count,
            missing_requirements_count,
            total_requirements,
            keyword_coverage,
        ),
    )
