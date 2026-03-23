"""Category-aware deterministic matching service that builds MatchResult and RequirementMatch."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re

from app.models.analysis import MatchAnalysisRequest
from app.models.job import JobPosting, Requirement
from app.models.match import MatchResult, RequirementMatch
from app.services.openai_education_match_service import (
    EducationRequirementMatchOpenAIError,
    OpenAIEducationRequirementMatchOutput,
    evaluate_education_requirement_with_openai,
)
from app.services.openai_requirement_type_service import (
    RequirementTypeClassificationOpenAIError,
    evaluate_requirement_type_with_openai,
)

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
_CATEGORY_SCORE_MULTIPLIERS = {
    "technical_skill": 1.0,
    "experience": 1.0,
    "education": 0.9,
    "language": 0.8,
    "domain": 0.7,
    "application_constraint": 0.0,
    "soft_signal": 0.15,
    "low_signal": 0.0,
    "eligibility": 0.0,
    "soft_skill": 0.15,
}
_HIGH_FIT_THRESHOLD = 0.75
_MEDIUM_FIT_THRESHOLD = 0.4

_TOKEN_RE = re.compile(r"[\w\+#]+", flags=re.UNICODE)
_YEARS_RE = re.compile(r"(\d+(?:[\.,]\d+)?)\s*\+?\s*(?:years?|yrs?)", flags=re.IGNORECASE)

_LANGUAGE_SCORE_BY_LEVEL = {
    "a1": 1,
    "a2": 2,
    "b1": 3,
    "b2": 4,
    "c1": 5,
    "c2": 6,
    "communicative": 3,
    "communicative level": 3,
    "conversational": 3,
    "intermediate": 4,
    "upper intermediate": 4,
    "advanced": 5,
    "professional": 5,
    "professional working": 5,
    "fluent": 6,
    "native": 7,
}
_KNOWN_LANGUAGE_NAMES = {
    "english",
    "polish",
    "german",
    "french",
    "spanish",
    "italian",
    "ukrainian",
    "russian",
    "dutch",
    "swedish",
    "norwegian",
    "danish",
    "finnish",
    "czech",
}
_EXPERIENCE_NOISE_KEYWORDS = {
    "experience",
    "commercial",
    "hands-on",
    "hands",
    "practical",
    "knowledge",
    "background",
    "years",
    "year",
    "with",
    "in",
    "of",
}
_TOKEN_STOPWORDS = {
    "and",
    "or",
    "the",
    "a",
    "an",
    "to",
    "of",
    "with",
    "in",
    "for",
    "on",
    "is",
    "are",
    "be",
    "up",
    "valid",
    "required",
    "certificate",
    "certification",
    "license",
    "licence",
    "level",
    "knowledge",
    "experience",
}
_LOW_SIGNAL_TOKENS = {
    "communication",
    "teamwork",
    "team",
    "player",
    "motivated",
    "motivation",
    "proactive",
    "flexible",
    "flexibility",
    "organized",
    "organisation",
    "organization",
    "responsible",
    "independent",
    "detail",
    "attitude",
    "positive",
    "willingness",
    "learn",
}
_LOW_SIGNAL_PHRASES = {
    "good communication",
    "communication skills",
    "team player",
    "positive attitude",
    "willingness to learn",
    "ability to learn",
    "attention to detail",
}
_APPLICATION_CONSTRAINT_PHRASES = {
    "work authorization",
    "authorized to work",
    "right to work",
    "visa sponsorship",
    "security clearance",
    "background check",
    "criminal record",
    "student status",
    "currently enrolled",
    "driving license",
    "driver license",
    "driver's license",
    "prawo jazdy",
    "class b",
    "class c",
    "class d",
    "hours per week",
    "hours/week",
    "h/week",
    "per week",
    "available from",
    "start date",
    "notice period",
    "minimum 6 months",
    "6-month commitment",
    "for 6 months",
    "on-site",
    "onsite",
    "office presence",
    "relocation",
    "relocate",
}
_EDUCATION_TERMS = {
    "degree",
    "bachelor",
    "bachelors",
    "master",
    "masters",
    "engineer",
    "engineering",
    "diploma",
    "university",
    "college",
    "licencjat",
    "inzynier",
    "msc",
    "bsc",
    "bs",
    "ms",
}
_EDUCATION_FIELD_GROUPS = {
    "automation_related": {"automation", "robotics", "robotic", "control", "mechatronics", "plc"},
    "electrical_related": {"electrical", "electronics", "electrotechnics", "electronic", "power", "instrumentation"},
    "software_related": {"computer", "software", "informatics", "programming", "it", "information", "systems"},
    "mechanical_related": {"mechanical", "manufacturing", "industrial", "production"},
}
_BROAD_STEM_TOKENS = {
    "engineering",
    "engineer",
    "technical",
    "technology",
    "stem",
    "science",
    "scientific",
    "mathematics",
    "math",
    "physics",
    "biotechnology",
    "chemistry",
}


@dataclass(slots=True)
class MatchEvidenceContext:
    payload: MatchAnalysisRequest
    candidate_keywords: set[str]
    evidence_index: dict[str, dict[str, list[str]]]
    candidate_texts: list[str]
    skill_years_index: dict[str, float]
    language_levels: dict[str, str]


def _normalize(value: str | None) -> str:
    """Normalize a string for case-insensitive comparisons."""
    if not value:
        return ""
    return value.strip().lower()


def _tokenize(text: str | None) -> list[str]:
    """Split text into normalized tokens that are safe for lightweight heuristics."""
    if not text:
        return []
    return [token.strip("_") for token in _TOKEN_RE.findall(text.lower()) if token.strip("_")]


def _append_unique(target: list[str], value: str | None) -> None:
    """Append a string to a list only when it is non-empty and not duplicated."""
    if value and value not in target:
        target.append(value)


def _extend_unique(target: list[str], values: list[str]) -> None:
    """Extend a list with unique string values while preserving original order."""
    for value in values:
        _append_unique(target, value)


def _collect_text_values(values: list[str | None]) -> list[str]:
    """Collect non-empty text values while preserving order."""
    collected: list[str] = []
    for value in values:
        if value and value.strip():
            collected.append(value.strip())
    return collected


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
    """Attach evidence for a candidate keyword found in profile data."""
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


def _register_certificate_evidence(
    evidence_index: dict[str, dict[str, list[str]]],
    candidate_keywords: set[str],
    certificate_name: str,
    *,
    issuer: str | None,
    notes: str | None,
) -> None:
    """Register certificate-derived evidence for formal and technical requirements."""
    evidence_text = f"Certificate '{certificate_name}' is listed in the candidate profile."
    for value in [certificate_name, issuer, notes]:
        if not value or not value.strip():
            continue
        _register_keyword_evidence(
            evidence_index,
            candidate_keywords,
            value,
            evidence_text=evidence_text,
        )
        for token in _tokenize(value):
            if len(token) <= 2 or token in _TOKEN_STOPWORDS:
                continue
            _register_keyword_evidence(
                evidence_index,
                candidate_keywords,
                token,
                evidence_text=evidence_text,
            )


def _build_candidate_evidence_context(payload: MatchAnalysisRequest) -> MatchEvidenceContext:
    """Build reusable candidate evidence for category-aware requirement evaluators."""
    candidate = payload.candidate_profile
    experience_ids = {experience.id for experience in candidate.experience_entries}
    project_ids = {project.id for project in candidate.project_entries}

    candidate_keywords: set[str] = set()
    evidence_index: dict[str, dict[str, list[str]]] = {}
    skill_years_index: dict[str, float] = {}
    language_levels: dict[str, str] = {}

    for skill in candidate.skill_entries:
        skill_evidence_text = f"Skill '{skill.name}' is listed in the candidate profile."
        _register_keyword_evidence(
            evidence_index,
            candidate_keywords,
            skill.name,
            skill_name=skill.name,
            evidence_text=skill_evidence_text,
        )
        if skill.years_of_experience is not None:
            for name in [skill.name, *skill.aliases]:
                normalized_name = _normalize(name)
                if not normalized_name:
                    continue
                current_years = skill_years_index.get(normalized_name, 0.0)
                skill_years_index[normalized_name] = max(current_years, float(skill.years_of_experience))
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
        normalized_language = _normalize(language.language_name)
        if normalized_language:
            language_levels[normalized_language] = language.proficiency_level
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

    for certificate in candidate.certificate_entries:
        _register_certificate_evidence(
            evidence_index,
            candidate_keywords,
            certificate.certificate_name,
            issuer=certificate.issuer,
            notes=certificate.notes,
        )

    candidate_texts = _collect_text_values(
        [
            candidate.professional_summary_base,
            *candidate.target_roles,
            *[
                value
                for experience in candidate.experience_entries
                for value in [
                    experience.position_title,
                    experience.company_name,
                    *experience.responsibilities,
                    *experience.achievements,
                    *experience.technologies_used,
                    *experience.keywords,
                ]
            ],
            *[
                value
                for project in candidate.project_entries
                for value in [
                    project.project_name,
                    project.role,
                    project.description,
                    *project.technologies_used,
                    *project.outcomes,
                    *project.keywords,
                ]
            ],
            *[skill.name for skill in candidate.skill_entries],
            *[
                value
                for education in candidate.education_entries
                for value in [
                    education.institution_name,
                    education.degree,
                    education.field_of_study,
                ]
            ],
            *[
                value
                for certificate in candidate.certificate_entries
                for value in [
                    certificate.certificate_name,
                    certificate.issuer,
                    certificate.notes,
                ]
            ],
            *[
                value
                for language in candidate.language_entries
                for value in [language.language_name, language.proficiency_level]
            ],
        ]
    )

    return MatchEvidenceContext(
        payload=payload,
        candidate_keywords=candidate_keywords,
        evidence_index=evidence_index,
        candidate_texts=candidate_texts,
        skill_years_index=skill_years_index,
        language_levels=language_levels,
    )


def _prepare_requirement_keywords(requirement: Requirement) -> tuple[list[str], list[str]]:
    """Prepare deduplicated raw and normalized requirement keywords."""
    raw_keywords: list[str] = []
    normalized_keywords: list[str] = []

    for keyword in requirement.extracted_keywords:
        stripped_keyword = keyword.strip()
        normalized_keyword = _normalize(keyword)
        if stripped_keyword and normalized_keyword not in normalized_keywords:
            raw_keywords.append(stripped_keyword)
            normalized_keywords.append(normalized_keyword)

    return raw_keywords, normalized_keywords


def _collect_keyword_evidence(
    raw_keywords: list[str],
    normalized_keywords: list[str],
    evidence_index: dict[str, dict[str, list[str]]],
) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str]]:
    """Collect all evidence buckets for a requirement's normalized keywords."""
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
    return (
        matched_keywords,
        missing_keywords,
        matched_skill_names,
        matched_experience_ids,
        matched_project_ids,
        evidence_texts,
    )


