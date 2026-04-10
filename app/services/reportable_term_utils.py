"""Helpers for classifying offer-side signals before they leak into generation-facing keyword layers."""

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

OfferSignalRole = Literal[
    "skill_or_tool",
    "domain",
    "education_field_or_signal",
    "job_meta",
    "constraint",
    "generic_wrapper_or_noise",
]
OfferSignalAllowedUse = Literal[
    "generation_allowed",
    "matching_only",
    "warning_or_manual_confirmation",
    "ranking_only",
    "debug_only",
]
OfferSignalSource = Literal["job_keyword", "requirement_keyword", "job_metadata"]

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
    "data",
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
    "technologia",
    "technology",
    "technologies",
    "work",
    "znajomosc",
    "doswiadczenie",
}
_GENERIC_MULTIWORD_MARKERS = {
    "bardzo dobra znajomosc",
    "bardzo dobra znajomość",
    "commercial experience",
    "dobra znajomosc",
    "dobra znajomość",
    "good knowledge",
    "hands-on experience",
    "kierunki techniczne",
    "production projects",
    "professional experience",
    "projekty produkcyjne",
    "scalable services",
    "serwowanie modeli",
    "skalowalne uslugi",
    "skalowalne usługi",
    "technical fields",
    "technical direction",
    "technical studies",
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
_WORK_MODE_NORMALIZATION = {
    "hybrid": ("Hybrid", "hybrid"),
    "hybrydowa": ("Hybrid", "hybrid"),
    "hybrydowy": ("Hybrid", "hybrid"),
    "hybrydowe": ("Hybrid", "hybrid"),
    "remote": ("Remote", "remote"),
    "zdalna": ("Remote", "remote"),
    "zdalny": ("Remote", "remote"),
    "zdalne": ("Remote", "remote"),
    "onsite": ("On-site", "onsite"),
    "on-site": ("On-site", "onsite"),
    "stacjonarna": ("On-site", "onsite"),
    "stacjonarny": ("On-site", "onsite"),
    "stacjonarne": ("On-site", "onsite"),
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
    "umowa zlecenie",
    "zlecenie",
}
_EMPLOYMENT_TYPE_NORMALIZATION = {
    "b2b": ("B2B", "b2b"),
    "contract": ("Contract", "contract"),
    "full-time": ("Full-time", "full-time"),
    "full time": ("Full-time", "full-time"),
    "part-time": ("Part-time", "part-time"),
    "part time": ("Part-time", "part-time"),
    "uop": ("Employment contract", "employment_contract"),
    "umowa o prace": ("Employment contract", "employment_contract"),
    "umowa o pracę": ("Employment contract", "employment_contract"),
    "umowa zlecenie": ("Contract", "contract"),
    "zlecenie": ("Contract", "contract"),
}
_INTERNSHIP_NORMALIZATION = {
    "intern": ("Internship", "internship"),
    "internship": ("Internship", "internship"),
    "program intern": ("Internship", "internship"),
    "program internship": ("Internship", "internship"),
    "program stazowy": ("Internship", "internship"),
    "staz": ("Internship", "internship"),
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
_EDUCATION_SIGNAL_TOKENS = {
    "absolwent",
    "bachelor",
    "degree",
    "education",
    "graduate",
    "graduated",
    "inzynier",
    "kierunek",
    "kierunki",
    "licencjat",
    "magister",
    "master",
    "masters",
    "student",
    "studia",
    "studies",
    "university",
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
    re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:h|hr|hrs|hour|hours|godzin(?:y)?)\s*/?\s*(?:week|weekly|tydzien|tygodniowo)\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:month|months|miesiac|miesiace|miesiecy)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class OfferSignal:
    """One canonical offer-side signal together with its downstream usage constraints."""

    raw_label: str
    label: str
    normalized_label: str
    role: OfferSignalRole
    allowed_uses: tuple[OfferSignalAllowedUse, ...]
    source: OfferSignalSource
    linked_requirement_ids: tuple[str, ...] = ()
    suppression_reason: str | None = None
    generation_candidate_label: str | None = None

    def to_debug_dict(self) -> dict[str, object]:
        """Serialize the signal into a JSON-friendly structure for backend debug output."""

        return {
            "raw_label": self.raw_label,
            "label": self.label,
            "normalized_label": self.normalized_label,
            "role": self.role,
            "allowed_uses": list(self.allowed_uses),
            "source": self.source,
            "linked_requirement_ids": list(self.linked_requirement_ids),
            "suppression_reason": self.suppression_reason,
            "generation_candidate_label": self.generation_candidate_label,
        }


@dataclass(frozen=True)
class ReportableOfferTermsContext:
    """Canonical offer-side signal context reused across downstream report and CV flows."""

    reportable_terms: list[str]
    requirement_terms_lookup: dict[str, list[str]]
    top_level_terms: list[str]
    signal_inventory: list[OfferSignal]
    generation_eligible_offer_terms: list[str]
    matching_only_signals: list[OfferSignal]
    manual_confirmation_items: list[OfferSignal]
    suppressed_terms: list[OfferSignal]
    role_alignment_signals: list[OfferSignal]

    def to_debug_payload(self) -> dict[str, object]:
        """Build a structured backend-facing debug breakdown for manual inspection."""

        return {
            "generation_eligible_offer_terms": list(self.generation_eligible_offer_terms),
            "matching_only_signals": [signal.to_debug_dict() for signal in self.matching_only_signals],
            "manual_confirmation_items": [signal.to_debug_dict() for signal in self.manual_confirmation_items],
            "suppressed_terms": [signal.to_debug_dict() for signal in self.suppressed_terms],
            "role_alignment_signals": [signal.to_debug_dict() for signal in self.role_alignment_signals],
            "top_level_offer_terms": list(self.top_level_terms),
            "requirement_generation_terms_lookup": dict(self.requirement_terms_lookup),
            "signal_inventory": [signal.to_debug_dict() for signal in self.signal_inventory],
        }


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
    """Build cleaned, requirement-level generation-facing terms for later grounded highlighting."""

    return build_reportable_offer_terms_context(
        job_posting,
        requirement_priority_lookup=requirement_priority_lookup,
    ).requirement_terms_lookup


def build_reportable_offer_terms_context(
    job_posting: JobPosting,
    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem] | None = None,
) -> ReportableOfferTermsContext:
    """Build one canonical offer-side signal inventory for downstream report and CV flows."""

    priority_lookup = requirement_priority_lookup or {}
    top_level_signals = _build_top_level_signals(job_posting)
    metadata_signals = _build_metadata_signals(job_posting)
    requirement_signals_lookup = _build_requirement_signal_lookup(job_posting, priority_lookup)

    blocked_terms = _build_blocked_reportable_terms(
        job_posting,
        priority_lookup,
        requirement_signals_lookup,
    )
    top_level_terms = _build_top_level_reportable_terms(top_level_signals, blocked_terms)
    requirement_terms_lookup = _build_requirement_reportable_terms_lookup(
        job_posting,
        priority_lookup,
        top_level_terms,
        requirement_signals_lookup,
    )

    generation_eligible_offer_terms: list[str] = []
    for requirement in _get_ordered_requirements(job_posting, priority_lookup):
        for term in requirement_terms_lookup.get(requirement.id, []):
            _append_unique(generation_eligible_offer_terms, term)
    for term in top_level_terms:
        _append_unique(generation_eligible_offer_terms, term)

    signal_inventory = _build_signal_inventory(
        top_level_signals=top_level_signals,
        metadata_signals=metadata_signals,
        requirement_signals_lookup=requirement_signals_lookup,
        generation_eligible_offer_terms=generation_eligible_offer_terms,
        requirement_terms_lookup=requirement_terms_lookup,
    )

    matching_only_signals = [
        signal
        for signal in signal_inventory
        if "matching_only" in signal.allowed_uses
        and "generation_allowed" not in signal.allowed_uses
        and "warning_or_manual_confirmation" not in signal.allowed_uses
    ]
    manual_confirmation_items = [
        signal for signal in signal_inventory if "warning_or_manual_confirmation" in signal.allowed_uses
    ]
    suppressed_terms = [signal for signal in signal_inventory if signal.suppression_reason]
    role_alignment_signals = [
        signal for signal in signal_inventory if _is_role_alignment_signal(signal)
    ]

    cleaned_generation_terms = build_display_keywords(generation_eligible_offer_terms)

    return ReportableOfferTermsContext(
        reportable_terms=cleaned_generation_terms,
        requirement_terms_lookup=requirement_terms_lookup,
        top_level_terms=top_level_terms,
        signal_inventory=signal_inventory,
        generation_eligible_offer_terms=cleaned_generation_terms,
        matching_only_signals=matching_only_signals,
        manual_confirmation_items=manual_confirmation_items,
        suppressed_terms=suppressed_terms,
        role_alignment_signals=role_alignment_signals,
    )


