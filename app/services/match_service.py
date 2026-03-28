"""Category-aware deterministic matching service that builds MatchResult and RequirementMatch."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re

from app.models.analysis import MatchAnalysisRequest
from app.models.job import JobPosting, Requirement
from app.models.match import MatchResult, RequirementMatch
from app.services.display_keyword_utils import build_display_keywords
from app.services.openai_candidate_profile_understanding_service import (
    CandidateProfileUnderstanding,
    CandidateSourceSignal,
    get_candidate_profile_understanding,
)
from app.services.openai_education_match_service import (
    EducationRequirementMatchOpenAIError,
    OpenAIEducationRequirementMatchOutput,
    evaluate_education_requirement_with_openai,
)
from app.services.openai_requirement_candidate_match_service import (
    RequirementCandidateMatchItem,
    RequirementCandidateMatchOpenAIError,
    build_candidate_match_source_catalog,
    evaluate_requirement_candidate_block_with_openai,
)
from app.services.openai_requirement_priority_service import (
    OpenAIRequirementPriorityItem,
    build_requirement_priority_sort_key,
    count_requirement_priority_tiers,
    get_requirement_priority_lookup,
)
from app.services.openai_requirement_type_service import (
    RequirementTypeClassificationOpenAIError,
    evaluate_requirement_type_with_openai,
)
from app.services.reportable_term_utils import build_reportable_offer_terms

_IMPORTANCE_WEIGHTS = {
    "high": 1.0,
    "medium": 0.7,
    "low": 0.4,
}
_REQUIREMENT_TYPE_MULTIPLIERS = {
    "must_have": 1.3,
    "nice_to_have": 1.0,
}
_CATEGORY_SCORE_MULTIPLIERS = {
    "technical_skill": 1.0,
    "experience": 1.0,
    "education": 0.95,
    "language": 0.9,
    "domain": 0.85,
    "application_constraint": 0.0,
    "soft_signal": 0.6,
    "low_signal": 0.45,
    "eligibility": 0.0,
    "soft_skill": 0.6,
}
_SCORING_BUCKET_BLEND_WEIGHTS = {
    "core": 0.72,
    "supporting": 0.2,
    "contextual": 0.08,
}
_SCORING_BUCKET_BASE_MULTIPLIERS = {
    "core": 1.0,
    "supporting": 0.45,
    "contextual": 0.2,
    "manual_confirmation": 0.0,
}
_MATCH_STATUS_SCORES_BY_BUCKET = {
    "core": {
        "matched": 1.0,
        "partial": 0.72,
        "missing": 0.0,
    },
    "supporting": {
        "matched": 1.0,
        "partial": 0.5,
        "missing": 0.0,
    },
    "contextual": {
        "matched": 1.0,
        "partial": 0.35,
        "missing": 0.0,
    },
}
_HIGH_FIT_THRESHOLD = 0.75
_MEDIUM_FIT_THRESHOLD = 0.45
_MAX_KEYWORD_COVERAGE = 8
_AI_REQUIREMENT_MATCH_BLOCK_SIZE = 6
_AI_SEMANTIC_ELIGIBLE_GROUPS = {
    "technical_skill",
    "experience",
    "education",
    "language",
    "domain",
    "soft_signal",
}
_MANUAL_CONFIRMATION_GROUPS = {"application_constraint", "eligibility"}

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
_LANGUAGE_DESCRIPTOR_ALIASES = {
    "professional written": "professional_written",
    "professional spoken": "professional_spoken",
    "business working": "business_working",
}
_GENERIC_PROFILE_SIGNAL_TOKENS = {
    "technology",
    "technologies",
    "engineering",
    "engineer",
    "work",
    "project",
    "projects",
    "experience",
    "experiences",
    "skill",
    "skills",
    "knowledge",
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
    language_descriptor_index: dict[str, set[str]]
    candidate_profile_understanding: CandidateProfileUnderstanding


@dataclass(slots=True)
class RequirementEvaluationRecord:
    """Internal requirement evaluation row used for explainability ordering."""

    original_index: int
    requirement: Requirement
    requirement_group: str
    requirement_match: RequirementMatch


@dataclass(slots=True)
class RequirementScoringProfile:
    """Internal scoring profile for one evaluated requirement."""

    bucket: str
    weight: float
    status_score: float | None
    priority_tier: str | None


@dataclass(slots=True)
class MatchScoreBreakdown:
    """Compact deterministic score breakdown used for fit and recommendation."""

    overall_score: float
    core_coverage: float | None
    supporting_coverage: float | None
    contextual_coverage: float | None
    core_requirement_count: int
    supporting_requirement_count: int
    contextual_requirement_count: int
    manual_confirmation_requirement_count: int
    core_missing_count: int
    core_missing_must_have_count: int
    missing_must_have_count: int
    core_partial_count: int
    critical_not_verifiable_count: int
    pending_confirmation_count: int


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


def _build_ai_profile_signal_evidence_text(source_signal: CandidateSourceSignal) -> str:
    """Build a readable evidence text for a grounded AI-understood candidate signal."""

    readable_signal_kind = source_signal.signal_kind.replace("_", " ")
    return (
        f"AI-understood {readable_signal_kind} '{source_signal.signal_label}' is grounded in "
        f"{source_signal.source_type} '{source_signal.source_title}'."
    )


def _register_profile_understanding_source_signal(
    evidence_index: dict[str, dict[str, list[str]]],
    candidate_keywords: set[str],
    source_signal: CandidateSourceSignal,
) -> None:
    """Register grounded hard-evidence profile signals into the deterministic evidence index."""

    if source_signal.evidence_class != "hard_evidence":
        return

    experience_id = source_signal.source_id if source_signal.source_type == "experience" else None
    project_id = source_signal.source_id if source_signal.source_type == "project" else None
    skill_name = source_signal.signal_label if source_signal.source_type == "skill" else None
    evidence_text = _build_ai_profile_signal_evidence_text(source_signal)

    for value in [source_signal.signal_label, *source_signal.normalized_terms]:
        if not value or not value.strip():
            continue
        _register_keyword_evidence(
            evidence_index,
            candidate_keywords,
            value,
            skill_name=skill_name,
            experience_id=experience_id,
            project_id=project_id,
            evidence_text=evidence_text,
        )
        for token in _tokenize(value):
            if (
                len(token) <= 2
                or token in _TOKEN_STOPWORDS
                or token in _GENERIC_PROFILE_SIGNAL_TOKENS
            ):
                continue
            _register_keyword_evidence(
                evidence_index,
                candidate_keywords,
                token,
                skill_name=skill_name,
                experience_id=experience_id,
                project_id=project_id,
                evidence_text=evidence_text,
            )


def _expand_language_descriptors(descriptors: set[str]) -> set[str]:
    """Expand language descriptors with conservative implied base descriptors."""

    expanded_descriptors = set(descriptors)
    if "professional_written" in expanded_descriptors:
        expanded_descriptors.add("written")
    if "professional_spoken" in expanded_descriptors:
        expanded_descriptors.add("spoken")
    if "fluent" in expanded_descriptors:
        expanded_descriptors.update({"written", "spoken"})
    if "business_working" in expanded_descriptors:
        expanded_descriptors.add("spoken")
    return expanded_descriptors


def _build_candidate_evidence_context(
    payload: MatchAnalysisRequest,
    *,
    candidate_profile_understanding: CandidateProfileUnderstanding | None = None,
) -> MatchEvidenceContext:
    """Build reusable candidate evidence for category-aware requirement evaluators."""
    candidate = payload.candidate_profile
    profile_understanding = candidate_profile_understanding or CandidateProfileUnderstanding()
    experience_ids = {experience.id for experience in candidate.experience_entries}
    project_ids = {project.id for project in candidate.project_entries}

    candidate_keywords: set[str] = set()
    evidence_index: dict[str, dict[str, list[str]]] = {}
    skill_years_index: dict[str, float] = {}
    language_levels: dict[str, str] = {}
    language_descriptor_index: dict[str, set[str]] = {}

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

    for source_signal in profile_understanding.source_signals:
        _register_profile_understanding_source_signal(
            evidence_index,
            candidate_keywords,
            source_signal,
        )

    for language_normalization in profile_understanding.language_normalizations:
        normalized_language_name = _normalize(language_normalization.language_name)
        if not normalized_language_name:
            continue

        if language_normalization.normalized_cefr:
            language_levels[normalized_language_name] = language_normalization.normalized_cefr.upper()

        expanded_descriptors = _expand_language_descriptors(
            set(language_normalization.semantic_descriptors)
        )
        if expanded_descriptors:
            descriptor_bucket = language_descriptor_index.setdefault(normalized_language_name, set())
            descriptor_bucket.update(expanded_descriptors)

    profile_understanding_texts = _collect_text_values(
        [
            *[
                value
                for signal in profile_understanding.profile_signals
                for value in [signal.signal_label, *signal.normalized_terms]
            ],
            *[
                value
                for alignment in profile_understanding.thematic_alignments
                for value in [alignment.theme_label, *alignment.normalized_terms]
            ],
            *[
                value
                for signal in profile_understanding.source_signals
                if signal.evidence_class == "declared_signal"
                for value in [signal.signal_label, *signal.normalized_terms]
            ],
            *[
                value
                for normalization in profile_understanding.language_normalizations
                for value in [
                    normalization.language_name,
                    normalization.source_level,
                    normalization.normalized_cefr.upper() if normalization.normalized_cefr else None,
                    *normalization.semantic_descriptors,
                ]
            ],
        ]
    )

    candidate_texts = _collect_text_values(
        [
            candidate.professional_summary_base,
            *candidate.target_roles,
            *candidate.soft_skill_entries,
            *candidate.interest_entries,
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
            *profile_understanding_texts,
        ]
    )

    return MatchEvidenceContext(
        payload=payload,
        candidate_keywords=candidate_keywords,
        evidence_index=evidence_index,
        candidate_texts=candidate_texts,
        skill_years_index=skill_years_index,
        language_levels=language_levels,
        language_descriptor_index=language_descriptor_index,
        candidate_profile_understanding=profile_understanding,
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


def _extract_required_language_descriptors(requirement: Requirement) -> list[str]:
    """Extract requested semantic language descriptors like fluent, written and spoken."""

    text = _requirement_text_blob(requirement)
    descriptors: list[str] = []

    for phrase, descriptor in _LANGUAGE_DESCRIPTOR_ALIASES.items():
        if phrase in text:
            _append_unique(descriptors, descriptor)

    for descriptor in (
        "fluent",
        "written",
        "spoken",
        "professional_written",
        "professional_spoken",
        "business_working",
        "conversational",
    ):
        if descriptor in text:
            _append_unique(descriptors, descriptor)

    return descriptors


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
    required_descriptors = _extract_required_language_descriptors(requirement)
    candidate_level_score = _LANGUAGE_SCORE_BY_LEVEL.get(_normalize(candidate_level))
    evidence_text = f"Language '{language_name}' is listed with level '{candidate_level}'."
    candidate_descriptors = context.language_descriptor_index.get(normalized_language_name, set())

    if required_descriptors and candidate_descriptors:
        matched_descriptors = [
            descriptor for descriptor in required_descriptors if descriptor in candidate_descriptors
        ]
        descriptor_summary = ", ".join(required_descriptors)
        if len(matched_descriptors) == len(required_descriptors):
            explanation = (
                f"Matched language requirement '{requirement.text}' using normalized language evidence "
                f"for '{language_name}' with descriptors: {descriptor_summary}."
            )
            return _build_requirement_match(
                requirement,
                match_status="matched",
                explanation=explanation,
                evidence_texts=[
                    evidence_text,
                    (
                        f"AI-normalized language descriptors for '{language_name}' include: "
                        f"{', '.join(sorted(candidate_descriptors))}."
                    ),
                ],
            )

        if matched_descriptors:
            explanation = (
                f"Partially matched language requirement '{requirement.text}' using normalized language "
                f"evidence for '{language_name}'. Matched descriptors: {', '.join(matched_descriptors)}; "
                f"missing descriptors: {', '.join(descriptor for descriptor in required_descriptors if descriptor not in matched_descriptors)}."
            )
            return _build_requirement_match(
                requirement,
                match_status="partial",
                explanation=explanation,
                evidence_texts=[
                    evidence_text,
                    (
                        f"AI-normalized language descriptors for '{language_name}' include: "
                        f"{', '.join(sorted(candidate_descriptors))}."
                    ),
                ],
                missing_elements=[
                    f"{language_name} with {descriptor}"
                    for descriptor in required_descriptors
                    if descriptor not in matched_descriptors
                ],
            )

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


def _should_attempt_ai_requirement_candidate_match(
    record: RequirementEvaluationRecord,
) -> bool:
    """Return whether one requirement is eligible for the semantic AI upgrade layer."""

    return (
        record.requirement_group in _AI_SEMANTIC_ELIGIBLE_GROUPS
        and record.requirement_match.match_status in {"partial", "missing", "not_verifiable"}
    )


def _chunk_requirement_records(
    requirement_records: list[RequirementEvaluationRecord],
    *,
    chunk_size: int,
) -> list[list[RequirementEvaluationRecord]]:
    """Split an ordered requirement list into stable small blocks."""

    if chunk_size <= 0:
        return [list(requirement_records)] if requirement_records else []

    return [
        requirement_records[index:index + chunk_size]
        for index in range(0, len(requirement_records), chunk_size)
    ]


def _build_ai_semantic_evidence_texts(
    ai_item: RequirementCandidateMatchItem,
    candidate_source_lookup: dict[tuple[str, str], dict[str, str]],
) -> list[str]:
    """Turn grounded AI refs into readable evidence texts for the public match result."""

    evidence_texts: list[str] = []

    for evidence_ref in ai_item.evidence_refs:
        source_meta = candidate_source_lookup.get((evidence_ref.source_type, evidence_ref.source_id))
        if source_meta is None:
            continue
        _append_unique(
            evidence_texts,
            (
                f"AI-grounded evidence '{evidence_ref.supporting_snippet}' came from "
                f"{evidence_ref.source_type} '{source_meta['source_title']}'."
            ),
        )

    return evidence_texts


def _build_match_fields_from_ai_evidence_refs(
    ai_item: RequirementCandidateMatchItem,
    candidate_source_lookup: dict[tuple[str, str], dict[str, str]],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Map grounded AI evidence refs back into RequirementMatch support fields."""

    matched_skill_names: list[str] = []
    matched_experience_ids: list[str] = []
    matched_project_ids: list[str] = []
    evidence_texts = _build_ai_semantic_evidence_texts(ai_item, candidate_source_lookup)

    for evidence_ref in ai_item.evidence_refs:
        if evidence_ref.source_type == "skill":
            source_meta = candidate_source_lookup.get((evidence_ref.source_type, evidence_ref.source_id))
            if source_meta is not None:
                _append_unique(matched_skill_names, source_meta["source_title"])
        elif evidence_ref.source_type == "experience":
            _append_unique(matched_experience_ids, evidence_ref.source_id)
        elif evidence_ref.source_type == "project":
            _append_unique(matched_project_ids, evidence_ref.source_id)

    return matched_skill_names, matched_experience_ids, matched_project_ids, evidence_texts


