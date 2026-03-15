from __future__ import annotations

from app.models.analysis import MatchAnalysisRequest
from app.models.job import Requirement
from app.models.match import MatchResult, RequirementMatch


def _normalize(value: str) -> str:
    return value.strip().lower()


def _append_unique(target: list[str], value: str) -> None:
    if value and value not in target:
        target.append(value)


def _extend_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        _append_unique(target, value)


def _create_evidence_entry() -> dict[str, list[str]]:
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


def _calculate_fit_classification(overall_score: float) -> str:
    if overall_score >= 0.75:
        return "high"
    if overall_score >= 0.4:
        return "medium"
    return "low"


def _build_recommendation(fit_classification: str) -> str:
    recommendation_by_fit = {
        "high": "generate",
        "medium": "generate_with_caution",
        "low": "do_not_recommend",
    }
    return recommendation_by_fit[fit_classification]


def _build_strengths(
    payload: MatchAnalysisRequest,
    requirement_matches: list[RequirementMatch],
    keyword_coverage: list[str],
) -> list[str]:
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
    covered_keywords = ", ".join(keyword_coverage) if keyword_coverage else "none"
    return (
        f"Profile fit for '{job_title}' is {fit_classification} with score "
        f"{overall_score:.2f}. Requirements summary: {matched_requirements_count} matched, "
        f"{partial_requirements_count} partial, {missing_requirements_count} missing out of "
        f"{total_requirements}. Recommendation: {recommendation}. Covered job keywords: "
        f"{covered_keywords}."
    )


def analyze_match_basic(payload: MatchAnalysisRequest) -> MatchResult:
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
    if total_requirements > 0:
        overall_score = (
            matched_requirements_count + 0.5 * partial_requirements_count
        ) / total_requirements
    else:
        overall_score = 0.0

    rounded_score = round(overall_score, 2)
    fit_classification = _calculate_fit_classification(rounded_score)

    recommendation = _build_recommendation(fit_classification)

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