def parse_offer_term_candidate(
    raw_value: str | None,
    *,
    source_kind: Literal["requirement", "job_keyword", "job_metadata"],
    job_posting: JobPosting,
    requirement: Requirement | None = None,
) -> OfferSignal:
    """Classify one raw offer-side term candidate and describe its downstream allowed uses."""

    cleaned_value = _normalize_term(raw_value)
    source = _normalize_source_kind(source_kind)
    linked_requirement_ids = (requirement.id,) if requirement is not None else ()

    if not cleaned_value:
        return OfferSignal(
            raw_label="",
            label="",
            normalized_label="",
            role="generic_wrapper_or_noise",
            allowed_uses=("debug_only",),
            source=source,
            linked_requirement_ids=linked_requirement_ids,
            suppression_reason="empty_signal",
        )

    label, normalized_label = _normalize_signal_label(cleaned_value)
    reportable_term = _extract_reportable_term(cleaned_value)
    manual_confirmation = _looks_like_manual_confirmation(cleaned_value, requirement)
    metadata = _looks_like_metadata(cleaned_value, job_posting)
    threshold = _looks_like_threshold(cleaned_value)
    modifier = _looks_like_modifier(cleaned_value)
    education_signal = _looks_like_education_signal(cleaned_value, requirement)

    if manual_confirmation:
        role: OfferSignalRole = "constraint"
    elif metadata:
        role = "job_meta"
    elif threshold or modifier:
        role = "constraint"
    elif education_signal:
        role = "education_field_or_signal"
    elif reportable_term is None:
        role = "generic_wrapper_or_noise"
    elif _looks_like_skill_or_tool(reportable_term, requirement):
        role = "skill_or_tool"
    else:
        role = "domain"

    suppression_reason = _build_suppression_reason(
        cleaned_value,
        role=role,
        reportable_term=reportable_term,
        modifier=modifier,
        manual_confirmation=manual_confirmation,
    )
    generation_candidate_label = (
        reportable_term
        if role in {"skill_or_tool", "domain", "constraint"}
        and suppression_reason is None
        and not manual_confirmation
        else None
    )

    return OfferSignal(
        raw_label=cleaned_value,
        label=label,
        normalized_label=normalized_label,
        role=role,
        allowed_uses=_build_allowed_uses(
            role,
            normalized_label=normalized_label,
            manual_confirmation=manual_confirmation,
            suppression_reason=suppression_reason,
        ),
        source=source,
        linked_requirement_ids=linked_requirement_ids,
        suppression_reason=suppression_reason,
        generation_candidate_label=generation_candidate_label,
    )