def _build_requirement_match(
    requirement: Requirement,
    *,
    match_status: str,
    explanation: str,
    matched_skill_names: list[str] | None = None,
    matched_experience_ids: list[str] | None = None,
    matched_project_ids: list[str] | None = None,
    evidence_texts: list[str] | None = None,
    missing_elements: list[str] | None = None,
) -> RequirementMatch:
    """Construct one RequirementMatch object with consistent defaults."""
    return RequirementMatch(
        requirement_id=requirement.id,
        match_status=match_status,
        matched_skill_names=matched_skill_names or [],
        matched_experience_ids=matched_experience_ids or [],
        matched_project_ids=matched_project_ids or [],
        evidence_texts=evidence_texts or [],
        explanation=explanation,
        missing_elements=missing_elements or [],
    )


def _requirement_text_blob(requirement: Requirement) -> str:
    """Return one normalized text blob used by lightweight classifiers."""
    return _normalize(f"{requirement.text} {' '.join(requirement.extracted_keywords)}")


def _looks_like_application_constraint_requirement(requirement: Requirement) -> bool:
    """Return whether the requirement behaves like a manual application constraint."""
    text = _requirement_text_blob(requirement)
    tokens = set(_tokenize(text))

    if any(phrase in text for phrase in _APPLICATION_CONSTRAINT_PHRASES):
        return True
    if "age" in tokens or ("18" in tokens and ("old" in tokens or "years" in tokens)):
        return True
    if {"authorized", "work"}.issubset(tokens) or {"right", "work"}.issubset(tokens):
        return True
    if {"student", "status"}.issubset(tokens) or "enrolled" in tokens or "enrollment" in tokens:
        return True
    if "availability" in tokens:
        return True
    if "available" in tokens and ({"week", "weeks", "month", "months", "from"} & tokens):
        return True
    if "relocation" in tokens or "relocate" in tokens or "onsite" in tokens:
        return True
    if {"on", "site"}.issubset(tokens):
        return True
    if ("hour" in tokens or "hours" in tokens) and "week" in tokens:
        return True
    if ("month" in tokens or "months" in tokens) and ({"minimum", "commitment", "duration", "available"} & tokens):
        return True
    if ("driving" in tokens and "license" in tokens) or ("prawo" in tokens and "jazdy" in tokens):
        return True
    return False