def _missing_elements_include_year_threshold(missing_elements: list[str]) -> bool:
    """Return whether the current missing-elements list still reflects a years threshold gap."""

    return any("years of documented experience" in _normalize(item) for item in missing_elements)


def _merge_semantic_missing_elements(
    deterministic_match: RequirementMatch,
    ai_item: RequirementCandidateMatchItem,
    *,
    final_status: str,
    additional_missing_elements: list[str] | None = None,
) -> list[str]:
    """Merge missing elements conservatively so hard gaps are not erased by semantics."""

    if final_status == "matched":
        return []

    missing_elements: list[str] = []
    _extend_unique(missing_elements, deterministic_match.missing_elements)
    _extend_unique(missing_elements, ai_item.missing_elements)
    _extend_unique(missing_elements, additional_missing_elements or [])
    return missing_elements


def _build_requirement_match_from_ai_semantic_item(
    requirement: Requirement,
    deterministic_match: RequirementMatch,
    ai_item: RequirementCandidateMatchItem,
    *,
    final_status: str,
    candidate_source_lookup: dict[tuple[str, str], dict[str, str]],
    additional_missing_elements: list[str] | None = None,
) -> RequirementMatch:
    """Map a validated semantic AI decision back into the public RequirementMatch shape."""

    (
        matched_skill_names,
        matched_experience_ids,
        matched_project_ids,
        ai_evidence_texts,
    ) = _build_match_fields_from_ai_evidence_refs(ai_item, candidate_source_lookup)

    merged_evidence_texts = list(deterministic_match.evidence_texts)
    _extend_unique(merged_evidence_texts, ai_evidence_texts)

    merged_skill_names = list(deterministic_match.matched_skill_names)
    _extend_unique(merged_skill_names, matched_skill_names)

    merged_experience_ids = list(deterministic_match.matched_experience_ids)
    _extend_unique(merged_experience_ids, matched_experience_ids)

    merged_project_ids = list(deterministic_match.matched_project_ids)
    _extend_unique(merged_project_ids, matched_project_ids)

    supporting_signal_note = (
        f" Supporting signals: {', '.join(ai_item.supporting_signal_labels)}."
        if ai_item.supporting_signal_labels
        else ""
    )
    merged_missing_elements = _merge_semantic_missing_elements(
        deterministic_match,
        ai_item,
        final_status=final_status,
        additional_missing_elements=additional_missing_elements,
    )

    return _build_requirement_match(
        requirement,
        match_status=final_status,
        explanation=(
            f"AI-assisted semantic review: {ai_item.reasoning_note}"
            f"{supporting_signal_note}"
        ),
        matched_skill_names=merged_skill_names,
        matched_experience_ids=merged_experience_ids,
        matched_project_ids=merged_project_ids,
        evidence_texts=merged_evidence_texts,
        missing_elements=merged_missing_elements,
    )