def _build_top_level_signals(job_posting: JobPosting) -> list[OfferSignal]:
    return [
        parse_offer_term_candidate(
            raw_keyword,
            source_kind="job_keyword",
            job_posting=job_posting,
        )
        for raw_keyword in job_posting.keywords
    ]


def _build_metadata_signals(job_posting: JobPosting) -> list[OfferSignal]:
    metadata_values = [
        job_posting.location,
        job_posting.work_mode,
        job_posting.employment_type,
        job_posting.seniority_level,
    ]

    return [
        parse_offer_term_candidate(
            value,
            source_kind="job_metadata",
            job_posting=job_posting,
        )
        for value in metadata_values
        if _normalize_term(value)
    ]


def _build_requirement_signal_lookup(
    job_posting: JobPosting,
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
) -> dict[str, list[OfferSignal]]:
    requirement_signals_lookup: dict[str, list[OfferSignal]] = {}

    for requirement in _get_ordered_requirements(job_posting, priority_lookup):
        requirement_signals_lookup[requirement.id] = [
            parse_offer_term_candidate(
                raw_keyword,
                source_kind="requirement",
                requirement=requirement,
                job_posting=job_posting,
            )
            for raw_keyword in requirement.extracted_keywords
        ]

    return requirement_signals_lookup