def _looks_like_education_requirement(requirement: Requirement) -> bool:
    """Return whether the requirement is education-like based on category or text."""
    normalized_category = _normalize(requirement.category)
    if normalized_category == "education":
        return True

    tokens = set(_tokenize(_requirement_text_blob(requirement)))
    return bool(tokens & _EDUCATION_TERMS)


def _looks_like_language_requirement(requirement: Requirement) -> bool:
    """Return whether the requirement looks like a language requirement."""
    normalized_category = _normalize(requirement.category)
    if normalized_category == "language":
        return True

    tokens = set(_tokenize(_requirement_text_blob(requirement)))
    return bool(tokens & _KNOWN_LANGUAGE_NAMES)


def _looks_like_experience_requirement(requirement: Requirement) -> bool:
    """Return whether the requirement looks like an experience requirement."""
    normalized_category = _normalize(requirement.category)
    if normalized_category in {"experience", "domain"}:
        return True

    text = _requirement_text_blob(requirement)
    tokens = set(_tokenize(text))
    if _YEARS_RE.search(text):
        return True
    return "experience" in tokens or "commercial" in tokens or "hands" in tokens


def _looks_like_soft_skill_requirement(requirement: Requirement) -> bool:
    """Return whether the requirement behaves like a soft-signal requirement."""
    normalized_category = _normalize(requirement.category)
    text = _requirement_text_blob(requirement)
    tokens = set(_tokenize(text))

    if normalized_category in {"soft_skill", "soft_signal"}:
        return True
    if any(phrase in text for phrase in _LOW_SIGNAL_PHRASES):
        return True
    return bool(tokens & _LOW_SIGNAL_TOKENS)


def _looks_like_low_signal_requirement(requirement: Requirement) -> bool:
    """Return whether the requirement is too generic to score strongly."""
    normalized_category = _normalize(requirement.category)
    text = _requirement_text_blob(requirement)
    tokens = set(_tokenize(text))

    if normalized_category in {"other", ""} and not requirement.extracted_keywords:
        return True
    if all(token in _LOW_SIGNAL_TOKENS or token in _TOKEN_STOPWORDS for token in tokens):
        return True
    return any(phrase in text for phrase in _LOW_SIGNAL_PHRASES)


def _determine_requirement_group_heuristic(requirement: Requirement) -> str:
    """Map parser categories and text heuristics to normalized matching groups."""
    normalized_category = _normalize(requirement.category)
    category_map = {
        "technology": "technical_skill",
        "experience": "experience",
        "language": "language",
        "education": "education",
        "soft_skill": "soft_signal",
        "soft_signal": "soft_signal",
        "domain": "domain",
    }

    if _looks_like_application_constraint_requirement(requirement):
        return "application_constraint"
    if _looks_like_education_requirement(requirement) and normalized_category not in {"technology", "domain"}:
        return "education"
    if _looks_like_language_requirement(requirement) and normalized_category not in {"technology", "domain"}:
        return "language"
    if normalized_category in category_map:
        return category_map[normalized_category]
    if _looks_like_experience_requirement(requirement):
        return "experience"
    if _looks_like_soft_skill_requirement(requirement):
        return "soft_signal"
    if _looks_like_low_signal_requirement(requirement):
        return "low_signal"
    if requirement.extracted_keywords:
        return "technical_skill"
    return "low_signal"


def _map_ai_requirement_type_to_group(requirement: Requirement, normalized_requirement_type: str) -> str:
    """Map AI normalized requirement types back to the internal matcher groups."""
    if normalized_requirement_type == "experience" and _normalize(requirement.category) == "domain":
        return "domain"
    return normalized_requirement_type


def _determine_requirement_group(requirement: Requirement, job_posting: JobPosting) -> str:
    """Determine the normalized requirement group using AI first and heuristic fallback."""
    fallback_group = _determine_requirement_group_heuristic(requirement)
    if not _has_configured_openai_api_key():
        return fallback_group

    try:
        ai_output = evaluate_requirement_type_with_openai(requirement, job_posting)
    except RequirementTypeClassificationOpenAIError:
        return fallback_group

    return _map_ai_requirement_type_to_group(requirement, ai_output.normalized_requirement_type)


def _evaluate_keyword_requirement(
    requirement: Requirement,
    context: MatchEvidenceContext,
    *,
    group_name: str,
) -> RequirementMatch:
    """Evaluate a technical or domain requirement with explicit keyword evidence."""
    raw_keywords, normalized_keywords = _prepare_requirement_keywords(requirement)
    if not normalized_keywords:
        return _build_requirement_match(
            requirement,
            match_status="not_verifiable",
            explanation=(
                f"Could not verify {group_name.replace('_', ' ')} requirement '{requirement.text}' "
                "because it has no extracted keywords for deterministic matching."
            ),
        )

    (
        matched_keywords,
        missing_keywords,
        matched_skill_names,
        matched_experience_ids,
        matched_project_ids,
        evidence_texts,
    ) = _collect_keyword_evidence(raw_keywords, normalized_keywords, context.evidence_index)

    if len(matched_keywords) == len(raw_keywords):
        status = "matched"
    elif matched_keywords:
        status = "partial"
    else:
        status = "missing"

    if status == "matched":
        explanation = (
            f"Matched {group_name.replace('_', ' ')} requirement '{requirement.text}' using keyword evidence: "
            f"{', '.join(matched_keywords)}."
        )
    elif status == "partial":
        explanation = (
            f"Partially matched {group_name.replace('_', ' ')} requirement '{requirement.text}'. "
            f"Matched: {', '.join(matched_keywords)}. Missing: {', '.join(missing_keywords)}."
        )
    else:
        explanation = (
            f"Missing {group_name.replace('_', ' ')} requirement '{requirement.text}'. "
            f"No evidence was found for: {', '.join(missing_keywords)}."
        )

    if evidence_texts:
        explanation = f"{explanation} Evidence: {'; '.join(evidence_texts[:2])}"

    return _build_requirement_match(
        requirement,
        match_status=status,
        explanation=explanation,
        matched_skill_names=matched_skill_names,
        matched_experience_ids=matched_experience_ids,
        matched_project_ids=matched_project_ids,
        evidence_texts=evidence_texts,
        missing_elements=missing_keywords if status in {"partial", "missing"} else [],
    )


def _extract_required_years(requirement: Requirement) -> float | None:
    """Extract a lightweight years-of-experience threshold from requirement text."""
    match = _YEARS_RE.search(_requirement_text_blob(requirement))
    if not match:
        return None

    raw_value = match.group(1).replace(",", ".")
    try:
        return float(raw_value)
    except ValueError:
        return None