def _merge_ai_soft_signal_requirement_match(
    requirement: Requirement,
    deterministic_match: RequirementMatch,
    ai_item: RequirementCandidateMatchItem,
    *,
    candidate_source_lookup: dict[tuple[str, str], dict[str, str]],
) -> RequirementMatch:
    """Merge semantic AI output for soft-signal requirements conservatively."""

    if ai_item.grounding_strength == "weak":
        return deterministic_match

    if ai_item.suggested_status in {"matched", "partial"} and ai_item.evidence_basis in {
        "hard_evidence",
        "mixed",
        "declared_only",
        "thematic_only",
    }:
        final_status = "matched"
        if ai_item.evidence_basis in {"declared_only", "thematic_only"} or ai_item.grounding_strength != "strong":
            final_status = "partial"
        return _build_requirement_match_from_ai_semantic_item(
            requirement,
            deterministic_match,
            ai_item,
            final_status=final_status,
            candidate_source_lookup=candidate_source_lookup,
        )

    return deterministic_match


def _merge_ai_requirement_candidate_match(
    requirement: Requirement,
    requirement_group: str,
    deterministic_match: RequirementMatch,
    ai_item: RequirementCandidateMatchItem,
    *,
    candidate_source_lookup: dict[tuple[str, str], dict[str, str]],
) -> RequirementMatch:
    """Conservatively merge semantic AI matching with the deterministic baseline."""

    if requirement_group == "soft_signal":
        return _merge_ai_soft_signal_requirement_match(
            requirement,
            deterministic_match,
            ai_item,
            candidate_source_lookup=candidate_source_lookup,
        )

    if ai_item.grounding_strength == "weak":
        return deterministic_match

    if ai_item.evidence_basis in {"declared_only", "thematic_only", "none"}:
        return deterministic_match

    final_status = deterministic_match.match_status
    additional_missing_elements: list[str] = []
    if ai_item.suggested_status == "matched" and ai_item.grounding_strength == "strong":
        final_status = "matched"
    elif ai_item.suggested_status == "partial" and ai_item.grounding_strength in {"strong", "moderate"}:
        final_status = "partial"
    else:
        return deterministic_match

    required_years = _extract_required_years(requirement) if requirement_group == "experience" else None
    if requirement_group == "experience" and required_years is not None and final_status == "matched":
        if deterministic_match.match_status != "matched":
            final_status = "partial"
            additional_missing_elements.append(f"{required_years:g}+ years of documented experience")
        elif _missing_elements_include_year_threshold(deterministic_match.missing_elements):
            final_status = "partial"
            additional_missing_elements.append(f"{required_years:g}+ years of documented experience")

    if final_status == deterministic_match.match_status and not ai_item.supporting_signal_labels:
        return deterministic_match

    return _build_requirement_match_from_ai_semantic_item(
        requirement,
        deterministic_match,
        ai_item,
        final_status=final_status,
        candidate_source_lookup=candidate_source_lookup,
        additional_missing_elements=additional_missing_elements,
    )


