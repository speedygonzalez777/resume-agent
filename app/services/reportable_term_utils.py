"""Helpers for separating CV-usable offer terms from thresholds, modifiers and metadata."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from app.models.job import JobPosting, Requirement
from app.services.display_keyword_utils import build_display_keywords
from app.services.openai_requirement_priority_service import (
    OpenAIRequirementPriorityItem,
    build_requirement_priority_sort_key,
)

_TOKEN_RE = re.compile(r"[\w+/.#-]+", flags=re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")
_SHORT_TERM_CANONICAL_MAP = {
    "ai": "AI",
    "api": "API",
    "aws": "AWS",
    "cad": "CAD",
    "erp": "ERP",
    "gcp": "GCP",
    "hmi": "HMI",
    "llm": "LLM",
    "mes": "MES",
    "ml": "ML",
    "nlp": "NLP",
    "plc": "PLC",
    "sap": "SAP",
    "scada": "SCADA",
    "scrum": "SCRUM",
    "sql": "SQL",
    "ui": "UI",
    "ux": "UX",
}
_GENERIC_SINGLE_TOKENS = {
    "dev",
    "developer",
    "deweloper",
    "engineer",
    "engineering",
    "experience",
    "framework",
    "frameworks",
    "frameworki",
    "knowledge",
    "skill",
    "skills",
    "system",
    "systems",
    "systemy",
    "technology",
    "technologies",
    "work",
    "znajomosc",
    "doswiadczenie",
}
_LEADING_NOISE_TOKENS = {
    "at",
    "basic",
    "bardzo",
    "co",
    "commercial",
    "commercially",
    "degree",
    "doswiadczenie",
    "experience",
    "familiarity",
    "fluent",
    "for",
    "framework",
    "frameworks",
    "frameworki",
    "good",
    "hands-on",
    "hands",
    "in",
    "jako",
    "knowledge",
    "least",
    "masters",
    "master",
    "mile",
    "min",
    "minimum",
    "najmniej",
    "of",
    "plus",
    "preferowane",
    "preferowany",
    "preferowana",
    "preferred",
    "rok",
    "roku",
    "lata",
    "lat",
    "spoken",
    "strong",
    "very",
    "w",
    "with",
    "written",
    "widziany",
    "widziana",
    "widziane",
    "year",
    "years",
    "z",
    "ze",
    "znajomosc",
}
_TRAILING_NOISE_TOKENS = {
    "doswiadczenie",
    "experience",
    "framework",
    "frameworks",
    "frameworki",
    "knowledge",
    "skill",
    "skills",
    "technologies",
    "technology",
    "znajomosc",
}
_MODIFIER_MARKERS = {
    "at least",
    "co najmniej",
    "mile widziany",
    "mile widziana",
    "mile widziane",
    "must have",
    "must-have",
    "nice to have",
    "nice-to-have",
    "preferowane",
    "preferowany",
    "preferowana",
    "preferred",
}
_MANUAL_CONFIRMATION_MARKERS = {
    "32 hours",
    "availability",
    "authorized",
    "authorization",
    "monday-friday",
    "monday friday",
    "relocation",
    "schedule",
    "start date",
    "work authorization",
    "work permit",
}
_WORK_MODE_TERMS = {
    "hybrid",
    "onsite",
    "on-site",
    "remote",
    "hybrydowa",
    "hybrydowy",
    "hybrydowe",
    "stacjonarna",
    "stacjonarny",
    "stacjonarne",
    "zdalna",
    "zdalny",
    "zdalne",
}
_EMPLOYMENT_TYPE_TERMS = {
    "b2b",
    "contract",
    "full-time",
    "full time",
    "part-time",
    "part time",
    "uop",
    "umowa o prace",
    "umowa o pracę",
    "zlecenie",
}
_LANGUAGE_LEVEL_TOKENS = {
    "a1",
    "a2",
    "advanced",
    "b1",
    "b2",
    "business",
    "c1",
    "c2",
    "conversational",
    "fluent",
    "professional",
    "spoken",
    "written",
}
_THRESHOLD_PATTERNS = (
    re.compile(r"\bmin\.?\s*\d+(?:[.,]\d+)?\b", re.IGNORECASE),
    re.compile(r"\bminimum\s+\d+(?:[.,]\d+)?\b", re.IGNORECASE),
    re.compile(r"\bat least\s+\d+(?:[.,]\d+)?\b", re.IGNORECASE),
    re.compile(r"\bco najmniej\s+\d+(?:[.,]\d+)?\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:[.,]\d+)?\s*\+?\s*(?:rok|roku|lata|lat|year|years|month|months|miesiac|miesiace|miesiecy)\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:h|hr|hrs|hour|hours|godzin(?:y)?|tygodniowo|weekly)\b", re.IGNORECASE),
)
_APPLICATION_CONSTRAINT_PATTERNS = (
    re.compile(r"\b(?:availability|available|monday-friday|monday friday|schedule|relocation|start date)\b", re.IGNORECASE),
    re.compile(r"\b(?:work authorization|work permit|authorized to work|age|clearance)\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:h|hr|hrs|hour|hours|godzin(?:y)?)\s*/?\s*(?:week|weekly|tydzien|tydzien|tygodniowo)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class OfferTermCandidate:
    """One raw offer-side term candidate together with its semantic role."""

    raw_value: str
    primary_role: Literal[
        "reportable_term",
        "matching_constraint",
        "modifier",
        "generic_wrapper",
        "metadata",
        "manual_confirmation",
        "noise",
    ]
    reportable_term: str | None
    source_kind: Literal["requirement", "job_keyword"]
    requirement_id: str | None = None


@dataclass(frozen=True)
class ReportableOfferTermsContext:
    """Canonical offer-side term context reused across downstream report/CV flows."""

    reportable_terms: list[str]
    requirement_terms_lookup: dict[str, list[str]]
    top_level_terms: list[str]


def build_reportable_offer_terms(
    job_posting: JobPosting,
    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem] | None = None,
) -> list[str]:
    """Build the final clean offer-side term layer used by report/explainability/CV."""
    return build_reportable_offer_terms_context(
        job_posting,
        requirement_priority_lookup=requirement_priority_lookup,
    ).reportable_terms


def build_requirement_reportable_terms_lookup(
    job_posting: JobPosting,
    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem] | None = None,
) -> dict[str, list[str]]:
    """Build cleaned, requirement-level reportable terms for later grounded highlighting."""
    return build_reportable_offer_terms_context(
        job_posting,
        requirement_priority_lookup=requirement_priority_lookup,
    ).requirement_terms_lookup


def build_reportable_offer_terms_context(
    job_posting: JobPosting,
    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem] | None = None,
) -> ReportableOfferTermsContext:
    """Build one canonical offer-side term context for downstream report and CV flows."""

    priority_lookup = requirement_priority_lookup or {}
    top_level_terms = _build_top_level_reportable_terms(
        job_posting,
        priority_lookup,
    )
    requirement_terms_lookup = _build_requirement_reportable_terms_lookup(
        job_posting,
        priority_lookup,
        top_level_terms,
    )

    reportable_terms: list[str] = []
    for requirement in _get_ordered_requirements(job_posting, priority_lookup):
        for term in requirement_terms_lookup.get(requirement.id, []):
            _append_unique(reportable_terms, term)

    for term in top_level_terms:
        _append_unique(reportable_terms, term)

    return ReportableOfferTermsContext(
        reportable_terms=build_display_keywords(reportable_terms),
        requirement_terms_lookup=requirement_terms_lookup,
        top_level_terms=top_level_terms,
    )


def _build_top_level_reportable_terms(
    job_posting: JobPosting,
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> list[str]:
    """Treat parser-derived top-level keywords as the primary source of final offer terms."""

    blocked_terms = _build_blocked_reportable_terms(
        job_posting,
        priority_lookup,
        top_level_terms=[],
    )
    top_level_terms: list[str] = []

    for raw_keyword in job_posting.keywords:
        candidate = parse_offer_term_candidate(
            raw_keyword,
            source_kind="job_keyword",
            job_posting=job_posting,
        )
        if (
            candidate.primary_role == "reportable_term"
            and candidate.reportable_term
            and _ascii_key(candidate.reportable_term) not in blocked_terms
        ):
            _append_unique(top_level_terms, candidate.reportable_term)

    return build_display_keywords(top_level_terms)


def _build_requirement_reportable_terms_lookup(
    job_posting: JobPosting,
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
    top_level_terms: list[str],
) -> dict[str, list[str]]:
    """Build grounded requirement terms while keeping top-level parser keywords authoritative."""

    terms_lookup: dict[str, list[str]] = {}
    top_level_term_lookup = {_ascii_key(term): term for term in top_level_terms}

    for requirement in _get_ordered_requirements(job_posting, priority_lookup):
        if _should_skip_requirement_for_reportable_terms(requirement, priority_lookup):
            terms_lookup[requirement.id] = []
            continue

        preferred_terms: list[str] = []
        supplemental_terms: list[str] = []

        for raw_keyword in requirement.extracted_keywords:
            candidate = parse_offer_term_candidate(
                raw_keyword,
                source_kind="requirement",
                requirement=requirement,
                job_posting=job_posting,
            )
            if candidate.reportable_term is None:
                continue

            normalized_term = _ascii_key(candidate.reportable_term)
            canonical_top_level_term = top_level_term_lookup.get(normalized_term)
            if canonical_top_level_term is not None:
                _append_unique(preferred_terms, canonical_top_level_term)
                continue

            if (
                candidate.primary_role in {"reportable_term", "matching_constraint", "modifier"}
                and _should_allow_requirement_only_term(candidate.reportable_term, requirement)
            ):
                _append_unique(supplemental_terms, candidate.reportable_term)

        if not preferred_terms:
            for fallback_term in _collect_requirement_text_fallback_terms(requirement, top_level_terms):
                _append_unique(preferred_terms, fallback_term)

        terms_lookup[requirement.id] = build_display_keywords(
            [*preferred_terms, *supplemental_terms]
        )

    return terms_lookup


def _build_blocked_reportable_terms(
    job_posting: JobPosting,
    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem] | None = None,
    *,
    top_level_terms: list[str],
) -> set[str]:
    """Collect reportable-looking terms that should stay excluded because their requirement is skipped."""

    priority_lookup = requirement_priority_lookup or {}
    blocked_terms: set[str] = set()

    for requirement in _get_ordered_requirements(job_posting, priority_lookup):
        if not _should_skip_requirement_for_reportable_terms(requirement, priority_lookup):
            continue

        for raw_keyword in requirement.extracted_keywords:
            candidate = parse_offer_term_candidate(
                raw_keyword,
                source_kind="requirement",
                requirement=requirement,
                job_posting=job_posting,
            )
            if candidate.reportable_term:
                blocked_terms.add(_ascii_key(candidate.reportable_term))

        for fallback_term in _collect_requirement_text_fallback_terms(requirement, top_level_terms):
            blocked_terms.add(_ascii_key(fallback_term))

    return blocked_terms


def parse_offer_term_candidate(
    raw_value: str | None,
    *,
    source_kind: Literal["requirement", "job_keyword"],
    job_posting: JobPosting,
    requirement: Requirement | None = None,
) -> OfferTermCandidate:
    """Classify one raw term candidate and optionally salvage a clean reportable term from it."""

    cleaned_value = _normalize_term(raw_value)
    if not cleaned_value:
        return OfferTermCandidate(
            raw_value="",
            primary_role="noise",
            reportable_term=None,
            source_kind=source_kind,
            requirement_id=requirement.id if requirement is not None else None,
        )

    manual_confirmation = _looks_like_manual_confirmation(cleaned_value, requirement)
    metadata = _looks_like_metadata(cleaned_value, job_posting)
    threshold = _looks_like_threshold(cleaned_value)
    modifier = _looks_like_modifier(cleaned_value)
    reportable_term = _extract_reportable_term(cleaned_value)

    if manual_confirmation:
        primary_role = "manual_confirmation"
    elif metadata:
        primary_role = "metadata"
    elif threshold:
        primary_role = "matching_constraint"
    elif modifier:
        primary_role = "modifier"
    elif reportable_term:
        primary_role = "reportable_term"
    else:
        primary_role = "generic_wrapper"

    return OfferTermCandidate(
        raw_value=cleaned_value,
        primary_role=primary_role,
        reportable_term=reportable_term,
        source_kind=source_kind,
        requirement_id=requirement.id if requirement is not None else None,
    )


def _get_ordered_requirements(
    job_posting: JobPosting,
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> list[Requirement]:
    if not priority_lookup:
        return list(job_posting.requirements)

    return [
        requirement
        for _, requirement in sorted(
            enumerate(job_posting.requirements),
            key=lambda item: build_requirement_priority_sort_key(
                item[1],
                item[0],
                priority_lookup,
            ),
        )
    ]


def _should_skip_requirement_for_reportable_terms(
    requirement: Requirement,
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> bool:
    priority_item = priority_lookup.get(requirement.id)
    if priority_item is not None and priority_item.priority_tier == "low_signal":
        return True
    return _looks_like_manual_confirmation(requirement.text, requirement)


def _normalize_term(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip(" ,;:.").strip()


def _ascii_key(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(character for character in normalized if not unicodedata.combining(character))
    return _WHITESPACE_RE.sub(" ", without_accents).strip(" ,;:.").strip().lower()


def _tokenize(value: str) -> list[str]:
    return _TOKEN_RE.findall(value)


def _canonicalize_token(value: str) -> str:
    normalized_key = _ascii_key(value)
    if normalized_key in _SHORT_TERM_CANONICAL_MAP:
        return _SHORT_TERM_CANONICAL_MAP[normalized_key]
    return value


def _canonicalize_phrase(tokens: list[str]) -> str:
    return " ".join(_canonicalize_token(token) for token in tokens)


def _looks_like_modifier(value: str) -> bool:
    normalized = _ascii_key(value)
    if any(marker in normalized for marker in _MODIFIER_MARKERS):
        return True
    normalized_tokens = [_ascii_key(token) for token in _tokenize(value)]
    return bool(normalized_tokens and normalized_tokens[0] in {"preferred", "preferowane", "mile"})


def _looks_like_threshold(value: str) -> bool:
    normalized = _ascii_key(value)
    if any(pattern.search(normalized) for pattern in _THRESHOLD_PATTERNS):
        return True
    normalized_tokens = [_ascii_key(token) for token in _tokenize(value)]
    return any(token in _LANGUAGE_LEVEL_TOKENS for token in normalized_tokens) and len(normalized_tokens) == 1


def _looks_like_manual_confirmation(value: str, requirement: Requirement | None = None) -> bool:
    normalized = _ascii_key(value)
    if any(pattern.search(normalized) for pattern in _APPLICATION_CONSTRAINT_PATTERNS):
        return True

    requirement_text = _ascii_key(requirement.text) if requirement is not None else ""
    requirement_category = _ascii_key(requirement.category) if requirement is not None else ""
    if requirement_category == "other" and any(marker in requirement_text for marker in _MANUAL_CONFIRMATION_MARKERS):
        return True
    return any(marker in normalized for marker in _MANUAL_CONFIRMATION_MARKERS)


def _looks_like_metadata(value: str, job_posting: JobPosting) -> bool:
    normalized = _ascii_key(value)
    metadata_values = {
        *[_ascii_key(job_posting.location)],
        *[_ascii_key(job_posting.work_mode)],
        *[_ascii_key(job_posting.employment_type)],
        *[_ascii_key(job_posting.seniority_level)],
        *_WORK_MODE_TERMS,
        *_EMPLOYMENT_TYPE_TERMS,
    }
    location_tokens = {_ascii_key(token) for token in _tokenize(job_posting.location or "") if token}
    return normalized in metadata_values or normalized in location_tokens


def _extract_reportable_term(value: str) -> str | None:
    original_tokens = _tokenize(value)
    normalized_tokens = [_ascii_key(token) for token in original_tokens]
    if not original_tokens:
        return None

    start_index = 0
    while start_index < len(normalized_tokens) and _token_is_leading_noise(normalized_tokens[start_index]):
        start_index += 1

    end_index = len(normalized_tokens)
    while end_index > start_index and normalized_tokens[end_index - 1] in _TRAILING_NOISE_TOKENS:
        end_index -= 1

    candidate_tokens = original_tokens[start_index:end_index]
    candidate_normalized_tokens = normalized_tokens[start_index:end_index]
    if not candidate_tokens:
        return None

    candidate_phrase = _canonicalize_phrase(candidate_tokens)
    candidate_key = _ascii_key(candidate_phrase)
    if not candidate_key:
        return None
    if _looks_like_threshold(candidate_phrase):
        return None
    if candidate_key in _GENERIC_SINGLE_TOKENS and len(candidate_tokens) == 1:
        return None
    if not _contains_meaningful_token(candidate_normalized_tokens):
        return None
    if _looks_like_modifier(candidate_phrase):
        return None
    return candidate_phrase


def _collect_requirement_text_fallback_terms(
    requirement: Requirement,
    top_level_terms: list[str],
) -> list[str]:
    """Recover reportable terms from requirement text only through already-clean offer terms."""
    normalized_requirement_text = _ascii_key(requirement.text)
    if not normalized_requirement_text:
        return []

    fallback_terms: list[str] = []
    for term in top_level_terms:
        normalized_term = _ascii_key(term)
        if len(normalized_term) < 3:
            continue
        if normalized_term in normalized_requirement_text:
            _append_unique(fallback_terms, term)

    return fallback_terms


def _should_allow_requirement_only_term(term: str, requirement: Requirement) -> bool:
    """Admit requirement-only terms conservatively so raw requirement fragments do not dominate."""

    normalized_term = _ascii_key(term)
    if not normalized_term:
        return False

    normalized_category = _ascii_key(requirement.category)

    if _looks_like_threshold(term) or _looks_like_modifier(term):
        return False

    tokens = _tokenize(term)
    normalized_tokens = [_ascii_key(token) for token in tokens]
    if not _contains_meaningful_token(normalized_tokens):
        return False

    if len(tokens) == 1:
        if any(character.isupper() for character in term):
            return True
        if any(symbol in term for symbol in "+/#.-"):
            return True
        return normalized_category in {"language", "education"}

    if any(character.isupper() for character in term):
        return True

    if any(symbol in term for symbol in "+/#.-"):
        return True

    if normalized_category in {"language", "education"}:
        return True

    return False


def _token_is_leading_noise(normalized_token: str) -> bool:
    if not normalized_token:
        return True
    if normalized_token.isdigit():
        return True
    if normalized_token in _LEADING_NOISE_TOKENS:
        return True
    if normalized_token in _LANGUAGE_LEVEL_TOKENS:
        return True
    return False


def _contains_meaningful_token(normalized_tokens: list[str]) -> bool:
    for token in normalized_tokens:
        if not token or token.isdigit():
            continue
        if token in _GENERIC_SINGLE_TOKENS:
            continue
        if token in _LEADING_NOISE_TOKENS or token in _TRAILING_NOISE_TOKENS:
            continue
        if token in _LANGUAGE_LEVEL_TOKENS:
            continue
        if len(token) < 3 and token not in _SHORT_TERM_CANONICAL_MAP:
            continue
        return True
    return False


def _append_unique(target: list[str], value: str | None) -> None:
    stripped_value = value.strip() if value else ""
    if stripped_value and stripped_value not in target:
        target.append(stripped_value)