def _filter_experience_keywords(raw_keywords: list[str]) -> tuple[list[str], list[str]]:
    """Drop generic experience markers so evaluation stays focused on the actual domain."""
    filtered_raw: list[str] = []
    filtered_normalized: list[str] = []

    for keyword in raw_keywords:
        normalized_keyword = _normalize(keyword)
        if normalized_keyword in _EXPERIENCE_NOISE_KEYWORDS:
            continue
        filtered_raw.append(keyword)
        filtered_normalized.append(normalized_keyword)

    return filtered_raw, filtered_normalized


def _evaluate_experience_requirement(
    requirement: Requirement,
    context: MatchEvidenceContext,
) -> RequirementMatch:
    """Evaluate experience requirements with keyword evidence and optional years thresholds."""
    raw_keywords, _ = _prepare_requirement_keywords(requirement)
    raw_keywords, normalized_keywords = _filter_experience_keywords(raw_keywords)
    required_years = _extract_required_years(requirement)

    if not normalized_keywords:
        return _build_requirement_match(
            requirement,
            match_status="not_verifiable",
            explanation=(
                f"Could not verify experience requirement '{requirement.text}' because it does not "
                "name a concrete skill, domain, or technology that can be checked deterministically."
            ),
        )

    (
        matched_keywords,
        missing_keywords,
        matched_skill_names,
        matched_experience_ids,
        matched_project_ids,
        evidence_texts,
    ) = _collect_keyword_evidence(raw_keywords, normalized_keywords, context.evidence_index)

    matched_years = [
        context.skill_years_index[normalized_keyword]
        for normalized_keyword in normalized_keywords
        if normalized_keyword in context.skill_years_index
    ]
    max_years = max(matched_years) if matched_years else None

    if not matched_keywords:
        status = "missing"
        explanation = (
            f"Missing experience requirement '{requirement.text}'. "
            f"No direct evidence was found for: {', '.join(missing_keywords)}."
        )
        return _build_requirement_match(
            requirement,
            match_status=status,
            explanation=explanation,
            missing_elements=missing_keywords,
        )

    if required_years is None:
        status = "matched" if len(matched_keywords) == len(raw_keywords) else "partial"
        explanation = (
            f"Matched experience evidence for '{requirement.text}' with keywords: {', '.join(matched_keywords)}."
            if status == "matched"
            else (
                f"Partially matched experience requirement '{requirement.text}'. "
                f"Matched: {', '.join(matched_keywords)}. Missing: {', '.join(missing_keywords)}."
            )
        )
        if evidence_texts:
            explanation = f"{explanation} Evidence: {'; '.join(evidence_texts[:2])}"
        return _build_requirement_match(
            requirement,
            match_status=status,
            explanation=explanation,
            matched_skill_names=matched_skill_names,
            matched_experience_ids=matched_experience_ids,
            matched_project_ids=matched_project_ids,
            evidence_texts=evidence_texts,
            missing_elements=missing_keywords if status == "partial" else [],
        )

    if max_years is None:
        explanation = (
            f"Partially matched experience requirement '{requirement.text}'. Evidence for "
            f"{', '.join(matched_keywords)} exists, but the profile does not record enough "
            f"years-of-experience data to verify the {required_years:g}+ years threshold."
        )
        if evidence_texts:
            explanation = f"{explanation} Evidence: {'; '.join(evidence_texts[:2])}"
        return _build_requirement_match(
            requirement,
            match_status="partial",
            explanation=explanation,
            matched_skill_names=matched_skill_names,
            matched_experience_ids=matched_experience_ids,
            matched_project_ids=matched_project_ids,
            evidence_texts=evidence_texts,
            missing_elements=[f"{required_years:g}+ years of documented experience"],
        )

    if max_years >= required_years and len(matched_keywords) == len(raw_keywords):
        explanation = (
            f"Matched experience requirement '{requirement.text}' with documented evidence for "
            f"{', '.join(matched_keywords)} and up to {max_years:g} years of experience."
        )
        if evidence_texts:
            explanation = f"{explanation} Evidence: {'; '.join(evidence_texts[:2])}"
        return _build_requirement_match(
            requirement,
            match_status="matched",
            explanation=explanation,
            matched_skill_names=matched_skill_names,
            matched_experience_ids=matched_experience_ids,
            matched_project_ids=matched_project_ids,
            evidence_texts=evidence_texts,
        )

    explanation = (
        f"Partially matched experience requirement '{requirement.text}'. Evidence exists for "
        f"{', '.join(matched_keywords)}, but the documented experience level reaches only "
        f"{max_years:g} years against the requested {required_years:g}+ years."
    )
    if missing_keywords:
        explanation = f"{explanation} Missing keyword evidence: {', '.join(missing_keywords)}."
    if evidence_texts:
        explanation = f"{explanation} Evidence: {'; '.join(evidence_texts[:2])}"
    return _build_requirement_match(
        requirement,
        match_status="partial",
        explanation=explanation,
        matched_skill_names=matched_skill_names,
        matched_experience_ids=matched_experience_ids,
        matched_project_ids=matched_project_ids,
        evidence_texts=evidence_texts,
        missing_elements=[f"{required_years:g}+ years of documented experience", *missing_keywords],
    )


def _extract_language_name(requirement: Requirement, context: MatchEvidenceContext) -> str | None:
    """Extract the target language name from keywords, text, or known candidate languages."""
    raw_keywords, _ = _prepare_requirement_keywords(requirement)
    for keyword in raw_keywords:
        normalized_keyword = _normalize(keyword)
        if normalized_keyword in _KNOWN_LANGUAGE_NAMES or normalized_keyword in context.language_levels:
            return keyword

    for token in _tokenize(_requirement_text_blob(requirement)):
        if token in _KNOWN_LANGUAGE_NAMES or token in context.language_levels:
            return token

    return None


def _extract_required_language_level(requirement: Requirement) -> tuple[str | None, int | None]:
    """Extract a lightweight language proficiency target from the requirement text."""
    text = _requirement_text_blob(requirement)
    for label, score in sorted(_LANGUAGE_SCORE_BY_LEVEL.items(), key=lambda item: len(item[0]), reverse=True):
        if label in text:
            return label, score
    return None, None