def _build_top_level_reportable_terms(
    top_level_signals: list[OfferSignal],
    blocked_terms: set[str],
) -> list[str]:
    """Treat parser-derived top-level keywords as the primary source of final offer terms."""

    top_level_terms: list[str] = []

    for signal in top_level_signals:
        if "generation_allowed" not in signal.allowed_uses:
            continue
        if signal.generation_candidate_label is None:
            continue
        if _ascii_key(signal.generation_candidate_label) in blocked_terms:
            continue
        _append_unique(top_level_terms, signal.generation_candidate_label)

    return build_display_keywords(top_level_terms)


def _build_requirement_reportable_terms_lookup(
    job_posting: JobPosting,
    priority_lookup: dict[str, OpenAIRequirementPriorityItem],
    top_level_terms: list[str],
    requirement_signals_lookup: dict[str, list[OfferSignal]],
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

        for signal in requirement_signals_lookup.get(requirement.id, []):
            if signal.generation_candidate_label is None:
                continue

            normalized_term = _ascii_key(signal.generation_candidate_label)
            canonical_top_level_term = top_level_term_lookup.get(normalized_term)
            if canonical_top_level_term is not None:
                _append_unique(preferred_terms, canonical_top_level_term)
                continue

            if _should_allow_requirement_only_term(signal.generation_candidate_label, requirement):
                _append_unique(supplemental_terms, signal.generation_candidate_label)

        if not preferred_terms:
            for fallback_term in _collect_requirement_text_fallback_terms(requirement, top_level_terms):
                _append_unique(preferred_terms, fallback_term)

        terms_lookup[requirement.id] = build_display_keywords(
            [*preferred_terms, *supplemental_terms]
        )

    return terms_lookup


def _build_blocked_reportable_terms(
    job_posting: JobPosting,
    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem] | None,
    requirement_signals_lookup: dict[str, list[OfferSignal]],
) -> set[str]:
    """Collect generation-looking terms that should stay excluded because their requirement is skipped."""

    priority_lookup = requirement_priority_lookup or {}
    blocked_terms: set[str] = set()

    for requirement in _get_ordered_requirements(job_posting, priority_lookup):
        if not _should_skip_requirement_for_reportable_terms(requirement, priority_lookup):
            continue

        for signal in requirement_signals_lookup.get(requirement.id, []):
            if signal.generation_candidate_label:
                blocked_terms.add(_ascii_key(signal.generation_candidate_label))

    return blocked_terms