def _apply_ai_requirement_candidate_matching(
    payload: MatchAnalysisRequest,
    requirement_records: list[RequirementEvaluationRecord],
    context: MatchEvidenceContext,
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> tuple[list[RequirementEvaluationRecord], int]:
    """Apply the semantic AI upgrade layer on top of deterministic requirement matches."""

    if not _has_configured_openai_api_key():
        return requirement_records, 0

    eligible_records = [
        record
        for record in _order_requirement_records(requirement_records, priority_lookup)
        if _should_attempt_ai_requirement_candidate_match(record)
    ]
    if not eligible_records:
        return requirement_records, 0

    _, candidate_source_lookup = build_candidate_match_source_catalog(
        payload.candidate_profile,
    )
    requirement_groups = {
        record.requirement.id: record.requirement_group
        for record in requirement_records
    }
    deterministic_match_lookup = {
        record.requirement.id: record.requirement_match
        for record in requirement_records
    }
    merged_lookup = dict(deterministic_match_lookup)
    semantic_upgrade_count = 0

    for requirement_block in _chunk_requirement_records(
        eligible_records,
        chunk_size=_AI_REQUIREMENT_MATCH_BLOCK_SIZE,
    ):
        try:
            ai_output = evaluate_requirement_candidate_block_with_openai(
                payload,
                target_requirements=[record.requirement for record in requirement_block],
                requirement_groups=requirement_groups,
                deterministic_match_lookup=merged_lookup,
                requirement_priority_lookup=priority_lookup,
                candidate_profile_understanding=context.candidate_profile_understanding,
            )
        except RequirementCandidateMatchOpenAIError:
            continue

        ai_lookup = {item.requirement_id: item for item in ai_output.items}
        for record in requirement_block:
            ai_item = ai_lookup.get(record.requirement.id)
            if ai_item is None:
                continue

            merged_match = _merge_ai_requirement_candidate_match(
                record.requirement,
                record.requirement_group,
                merged_lookup[record.requirement.id],
                ai_item,
                candidate_source_lookup=candidate_source_lookup,
            )
            if merged_match.model_dump(mode="json") != merged_lookup[record.requirement.id].model_dump(mode="json"):
                semantic_upgrade_count += 1
            merged_lookup[record.requirement.id] = merged_match

    return (
        [
            RequirementEvaluationRecord(
                original_index=record.original_index,
                requirement=record.requirement,
                requirement_group=record.requirement_group,
                requirement_match=merged_lookup[record.requirement.id],
            )
            for record in requirement_records
        ],
        semantic_upgrade_count,
    )


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


def _is_must_have(requirement: Requirement) -> bool:
    """Return whether one requirement is explicitly marked as must-have."""
    return _normalize(requirement.requirement_type) == "must_have"


def _get_requirement_priority_tier(
    requirement: Requirement,
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> str | None:
    """Return the AI priority tier for one requirement when available."""

    priority_item = priority_lookup.get(requirement.id)
    if priority_item is None:
        return None
    return priority_item.priority_tier


def _get_scoring_bucket_base_multiplier(bucket: str) -> float:
    """Return the base score weight for one scoring bucket."""

    return _SCORING_BUCKET_BASE_MULTIPLIERS.get(
        bucket,
        _SCORING_BUCKET_BASE_MULTIPLIERS["contextual"],
    )


def _get_bucket_status_score(bucket: str, match_status: str) -> float | None:
    """Return the bucket-aware numeric score for one requirement match status."""

    normalized_match_status = _normalize(match_status)
    if normalized_match_status == "not_verifiable":
        return None

    bucket_scores = _MATCH_STATUS_SCORES_BY_BUCKET.get(
        bucket,
        _MATCH_STATUS_SCORES_BY_BUCKET["contextual"],
    )
    return bucket_scores.get(normalized_match_status, bucket_scores["missing"])


def _get_category_score_multiplier(requirement_group: str) -> float:
    """Return the score multiplier associated with one normalized requirement group."""
    return _CATEGORY_SCORE_MULTIPLIERS.get(requirement_group, 1.0)


def _determine_scoring_bucket(
    requirement: Requirement,
    requirement_group: str,
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> str:
    """Map one evaluated requirement into a compact deterministic scoring bucket."""

    if requirement_group in _MANUAL_CONFIRMATION_GROUPS:
        return "manual_confirmation"

    priority_tier = _get_requirement_priority_tier(requirement, priority_lookup)
    if priority_tier == "core":
        return "core"
    if priority_tier == "supporting":
        return "supporting"
    if priority_tier == "low_signal":
        return "contextual"

    normalized_importance = _normalize(requirement.importance)
    if requirement_group in {"technical_skill", "experience"}:
        if _is_must_have(requirement) and normalized_importance == "high":
            return "core"
        if _is_must_have(requirement) or normalized_importance in {"high", "medium"}:
            return "supporting"
        return "contextual"

    if requirement_group in {"education", "language", "domain"}:
        if _is_must_have(requirement) and normalized_importance == "high":
            return "core"
        if _is_must_have(requirement) or normalized_importance in {"high", "medium"}:
            return "supporting"
        return "contextual"

    return "contextual"


def _calculate_requirement_weight(
    requirement: Requirement,
    requirement_group: str,
    scoring_bucket: str,
) -> float:
    """Calculate the tier-aware importance of a single requirement for score coverage."""
    return (
        _get_importance_weight(requirement.importance)
        * _get_requirement_type_multiplier(requirement.requirement_type)
        * _get_category_score_multiplier(requirement_group)
        * _get_scoring_bucket_base_multiplier(scoring_bucket)
    )


def _calculate_bucket_coverage(
    weighted_score_sum: float,
    total_weight: float,
) -> float | None:
    """Return one normalized bucket coverage or None when the bucket has no score-bearing items."""

    if total_weight <= 0:
        return None
    return weighted_score_sum / total_weight


def _calculate_overall_score_from_bucket_coverages(
    core_coverage: float | None,
    supporting_coverage: float | None,
    contextual_coverage: float | None,
) -> float:
    """Blend tier-aware coverages into the final deterministic overall score."""

    weighted_sum = 0.0
    total_weight = 0.0

    for bucket_name, coverage in (
        ("core", core_coverage),
        ("supporting", supporting_coverage),
        ("contextual", contextual_coverage),
    ):
        if coverage is None:
            continue
        bucket_weight = _SCORING_BUCKET_BLEND_WEIGHTS[bucket_name]
        total_weight += bucket_weight
        weighted_sum += bucket_weight * coverage

    if total_weight <= 0:
        return 0.0

    return weighted_sum / total_weight


def _build_requirement_scoring_profile(
    record: RequirementEvaluationRecord,
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> RequirementScoringProfile:
    """Build the scoring profile for one evaluated requirement record."""

    scoring_bucket = _determine_scoring_bucket(
        record.requirement,
        record.requirement_group,
        priority_lookup,
    )
    return RequirementScoringProfile(
        bucket=scoring_bucket,
        weight=_calculate_requirement_weight(
            record.requirement,
            record.requirement_group,
            scoring_bucket,
        ),
        status_score=_get_bucket_status_score(
            scoring_bucket,
            record.requirement_match.match_status,
        ),
        priority_tier=_get_requirement_priority_tier(record.requirement, priority_lookup),
    )


def _calculate_match_score_breakdown(
    requirement_records: list[RequirementEvaluationRecord],
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> MatchScoreBreakdown:
    """Calculate the deterministic score breakdown used for fit and recommendation."""

    bucket_weight_sums = {
        "core": 0.0,
        "supporting": 0.0,
        "contextual": 0.0,
    }
    bucket_score_sums = {
        "core": 0.0,
        "supporting": 0.0,
        "contextual": 0.0,
    }
    bucket_requirement_counts = {
        "core": 0,
        "supporting": 0,
        "contextual": 0,
        "manual_confirmation": 0,
    }
    core_missing_count = 0
    core_missing_must_have_count = 0
    missing_must_have_count = 0
    core_partial_count = 0
    critical_not_verifiable_count = 0
    pending_confirmation_count = 0

    for record in requirement_records:
        profile = _build_requirement_scoring_profile(record, priority_lookup)
        requirement = record.requirement
        requirement_match = record.requirement_match
        bucket_requirement_counts[profile.bucket] += 1

        if profile.bucket == "manual_confirmation":
            if requirement_match.match_status != "matched":
                pending_confirmation_count += 1
            continue

        if profile.bucket == "core":
            if requirement_match.match_status == "missing":
                core_missing_count += 1
                if _is_must_have(requirement):
                    core_missing_must_have_count += 1
                    missing_must_have_count += 1
            elif requirement_match.match_status == "partial":
                core_partial_count += 1
            elif requirement_match.match_status == "not_verifiable":
                critical_not_verifiable_count += 1
        else:
            if requirement_match.match_status == "missing" and _is_must_have(requirement):
                missing_must_have_count += 1
            elif (
                requirement_match.match_status == "not_verifiable"
                and _is_must_have(requirement)
                and record.requirement_group not in {"soft_signal", "low_signal"}
            ):
                critical_not_verifiable_count += 1

        if profile.weight <= 0 or profile.status_score is None:
            continue

        bucket_weight_sums[profile.bucket] += profile.weight
        bucket_score_sums[profile.bucket] += profile.weight * profile.status_score

    core_coverage = _calculate_bucket_coverage(
        bucket_score_sums["core"],
        bucket_weight_sums["core"],
    )
    supporting_coverage = _calculate_bucket_coverage(
        bucket_score_sums["supporting"],
        bucket_weight_sums["supporting"],
    )
    contextual_coverage = _calculate_bucket_coverage(
        bucket_score_sums["contextual"],
        bucket_weight_sums["contextual"],
    )

    return MatchScoreBreakdown(
        overall_score=_calculate_overall_score_from_bucket_coverages(
            core_coverage,
            supporting_coverage,
            contextual_coverage,
        ),
        core_coverage=core_coverage,
        supporting_coverage=supporting_coverage,
        contextual_coverage=contextual_coverage,
        core_requirement_count=bucket_requirement_counts["core"],
        supporting_requirement_count=bucket_requirement_counts["supporting"],
        contextual_requirement_count=bucket_requirement_counts["contextual"],
        manual_confirmation_requirement_count=bucket_requirement_counts["manual_confirmation"],
        core_missing_count=core_missing_count,
        core_missing_must_have_count=core_missing_must_have_count,
        missing_must_have_count=missing_must_have_count,
        core_partial_count=core_partial_count,
        critical_not_verifiable_count=critical_not_verifiable_count,
        pending_confirmation_count=pending_confirmation_count,
    )


def _calculate_fit_classification(score_breakdown: MatchScoreBreakdown) -> str:
    """Classify fit from the tier-aware overall score while respecting core coverage."""

    overall_score = score_breakdown.overall_score
    core_coverage = score_breakdown.core_coverage

    if core_coverage is not None:
        if (
            overall_score >= _HIGH_FIT_THRESHOLD
            and core_coverage >= 0.72
            and score_breakdown.core_missing_must_have_count == 0
        ):
            return "high"
        if overall_score >= _MEDIUM_FIT_THRESHOLD and core_coverage >= 0.4:
            return "medium"
        return "low"

    if overall_score >= _HIGH_FIT_THRESHOLD:
        return "high"
    if overall_score >= _MEDIUM_FIT_THRESHOLD:
        return "medium"
    return "low"


def _build_recommendation(
    fit_classification: str,
    score_breakdown: MatchScoreBreakdown,
) -> str:
    """Build the product recommendation from the tier-aware fit breakdown."""

    core_coverage = score_breakdown.core_coverage
    if score_breakdown.missing_must_have_count >= 2:
        return "do_not_recommend"
    if core_coverage is not None and core_coverage < 0.35:
        return "do_not_recommend"
    if fit_classification == "low":
        return "do_not_recommend"
    if score_breakdown.missing_must_have_count >= 1:
        return "generate_with_caution"
    if score_breakdown.critical_not_verifiable_count >= 1:
        return "generate_with_caution"
    if score_breakdown.core_partial_count >= 2:
        return "generate_with_caution"
    if score_breakdown.pending_confirmation_count >= 1 and fit_classification == "high":
        return "generate_with_caution"
    if fit_classification == "high":
        return "generate"
    return "generate_with_caution"


def _get_requirement_priority_label(
    requirement: Requirement,
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> str | None:
    """Return a short user-facing label for one requirement priority tier."""

    priority_item = priority_lookup.get(requirement.id)
    if priority_item is None:
        return None

    if priority_item.priority_tier == "core":
        return "core signal"
    if priority_item.priority_tier == "supporting":
        return "supporting signal"
    return "low-signal requirement"


def _order_requirement_records(
    requirement_records: list[RequirementEvaluationRecord],
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> list[RequirementEvaluationRecord]:
    """Return requirement records in AI-prioritized order with stable fallback ordering."""

    if not priority_lookup:
        return list(requirement_records)

    return sorted(
        requirement_records,
        key=lambda record: build_requirement_priority_sort_key(
            record.requirement,
            record.original_index,
            priority_lookup,
        ),
    )


def _build_strengths(
    requirement_records: list[RequirementEvaluationRecord],
    keyword_coverage: list[str],
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> list[str]:
    """Build a short list of candidate strengths relative to the job posting."""
    strengths: list[str] = []

    for record in requirement_records:
        if record.requirement_match.match_status != "matched":
            continue

        priority_label = _get_requirement_priority_label(record.requirement, priority_lookup)
        if priority_label is not None:
            _append_unique(
                strengths,
                f"Matched {priority_label}: {record.requirement.text}",
            )
            continue

        _append_unique(strengths, f"Matched requirement: {record.requirement.text}")

    if keyword_coverage:
        _append_unique(
            strengths,
            f"Covered job keywords: {', '.join(keyword_coverage)}",
        )

    return strengths


def _build_gaps(
    requirement_records: list[RequirementEvaluationRecord],
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> list[str]:
    """Build a short list of gaps, partial matches, and non-verifiable requirements."""
    gaps: list[str] = []

    for record in requirement_records:
        requirement = record.requirement
        requirement_match = record.requirement_match
        priority_label = _get_requirement_priority_label(requirement, priority_lookup)
        if priority_label is None:
            partial_prefix = "Partially matched requirement"
            missing_prefix = "Missing requirement"
            unverifiable_prefix = "Could not verify requirement"
        else:
            partial_prefix = f"Partially matched {priority_label}"
            missing_prefix = f"Missing {priority_label}"
            unverifiable_prefix = f"Could not verify {priority_label}"

        if requirement_match.match_status == "partial":
            if requirement_match.missing_elements:
                _append_unique(
                    gaps,
                    (
                        f"{partial_prefix}: {requirement.text}. "
                        f"Still needs: {', '.join(requirement_match.missing_elements)}"
                    ),
                )
            else:
                _append_unique(gaps, f"{partial_prefix}: {requirement_match.explanation}")
        elif requirement_match.match_status == "missing":
            if requirement_match.missing_elements:
                _append_unique(
                    gaps,
                    (
                        f"{missing_prefix}: {requirement.text}. "
                        f"Missing: {', '.join(requirement_match.missing_elements)}"
                    ),
                )
            else:
                _append_unique(gaps, f"{missing_prefix}: {requirement.text}.")
        elif requirement_match.match_status == "not_verifiable":
            _append_unique(
                gaps,
                f"{unverifiable_prefix}: {requirement.text}. {requirement_match.explanation}",
            )

    return gaps


def _build_final_summary(
    job_title: str,
    score_breakdown: MatchScoreBreakdown,
    overall_score: float,
    fit_classification: str,
    recommendation: str,
    matched_requirements_count: int,
    partial_requirements_count: int,
    missing_requirements_count: int,
    not_verifiable_requirements_count: int,
    total_requirements: int,
    keyword_coverage: list[str],
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
    semantic_upgrade_count: int = 0,
) -> str:
    """Build the final user-facing summary of the matching result."""
    covered_keywords = ", ".join(keyword_coverage) if keyword_coverage else "none"
    coverage_parts: list[str] = []
    if score_breakdown.core_coverage is not None:
        coverage_parts.append(f"core {score_breakdown.core_coverage:.2f}")
    if score_breakdown.supporting_coverage is not None:
        coverage_parts.append(f"supporting {score_breakdown.supporting_coverage:.2f}")
    if score_breakdown.contextual_coverage is not None:
        coverage_parts.append(f"contextual {score_breakdown.contextual_coverage:.2f}")
    coverage_summary = ", ".join(coverage_parts) if coverage_parts else "none"

    summary = (
        f"Profile fit for '{job_title}' is {fit_classification} with score "
        f"{overall_score:.2f}. Requirements summary: {matched_requirements_count} matched, "
        f"{partial_requirements_count} partial, {missing_requirements_count} missing, "
        f"{not_verifiable_requirements_count} not verifiable out of {total_requirements}. "
        f"Tier-aware coverage: {coverage_summary}. Recommendation: {recommendation}. "
        f"Covered job keywords: {covered_keywords}."
    )
    if score_breakdown.core_missing_count or score_breakdown.core_partial_count or score_breakdown.critical_not_verifiable_count:
        summary = (
            f"{summary} Critical fit signals: {score_breakdown.core_missing_count} core missing, "
            f"{score_breakdown.core_partial_count} core partial, "
            f"{score_breakdown.critical_not_verifiable_count} critical not verifiable."
        )
    if score_breakdown.pending_confirmation_count:
        summary = (
            f"{summary} Pending confirmations: {score_breakdown.pending_confirmation_count} "
            "operational or manual-confirmation item(s) remain unresolved."
        )
    elif not_verifiable_requirements_count:
        summary = (
            f"{summary} Some requirements could not be verified from the currently stored profile data."
        )
    if priority_lookup:
        tier_counts = count_requirement_priority_tiers(priority_lookup)
        summary = (
            f"{summary} AI requirement prioritization identified "
            f"{tier_counts['core']} core, {tier_counts['supporting']} supporting, "
            f"and {tier_counts['low_signal']} low-signal requirements."
        )
    if semantic_upgrade_count:
        summary = (
            f"{summary} AI semantic requirement matching improved {semantic_upgrade_count} "
            f"requirement decision{'' if semantic_upgrade_count == 1 else 's'} using grounded candidate evidence."
        )
    return summary


def analyze_match_basic(
    payload: MatchAnalysisRequest,
    *,
    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem] | None = None,
    candidate_profile_understanding: CandidateProfileUnderstanding | None = None,
) -> MatchResult:
    """Analyze candidate-vs-job fit using category-aware deterministic evidence."""
    profile_understanding = candidate_profile_understanding
    if profile_understanding is None and _has_configured_openai_api_key():
        profile_understanding = get_candidate_profile_understanding(payload.candidate_profile)

    context = _build_candidate_evidence_context(
        payload,
        candidate_profile_understanding=profile_understanding,
    )
    priority_lookup = requirement_priority_lookup
    if priority_lookup is None and _has_configured_openai_api_key():
        priority_lookup = get_requirement_priority_lookup(payload.job_posting)
    if priority_lookup is None:
        priority_lookup = {}
    grouped_matches = [
        _evaluate_requirement(requirement, context)
        for requirement in payload.job_posting.requirements
    ]
    requirement_groups = [group_name for group_name, _ in grouped_matches]
    requirement_matches = [match for _, match in grouped_matches]
    requirement_records = [
        RequirementEvaluationRecord(
            original_index=index,
            requirement=requirement,
            requirement_group=group_name,
            requirement_match=requirement_match,
        )
        for index, (requirement, group_name, requirement_match) in enumerate(
            zip(
                payload.job_posting.requirements,
                requirement_groups,
                requirement_matches,
            )
        )
    ]
    requirement_records, semantic_upgrade_count = _apply_ai_requirement_candidate_matching(
        payload,
        requirement_records,
        context,
        priority_lookup,
    )
    requirement_matches = [record.requirement_match for record in requirement_records]
    ordered_requirement_records = _order_requirement_records(requirement_records, priority_lookup)
    ordered_requirement_matches = [
        record.requirement_match for record in ordered_requirement_records
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
    not_verifiable_requirements_count = sum(
        1
        for requirement_match in requirement_matches
        if requirement_match.match_status == "not_verifiable"
    )

    total_requirements = len(payload.job_posting.requirements)
    score_breakdown = _calculate_match_score_breakdown(
        requirement_records,
        priority_lookup,
    )
    rounded_score = round(score_breakdown.overall_score, 2)
    fit_classification = _calculate_fit_classification(score_breakdown)
    recommendation = _build_recommendation(
        fit_classification,
        score_breakdown,
    )

    keyword_coverage = build_display_keywords(
        [
            keyword
            for keyword in build_reportable_offer_terms(
                payload.job_posting,
                requirement_priority_lookup=priority_lookup,
            )
            if _normalize(keyword) in context.candidate_keywords
        ],
        max_items=_MAX_KEYWORD_COVERAGE,
    )

    strengths = _build_strengths(
        ordered_requirement_records,
        keyword_coverage,
        priority_lookup,
    )
    gaps = _build_gaps(
        ordered_requirement_records,
        priority_lookup,
    )

    return MatchResult(
        overall_score=rounded_score,
        fit_classification=fit_classification,
        recommendation=recommendation,
        requirement_matches=ordered_requirement_matches,
        strengths=strengths,
        gaps=gaps,
        keyword_coverage=keyword_coverage,
        final_summary=_build_final_summary(
            payload.job_posting.title,
            score_breakdown,
            rounded_score,
            fit_classification,
            recommendation,
            matched_requirements_count,
            partial_requirements_count,
            missing_requirements_count,
            not_verifiable_requirements_count,
            total_requirements,
            keyword_coverage,
            priority_lookup,
            semantic_upgrade_count,
        ),
    )