def _evaluate_language_requirement(
    requirement: Requirement,
    context: MatchEvidenceContext,
) -> RequirementMatch:
    """Evaluate language requirements using language name and proficiency levels."""
    language_name = _extract_language_name(requirement, context)
    if language_name is None:
        return _build_requirement_match(
            requirement,
            match_status="not_verifiable",
            explanation=(
                f"Could not verify language requirement '{requirement.text}' because the target language "
                "could not be identified deterministically."
            ),
        )

    normalized_language_name = _normalize(language_name)
    candidate_languages = context.payload.candidate_profile.language_entries
    if not candidate_languages:
        return _build_requirement_match(
            requirement,
            match_status="not_verifiable",
            explanation=(
                f"Could not verify language requirement '{requirement.text}' because the candidate profile "
                "does not contain language entries."
            ),
        )

    candidate_level = context.language_levels.get(normalized_language_name)
    if candidate_level is None:
        return _build_requirement_match(
            requirement,
            match_status="missing",
            explanation=(
                f"Missing language requirement '{requirement.text}'. The profile lists language data, "
                f"but not for '{language_name}'."
            ),
            missing_elements=[language_name],
        )

    required_level_label, required_level_score = _extract_required_language_level(requirement)
    candidate_level_score = _LANGUAGE_SCORE_BY_LEVEL.get(_normalize(candidate_level))
    evidence_text = f"Language '{language_name}' is listed with level '{candidate_level}'."

    if required_level_score is None or candidate_level_score is None:
        explanation = (
            f"Matched language requirement '{requirement.text}' using explicit evidence for '{language_name}'."
        )
        return _build_requirement_match(
            requirement,
            match_status="matched",
            explanation=explanation,
            evidence_texts=[evidence_text],
        )

    if candidate_level_score >= required_level_score:
        explanation = (
            f"Matched language requirement '{requirement.text}'. Candidate level '{candidate_level}' "
            f"meets or exceeds the requested '{required_level_label}'."
        )
        return _build_requirement_match(
            requirement,
            match_status="matched",
            explanation=explanation,
            evidence_texts=[evidence_text],
        )

    if candidate_level_score == required_level_score - 1:
        explanation = (
            f"Partially matched language requirement '{requirement.text}'. Candidate level '{candidate_level}' "
            f"is close to the requested '{required_level_label}', but does not fully meet it."
        )
        return _build_requirement_match(
            requirement,
            match_status="partial",
            explanation=explanation,
            evidence_texts=[evidence_text],
            missing_elements=[f"{language_name} at {required_level_label} level"],
        )

    explanation = (
        f"Missing language requirement '{requirement.text}'. Candidate level '{candidate_level}' "
        f"does not reach the requested '{required_level_label}'."
    )
    return _build_requirement_match(
        requirement,
        match_status="missing",
        explanation=explanation,
        evidence_texts=[evidence_text],
        missing_elements=[f"{language_name} at {required_level_label} level"],
    )


def _education_entry_tokens(entry) -> set[str]:
    """Return normalized tokens for one education entry."""
    return set(_tokenize(f"{entry.degree} {entry.field_of_study} {entry.institution_name}"))


def _education_entry_groups(entry) -> set[str]:
    """Return normalized technical-field groups detected for one education entry."""
    tokens = _education_entry_tokens(entry)
    groups: set[str] = set()
    for group_name, group_tokens in _EDUCATION_FIELD_GROUPS.items():
        if tokens & group_tokens:
            groups.add(group_name)
    return groups


def _education_entry_is_broad_stem(entry) -> bool:
    """Return whether the education entry belongs to broad STEM even without an exact field match."""
    tokens = _education_entry_tokens(entry)
    return bool(tokens & _BROAD_STEM_TOKENS or _education_entry_groups(entry))


def _education_requirement_profile(requirement: Requirement) -> dict[str, object]:
    """Build a lightweight profile of what the education requirement is asking for."""
    text = _requirement_text_blob(requirement)
    tokens = set(_tokenize(text))
    target_groups: set[str] = set()
    for group_name, group_tokens in _EDUCATION_FIELD_GROUPS.items():
        if tokens & group_tokens:
            target_groups.add(group_name)

    allows_related = "related field" in text or "related technical" in text or "or related" in text
    allows_broad_stem = "stem" in tokens or "technical degree" in text or "engineering degree" in text
    requires_degree = bool(tokens & _EDUCATION_TERMS)
    generic_degree_only = requires_degree and not target_groups and not allows_related and not allows_broad_stem
    generic_technical_degree = requires_degree and not target_groups and (allows_related or allows_broad_stem or "technical" in tokens)

    return {
        "target_groups": target_groups,
        "allows_related": allows_related,
        "allows_broad_stem": allows_broad_stem,
        "requires_degree": requires_degree,
        "generic_degree_only": generic_degree_only,
        "generic_technical_degree": generic_technical_degree,
    }


def _evaluate_education_requirement_deterministic(
    requirement: Requirement,
    context: MatchEvidenceContext,
) -> RequirementMatch:
    """Evaluate education requirements with a small exact/related/STEM model."""
    education_entries = context.payload.candidate_profile.education_entries
    if not education_entries:
        return _build_requirement_match(
            requirement,
            match_status="not_verifiable",
            explanation=(
                f"Could not verify education requirement '{requirement.text}' because the candidate profile "
                "does not contain education entries."
            ),
        )

    profile = _education_requirement_profile(requirement)
    target_groups = profile["target_groups"]
    allows_related = bool(profile["allows_related"])
    allows_broad_stem = bool(profile["allows_broad_stem"])
    generic_degree_only = bool(profile["generic_degree_only"])
    generic_technical_degree = bool(profile["generic_technical_degree"])

    best_level = "missing"
    best_entry = None
    for entry in education_entries:
        entry_groups = _education_entry_groups(entry)
        entry_is_stem = _education_entry_is_broad_stem(entry)
        entry_level = "missing"

        if generic_degree_only:
            entry_level = "exact match"
        elif generic_technical_degree:
            if entry_groups:
                entry_level = "related technical field"
            elif entry_is_stem:
                entry_level = "broad STEM"
        elif target_groups:
            if entry_groups & target_groups:
                entry_level = "exact match"
            elif entry_groups:
                entry_level = "related technical field"
            elif entry_is_stem:
                entry_level = "broad STEM"

        if entry_level == "exact match":
            best_level = entry_level
            best_entry = entry
            break
        if entry_level == "related technical field" and best_level not in {"exact match", "related technical field"}:
            best_level = entry_level
            best_entry = entry
        elif entry_level == "broad STEM" and best_level == "missing":
            best_level = entry_level
            best_entry = entry

    if best_entry is None:
        explanation = (
            f"Missing education requirement '{requirement.text}'. The profile contains education data, "
            "but none of the entries indicates the requested degree or field."
        )
        return _build_requirement_match(
            requirement,
            match_status="missing",
            explanation=explanation,
            missing_elements=["required degree or field evidence"],
        )

    evidence_text = (
        f"Education entry '{best_entry.degree}' in '{best_entry.field_of_study}' at "
        f"'{best_entry.institution_name}' was used as evidence."
    )

    if best_level == "exact match":
        explanation = (
            f"Matched education requirement '{requirement.text}' with an exact degree or field match."
        )
        return _build_requirement_match(
            requirement,
            match_status="matched",
            explanation=explanation,
            evidence_texts=[evidence_text],
        )

    if best_level == "related technical field":
        status = "matched" if allows_related or generic_technical_degree else "partial"
        explanation = (
            f"{status.capitalize()} education requirement '{requirement.text}' with a related technical field, "
            f"not an exact field match."
        )
        return _build_requirement_match(
            requirement,
            match_status=status,
            explanation=explanation,
            evidence_texts=[evidence_text],
            missing_elements=[] if status == "matched" else ["exact field match"],
        )

    status = "matched" if allows_broad_stem or generic_technical_degree else "partial"
    explanation = (
        f"{status.capitalize()} education requirement '{requirement.text}' using a broad STEM background, "
        f"but not an exact or closely related field match."
    )
    return _build_requirement_match(
        requirement,
        match_status=status,
        explanation=explanation,
        evidence_texts=[evidence_text],
        missing_elements=[] if status == "matched" else ["related technical field evidence"],
    )