def _build_signal_inventory(
    *,
    top_level_signals: list[OfferSignal],
    metadata_signals: list[OfferSignal],
    requirement_signals_lookup: dict[str, list[OfferSignal]],
    generation_eligible_offer_terms: list[str],
    requirement_terms_lookup: dict[str, list[str]],
) -> list[OfferSignal]:
    """Merge discovered offer-side signals into one canonical debug-friendly inventory."""

    generation_lookup = {_ascii_key(term): term for term in generation_eligible_offer_terms}
    linked_generation_terms_lookup: dict[str, tuple[str, ...]] = {}

    for requirement_id, terms in requirement_terms_lookup.items():
        for term in terms:
            key = _ascii_key(term)
            existing_links = list(linked_generation_terms_lookup.get(key, ()))
            if requirement_id not in existing_links:
                existing_links.append(requirement_id)
            linked_generation_terms_lookup[key] = tuple(existing_links)

    aggregated: dict[tuple[str, str, str, str | None], OfferSignal] = {}

    def register(signal: OfferSignal) -> None:
        if not signal.raw_label:
            return

        resolved_generation_label = signal.generation_candidate_label
        linked_requirement_ids = signal.linked_requirement_ids

        generation_key = _ascii_key(signal.generation_candidate_label)
        canonical_generation_label = generation_lookup.get(generation_key)
        if canonical_generation_label:
            resolved_generation_label = canonical_generation_label
            linked_requirement_ids = tuple(
                dict.fromkeys(
                    [*linked_requirement_ids, *linked_generation_terms_lookup.get(generation_key, ())]
                )
            )
        elif signal.label and signal.normalized_label in linked_generation_terms_lookup:
            linked_requirement_ids = tuple(
                dict.fromkeys(
                    [*linked_requirement_ids, *linked_generation_terms_lookup.get(signal.normalized_label, ())]
                )
            )

        key = (
            signal.normalized_label or _ascii_key(signal.raw_label),
            signal.role,
            signal.source,
            signal.suppression_reason,
        )
        existing_signal = aggregated.get(key)
        if existing_signal is None:
            aggregated[key] = OfferSignal(
                raw_label=signal.raw_label,
                label=signal.label,
                normalized_label=signal.normalized_label,
                role=signal.role,
                allowed_uses=signal.allowed_uses,
                source=signal.source,
                linked_requirement_ids=linked_requirement_ids,
                suppression_reason=signal.suppression_reason,
                generation_candidate_label=resolved_generation_label,
            )
            return

        merged_links = list(existing_signal.linked_requirement_ids)
        for requirement_id in linked_requirement_ids:
            if requirement_id not in merged_links:
                merged_links.append(requirement_id)
        aggregated[key] = OfferSignal(
            raw_label=existing_signal.raw_label,
            label=existing_signal.label,
            normalized_label=existing_signal.normalized_label,
            role=existing_signal.role,
            allowed_uses=existing_signal.allowed_uses,
            source=existing_signal.source,
            linked_requirement_ids=tuple(merged_links),
            suppression_reason=existing_signal.suppression_reason,
            generation_candidate_label=existing_signal.generation_candidate_label or resolved_generation_label,
        )

    for signal in top_level_signals:
        register(signal)
    for signal in metadata_signals:
        register(signal)
    for signals in requirement_signals_lookup.values():
        for signal in signals:
            register(signal)

    return list(aggregated.values())


def _normalize_source_kind(
    source_kind: Literal["requirement", "job_keyword", "job_metadata"],
) -> OfferSignalSource:
    if source_kind == "requirement":
        return "requirement_keyword"
    return source_kind


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


def _normalize_signal_label(value: str) -> tuple[str, str]:
    normalized = _ascii_key(value)

    internship_normalized = _normalize_internship_signal(normalized)
    if internship_normalized is not None:
        return internship_normalized

    if normalized in _WORK_MODE_NORMALIZATION:
        return _WORK_MODE_NORMALIZATION[normalized]

    if normalized in _EMPLOYMENT_TYPE_NORMALIZATION:
        return _EMPLOYMENT_TYPE_NORMALIZATION[normalized]

    tokens = _tokenize(value)
    if not tokens:
        return "", ""

    label = _canonicalize_phrase(tokens)
    return label, _ascii_key(label)