def _has_configured_openai_api_key() -> bool:
    """Return whether a usable OpenAI API key is configured for OpenAI-assisted matching helpers."""
    api_key = os.getenv("OPENAI_API_KEY")
    return bool(api_key and api_key != "tu_wkleisz_swoj_klucz")


def _should_attempt_ai_for_education_match(
    context: MatchEvidenceContext,
    deterministic_match: RequirementMatch,
) -> bool:
    """Return whether the current education requirement should try the AI-assisted path."""
    return bool(
        context.payload.candidate_profile.education_entries
        and deterministic_match.match_status in {"partial", "missing", "not_verifiable"}
        and _has_configured_openai_api_key()
    )


def _resolve_education_entry_by_source_id(education_entries, source_id: str):
    """Resolve one generated education source ID back to the original education entry."""
    prefix = "education_"
    if not source_id.startswith(prefix):
        return None

    suffix = source_id[len(prefix):]
    if not suffix.isdigit():
        return None

    index = int(suffix) - 1
    if index < 0 or index >= len(education_entries):
        return None

    return education_entries[index]


def _build_ai_education_evidence_texts(
    ai_output: OpenAIEducationRequirementMatchOutput,
    context: MatchEvidenceContext,
) -> list[str]:
    """Convert validated AI evidence refs into user-facing evidence texts."""
    evidence_texts: list[str] = []

    for evidence_ref in ai_output.evidence_refs:
        education_entry = _resolve_education_entry_by_source_id(
            context.payload.candidate_profile.education_entries,
            evidence_ref.source_id,
        )
        if education_entry is None:
            continue

        _append_unique(
            evidence_texts,
            (
                f"AI-validated education evidence '{evidence_ref.supporting_snippet}' came from "
                f"'{education_entry.degree}' in '{education_entry.field_of_study}' at "
                f"'{education_entry.institution_name}'."
            ),
        )

    return evidence_texts


def _build_requirement_match_from_ai_education_output(
    requirement: Requirement,
    ai_output: OpenAIEducationRequirementMatchOutput,
    context: MatchEvidenceContext,
) -> RequirementMatch:
    """Map validated AI education output back into the public RequirementMatch shape."""
    evidence_texts = _build_ai_education_evidence_texts(ai_output, context)
    return _build_requirement_match(
        requirement,
        match_status=ai_output.suggested_status,
        explanation=f"AI-assisted education review: {ai_output.explanation}",
        evidence_texts=evidence_texts,
        missing_elements=ai_output.missing_elements,
    )


def _merge_ai_education_requirement_match(
    requirement: Requirement,
    deterministic_match: RequirementMatch,
    ai_output: OpenAIEducationRequirementMatchOutput,
    context: MatchEvidenceContext,
) -> RequirementMatch:
    """Conservatively merge AI education output with the deterministic baseline."""
    if ai_output.grounding_strength == "weak":
        return deterministic_match

    if ai_output.suggested_status == "matched":
        if ai_output.grounding_strength != "strong":
            return deterministic_match

        promoted_status = "matched"
        missing_elements = list(ai_output.missing_elements)
        if (
            deterministic_match.match_status in {"missing", "not_verifiable"}
            and ai_output.match_kind == "broad_stem_match"
        ):
            promoted_status = "partial"
            if not missing_elements:
                missing_elements = ["closer field match"]

        return _build_requirement_match(
            requirement,
            match_status=promoted_status,
            explanation=f"AI-assisted education review: {ai_output.explanation}",
            evidence_texts=_build_ai_education_evidence_texts(ai_output, context),
            missing_elements=missing_elements,
        )

    if ai_output.suggested_status == "partial" and ai_output.grounding_strength in {"strong", "moderate"}:
        return _build_requirement_match_from_ai_education_output(requirement, ai_output, context)

    return deterministic_match


def _evaluate_education_requirement(
    requirement: Requirement,
    context: MatchEvidenceContext,
) -> RequirementMatch:
    """Evaluate education requirements with deterministic logic first and AI assistance as a safe upgrade path."""
    deterministic_match = _evaluate_education_requirement_deterministic(requirement, context)
    if not _should_attempt_ai_for_education_match(context, deterministic_match):
        return deterministic_match

    try:
        ai_output = evaluate_education_requirement_with_openai(
            requirement,
            context.payload.candidate_profile,
            context.payload.job_posting,
            deterministic_match,
        )
    except EducationRequirementMatchOpenAIError:
        return deterministic_match

    return _merge_ai_education_requirement_match(
        requirement,
        deterministic_match,
        ai_output,
        context,
    )


def _evaluate_application_constraint_requirement(
    requirement: Requirement,
    context: MatchEvidenceContext,
) -> RequirementMatch:
    """Evaluate application constraints without turning missing profile fields into technical misses."""
    text = _requirement_text_blob(requirement)
    tokens = set(_tokenize(text))
    candidate = context.payload.candidate_profile

    if "student" in tokens or "enrolled" in tokens or "enrollment" in tokens:
        if not candidate.education_entries:
            return _build_requirement_match(
                requirement,
                match_status="not_verifiable",
                explanation=(
                    f"Could not verify application constraint '{requirement.text}' because the profile "
                    "does not contain education entries."
                ),
            )
        current_entries = [entry for entry in candidate.education_entries if entry.is_current]
        if current_entries:
            evidence_text = (
                f"Current education entry '{current_entries[0].degree}' in "
                f"'{current_entries[0].field_of_study}' is marked as ongoing."
            )
            return _build_requirement_match(
                requirement,
                match_status="matched",
                explanation=(
                    f"Matched application constraint '{requirement.text}' using current education data."
                ),
                evidence_texts=[evidence_text],
            )
        return _build_requirement_match(
            requirement,
            match_status="missing",
            explanation=(
                f"Missing application constraint '{requirement.text}'. Education data is present, "
                "but no entry is marked as current."
            ),
            missing_elements=["current enrollment evidence"],
        )

    if "driving" in tokens or "license" in tokens or "prawo" in tokens or "jazdy" in tokens:
        raw_keywords, normalized_keywords = _prepare_requirement_keywords(requirement)
        if normalized_keywords:
            (
                matched_keywords,
                _missing_keywords,
                _matched_skill_names,
                _matched_experience_ids,
                _matched_project_ids,
                evidence_texts,
            ) = _collect_keyword_evidence(raw_keywords, normalized_keywords, context.evidence_index)
            if matched_keywords:
                return _build_requirement_match(
                    requirement,
                    match_status="matched",
                    explanation=(
                        f"Matched application constraint '{requirement.text}' using explicit certificate or profile evidence."
                    ),
                    evidence_texts=evidence_texts,
                )
        return _build_requirement_match(
            requirement,
            match_status="not_verifiable",
            explanation=(
                f"Could not verify application constraint '{requirement.text}' because the current profile "
                "does not store driving-license data in a dedicated field."
            ),
        )

    if "18" in tokens or "age" in tokens or "authorized" in tokens or "authorization" in tokens or "clearance" in tokens:
        return _build_requirement_match(
            requirement,
            match_status="not_verifiable",
            explanation=(
                f"Could not verify application constraint '{requirement.text}' because the current profile "
                "does not store age, work-authorization, or clearance data."
            ),
        )

    raw_keywords, normalized_keywords = _prepare_requirement_keywords(requirement)
    if normalized_keywords:
        (
            matched_keywords,
            _missing_keywords,
            _matched_skill_names,
            _matched_experience_ids,
            _matched_project_ids,
            evidence_texts,
        ) = _collect_keyword_evidence(raw_keywords, normalized_keywords, context.evidence_index)
        if matched_keywords:
            return _build_requirement_match(
                requirement,
                match_status="matched",
                explanation=(
                    f"Matched application constraint '{requirement.text}' using explicit certificate or profile evidence."
                ),
                evidence_texts=evidence_texts,
            )

    return _build_requirement_match(
        requirement,
        match_status="not_verifiable",
        explanation=(
            f"Could not verify application constraint '{requirement.text}' because it requires candidate confirmation "
            "and the current profile does not store that information."
        ),
    )


def _evaluate_soft_skill_requirement(
    requirement: Requirement,
    context: MatchEvidenceContext,
) -> RequirementMatch:
    """Evaluate soft signals conservatively so low-signal claims do not create noise."""
    raw_keywords, normalized_keywords = _prepare_requirement_keywords(requirement)
    if not normalized_keywords:
        return _build_requirement_match(
            requirement,
            match_status="not_verifiable",
            explanation=(
                f"Could not verify soft-signal requirement '{requirement.text}' because it has no "
                "explicit keywords to check."
            ),
        )

    candidate_text_blob = _normalize(" ".join(context.candidate_texts))
    matched_keywords = [keyword for keyword in raw_keywords if _normalize(keyword) in candidate_text_blob]
    if matched_keywords:
        return _build_requirement_match(
            requirement,
            match_status="partial",
            explanation=(
                f"Soft-signal requirement '{requirement.text}' has some supporting wording in the profile, "
                f"but remains only partially verifiable. Matched: {', '.join(matched_keywords)}."
            ),
            evidence_texts=["Soft-signal evidence was inferred from free-text profile content."],
            missing_elements=[keyword for keyword in raw_keywords if keyword not in matched_keywords],
        )

    return _build_requirement_match(
        requirement,
        match_status="not_verifiable",
        explanation=(
            f"Could not verify soft-signal requirement '{requirement.text}' reliably with deterministic evidence, "
            "so it stays neutral for scoring."
        ),
    )


def _evaluate_low_signal_requirement(
    requirement: Requirement,
    _context: MatchEvidenceContext,
) -> RequirementMatch:
    """Keep noisy, low-signal requirements neutral instead of overfitting to keywords."""
    return _build_requirement_match(
        requirement,
        match_status="not_verifiable",
        explanation=(
            f"Requirement '{requirement.text}' was treated as low-signal and left neutral because "
            "the deterministic matcher cannot verify it reliably without adding noise."
        ),
    )


def _evaluate_requirement(
    requirement: Requirement,
    context: MatchEvidenceContext,
) -> tuple[str, RequirementMatch]:
    """Dispatch one requirement to the evaluator best suited for its normalized group."""
    group_name = _determine_requirement_group(requirement, context.payload.job_posting)
    if group_name == "technical_skill":
        return group_name, _evaluate_keyword_requirement(requirement, context, group_name=group_name)
    if group_name == "domain":
        return group_name, _evaluate_keyword_requirement(requirement, context, group_name=group_name)
    if group_name == "experience":
        return group_name, _evaluate_experience_requirement(requirement, context)
    if group_name == "education":
        return group_name, _evaluate_education_requirement(requirement, context)
    if group_name == "language":
        return group_name, _evaluate_language_requirement(requirement, context)
    if group_name == "application_constraint":
        return group_name, _evaluate_application_constraint_requirement(requirement, context)
    if group_name == "soft_signal":
        return group_name, _evaluate_soft_skill_requirement(requirement, context)
    return group_name, _evaluate_low_signal_requirement(requirement, context)


def _get_importance_weight(importance: str) -> float:
    """Return the score weight for requirement importance."""
    normalized_importance = _normalize(importance)
    return _IMPORTANCE_WEIGHTS.get(normalized_importance, _IMPORTANCE_WEIGHTS["medium"])


def _get_requirement_type_multiplier(requirement_type: str) -> float:
    """Return the score multiplier for requirement type."""
    normalized_requirement_type = _normalize(requirement_type)
    return _REQUIREMENT_TYPE_MULTIPLIERS.get(
        normalized_requirement_type,
        _REQUIREMENT_TYPE_MULTIPLIERS["nice_to_have"],
    )


def _get_match_status_score(match_status: str) -> float | None:
    """Return the numeric score for a requirement match status or None when it is neutral."""
    normalized_match_status = _normalize(match_status)
    if normalized_match_status == "not_verifiable":
        return None
    return _MATCH_STATUS_SCORES.get(normalized_match_status, _MATCH_STATUS_SCORES["missing"])


def _get_category_score_multiplier(requirement_group: str) -> float:
    """Return the score multiplier associated with one normalized requirement group."""
    return _CATEGORY_SCORE_MULTIPLIERS.get(requirement_group, 1.0)