def _normalize_internship_signal(normalized_value: str) -> tuple[str, str] | None:
    if normalized_value in _INTERNSHIP_NORMALIZATION:
        return _INTERNSHIP_NORMALIZATION[normalized_value]
    if "program stazowy" in normalized_value:
        return _INTERNSHIP_NORMALIZATION["program stazowy"]
    if normalized_value.startswith("intern ") or normalized_value.endswith(" internship"):
        return _INTERNSHIP_NORMALIZATION["internship"]
    return None


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
    if _normalize_internship_signal(normalized) is not None:
        return True

    metadata_values = {
        *[_ascii_key(job_posting.location)],
        *[_ascii_key(job_posting.work_mode)],
        *[_ascii_key(job_posting.employment_type)],
        *[_ascii_key(job_posting.seniority_level)],
        *_WORK_MODE_TERMS,
        *_EMPLOYMENT_TYPE_TERMS,
    }
    location_tokens = {_ascii_key(token) for token in _tokenize(job_posting.location or "") if token}
    seniority_tokens = {_ascii_key(token) for token in _tokenize(job_posting.seniority_level or "") if token}
    return (
        normalized in metadata_values
        or normalized in location_tokens
        or normalized in seniority_tokens
    )


def _looks_like_education_signal(value: str, requirement: Requirement | None = None) -> bool:
    normalized = _ascii_key(value)
    normalized_tokens = {_ascii_key(token) for token in _tokenize(value)}
    normalized_category = _ascii_key(requirement.category) if requirement is not None else ""

    if normalized_category == "education":
        return True

    if any(token in _EDUCATION_SIGNAL_TOKENS for token in normalized_tokens):
        return True

    if "kierunki techniczne" in normalized or "technical field" in normalized:
        return True

    return False


def _looks_like_skill_or_tool(term: str, requirement: Requirement | None = None) -> bool:
    normalized_term = _ascii_key(term)
    normalized_category = _ascii_key(requirement.category) if requirement is not None else ""
    tokens = _tokenize(term)

    if normalized_category in {"technology", "programming_language", "automation_tool"}:
        return True
    if normalized_category == "language" and len(tokens) == 1:
        return True
    if any(symbol in term for symbol in "+/#.-"):
        return True
    if any(character.isupper() for character in term):
        return True
    if len(tokens) == 1 and normalized_term in _SHORT_TERM_CANONICAL_MAP:
        return True
    return False


def _build_allowed_uses(
    role: OfferSignalRole,
    *,
    normalized_label: str,
    manual_confirmation: bool,
    suppression_reason: str | None,
) -> tuple[OfferSignalAllowedUse, ...]:
    if suppression_reason is not None:
        return ("debug_only",)

    if role in {"skill_or_tool", "domain"}:
        return ("generation_allowed", "matching_only")
    if role == "education_field_or_signal":
        return ("matching_only", "ranking_only")
    if role == "job_meta":
        if normalized_label == "internship":
            return ("matching_only", "ranking_only")
        return ("matching_only",)
    if role == "constraint":
        if manual_confirmation:
            return ("warning_or_manual_confirmation",)
        return ("matching_only",)
    return ("debug_only",)


def _build_suppression_reason(
    value: str,
    *,
    role: OfferSignalRole,
    reportable_term: str | None,
    modifier: bool,
    manual_confirmation: bool,
) -> str | None:
    if manual_confirmation:
        return None
    if role == "constraint":
        return None
    if role in {"skill_or_tool", "domain"} and reportable_term:
        return None
    if role == "education_field_or_signal":
        return None
    if role == "job_meta":
        return None
    if modifier:
        return "modifier_without_generation_value"
    return "generic_or_noise"


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
    if candidate_key in _GENERIC_MULTIWORD_MARKERS:
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
    """Recover generation-facing terms from requirement text only through already-clean offer terms."""

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


def _is_role_alignment_signal(signal: OfferSignal) -> bool:
    return signal.role == "job_meta" and signal.normalized_label == "internship"


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