def _calculate_requirement_weight(requirement: Requirement, requirement_group: str) -> float:
    """Calculate the weighted-score importance of a single requirement."""
    return (
        _get_importance_weight(requirement.importance)
        * _get_requirement_type_multiplier(requirement.requirement_type)
        * _get_category_score_multiplier(requirement_group)
    )


def _calculate_weighted_score(
    requirements: list[Requirement],
    requirement_groups: list[str],
    requirement_matches: list[RequirementMatch],
) -> float:
    """Calculate the weighted overall score across all score-bearing requirements."""
    weighted_score_sum = 0.0
    total_weight = 0.0

    for requirement, requirement_group, requirement_match in zip(
        requirements,
        requirement_groups,
        requirement_matches,
    ):
        requirement_weight = _calculate_requirement_weight(requirement, requirement_group)
        match_status_score = _get_match_status_score(requirement_match.match_status)
        if requirement_weight <= 0 or match_status_score is None:
            continue
        total_weight += requirement_weight
        weighted_score_sum += requirement_weight * match_status_score

    if total_weight == 0:
        return 0.0

    return weighted_score_sum / total_weight


def _calculate_fit_classification(overall_score: float) -> str:
    """Classify the overall score using explicit high and medium thresholds."""
    if overall_score >= _HIGH_FIT_THRESHOLD:
        return "high"
    if overall_score >= _MEDIUM_FIT_THRESHOLD:
        return "medium"
    return "low"


def _build_recommendation(fit_classification: str) -> str:
    """Map fit classification to the base recommendation."""
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
    """Count must-have requirements that remain completely missing."""
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
    """Check whether any critical must-have requirement is fully missing."""
    return any(
        _normalize(requirement.requirement_type) == "must_have"
        and _normalize(requirement.importance) == "high"
        and requirement_match.match_status == "missing"
        for requirement, requirement_match in zip(requirements, requirement_matches)
    )


def _has_not_verifiable_must_have(
    requirements: list[Requirement],
    requirement_groups: list[str],
    requirement_matches: list[RequirementMatch],
) -> bool:
    """Check whether any must-have requirement stayed unverifiable and should trigger caution."""
    return any(
        _normalize(requirement.requirement_type) == "must_have"
        and requirement_match.match_status == "not_verifiable"
        and requirement_group not in {"low_signal", "soft_signal"}
        for requirement, requirement_group, requirement_match in zip(
            requirements,
            requirement_groups,
            requirement_matches,
        )
    )


def _apply_fit_classification_gating(
    fit_classification: str,
    requirements: list[Requirement],
    requirement_matches: list[RequirementMatch],
) -> str:
    """Apply simple gating rules that cap misleadingly optimistic fit labels."""
    if (
        fit_classification == "high"
        and _has_missing_high_importance_must_have(requirements, requirement_matches)
    ):
        return "medium"

    return fit_classification


def _apply_recommendation_gating(
    recommendation: str,
    requirements: list[Requirement],
    requirement_groups: list[str],
    requirement_matches: list[RequirementMatch],
) -> str:
    """Apply must-have gating so critical gaps cannot keep an optimistic recommendation."""
    missing_must_have_count = _count_missing_must_have_requirements(
        requirements,
        requirement_matches,
    )

    if missing_must_have_count >= 2:
        return "do_not_recommend"
    if missing_must_have_count >= 1 and recommendation == "generate":
        return "generate_with_caution"
    if (
        recommendation == "generate"
        and _has_not_verifiable_must_have(requirements, requirement_groups, requirement_matches)
    ):
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
    """Build a short list of gaps, partial matches, and non-verifiable requirements."""
    gaps: list[str] = []

    for requirement, requirement_match in zip(payload.job_posting.requirements, requirement_matches):
        if requirement_match.match_status == "partial":
            if requirement_match.missing_elements:
                _append_unique(
                    gaps,
                    (
                        f"Partially matched requirement: {requirement.text}. "
                        f"Still needs: {', '.join(requirement_match.missing_elements)}"
                    ),
                )
            else:
                _append_unique(gaps, f"Partially matched requirement: {requirement_match.explanation}")
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
                _append_unique(gaps, f"Missing requirement: {requirement.text}.")
        elif requirement_match.match_status == "not_verifiable":
            _append_unique(
                gaps,
                f"Could not verify requirement: {requirement.text}. {requirement_match.explanation}",
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
    not_verifiable_requirements_count: int,
    total_requirements: int,
    keyword_coverage: list[str],
) -> str:
    """Build the final user-facing summary of the matching result."""
    covered_keywords = ", ".join(keyword_coverage) if keyword_coverage else "none"
    summary = (
        f"Profile fit for '{job_title}' is {fit_classification} with score "
        f"{overall_score:.2f}. Requirements summary: {matched_requirements_count} matched, "
        f"{partial_requirements_count} partial, {missing_requirements_count} missing, "
        f"{not_verifiable_requirements_count} not verifiable out of {total_requirements}. "
        f"Recommendation: {recommendation}. Covered job keywords: {covered_keywords}."
    )
    if not_verifiable_requirements_count:
        summary = (
            f"{summary} Some requirements could not be verified from the currently stored profile data."
        )
    return summary


def analyze_match_basic(payload: MatchAnalysisRequest) -> MatchResult:
    """Analyze candidate-vs-job fit using category-aware deterministic evidence."""
    context = _build_candidate_evidence_context(payload)
    grouped_matches = [
        _evaluate_requirement(requirement, context)
        for requirement in payload.job_posting.requirements
    ]
    requirement_groups = [group_name for group_name, _ in grouped_matches]
    requirement_matches = [match for _, match in grouped_matches]

    matched_requirements_count = sum(
        1 for requirement_match in requirement_matches if requirement_match.match_status == "matched"
    )
    partial_requirements_count = sum(
        1 for requirement_match in requirement_matches if requirement_match.match_status == "partial"
    )
    missing_requirements_count = sum(
        1 for requirement_match in requirement_matches if requirement_match.match_status == "missing"
    )
    not_verifiable_requirements_count = sum(
        1
        for requirement_match in requirement_matches
        if requirement_match.match_status == "not_verifiable"
    )

    total_requirements = len(payload.job_posting.requirements)
    overall_score = _calculate_weighted_score(
        payload.job_posting.requirements,
        requirement_groups,
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
        requirement_groups,
        requirement_matches,
    )

    keyword_coverage = [
        keyword
        for keyword in payload.job_posting.keywords
        if _normalize(keyword) in context.candidate_keywords
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
            not_verifiable_requirements_count,
            total_requirements,
            keyword_coverage,
        ),
    )
