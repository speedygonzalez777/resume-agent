"""OpenAI-backed truthful-first understanding of candidate profile evidence."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from app.models.candidate import CandidateProfile
from app.prompts.candidate_profile_understanding_prompt import (
    CANDIDATE_PROFILE_UNDERSTANDING_INSTRUCTIONS,
)
from app.services.openai_model_resolver import resolve_matching_model

_SAMPLING_CAPABLE_MODEL_PREFIXES = (
    "gpt-4.1",
    "gpt-4o",
    "gpt-4.5",
    "gpt-3.5",
)
_WHITESPACE_RE = re.compile(r"\s+")
_GENERIC_SIGNAL_TERMS = {
    "dev",
    "developer",
    "deweloper",
    "doświadczenie",
    "doswiadczenie",
    "technology",
    "technologies",
    "framework",
    "frameworki",
    "frameworks",
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
    "system",
    "systems",
    "systemy",
    "znajomość",
    "znajomosc",
}
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
    "sql": "SQL",
    "ux": "UX",
    "ui": "UI",
}
_ALLOWED_LANGUAGE_DESCRIPTORS = {
    "fluent",
    "written",
    "spoken",
    "professional_written",
    "professional_spoken",
    "business_working",
    "conversational",
}
_ALLOWED_CEFR_LEVELS = {"a1", "a2", "b1", "b2", "c1", "c2"}
_CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


class CandidateProfileUnderstandingOpenAIError(Exception):
    """Raised when candidate-profile understanding cannot return a safe structured result."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.details = details or {}


class CandidateProfileSourceRef(BaseModel):
    """Validated source reference used in aggregated profile signals and alignments."""

    source_type: Literal[
        "experience",
        "project",
        "education",
        "certificate",
        "language",
        "skill",
        "soft_skill",
        "interest",
    ]
    source_id: str


class CandidateSourceSignal(BaseModel):
    """One grounded signal tied to a concrete profile source."""

    source_type: Literal[
        "experience",
        "project",
        "education",
        "certificate",
        "language",
        "skill",
        "soft_skill",
        "interest",
    ]
    source_id: str
    source_title: str
    signal_label: str
    signal_kind: Literal[
        "technical_competency",
        "domain_exposure",
        "education_signal",
        "language_signal",
        "soft_signal",
        "declared_interest",
    ]
    evidence_class: Literal["hard_evidence", "declared_signal"]
    normalized_terms: list[str] = Field(default_factory=list)
    supporting_snippets: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    reasoning_note: str


class CandidateProfileSignal(BaseModel):
    """Canonical, merged profile-level signal built from one or more grounded source signals."""

    signal_label: str
    signal_kind: Literal[
        "technical_competency",
        "domain_exposure",
        "education_signal",
        "language_signal",
        "soft_signal",
        "declared_interest",
    ]
    evidence_class: Literal["hard_evidence", "declared_signal"]
    normalized_terms: list[str] = Field(default_factory=list)
    source_refs: list[CandidateProfileSourceRef] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    reasoning_note: str


class CandidateLanguageNormalization(BaseModel):
    """Semantic normalization of one explicit language entry."""

    source_id: str
    language_name: str
    source_level: str
    normalized_cefr: Literal["a1", "a2", "b1", "b2", "c1", "c2"] | None = None
    semantic_descriptors: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    reasoning_note: str


class CandidateThematicAlignment(BaseModel):
    """Cross-source thematic coherence signal that does not create hard evidence on its own."""

    theme_label: str
    normalized_terms: list[str] = Field(default_factory=list)
    source_refs: list[CandidateProfileSourceRef] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    reasoning_note: str


class CandidateProfileUnderstanding(BaseModel):
    """Final validated candidate-understanding sidecar consumed by matching and resume generation."""

    source_signals: list[CandidateSourceSignal] = Field(default_factory=list)
    profile_signals: list[CandidateProfileSignal] = Field(default_factory=list)
    language_normalizations: list[CandidateLanguageNormalization] = Field(default_factory=list)
    thematic_alignments: list[CandidateThematicAlignment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OpenAICandidateSourceSignal(BaseModel):
    """Raw AI output for one grounded source signal."""

    source_type: Literal[
        "experience",
        "project",
        "education",
        "certificate",
        "language",
        "skill",
        "soft_skill",
        "interest",
    ]
    source_id: str
    signal_label: str
    signal_kind: Literal[
        "technical_competency",
        "domain_exposure",
        "education_signal",
        "language_signal",
        "soft_signal",
        "declared_interest",
    ]
    evidence_class: Literal["hard_evidence", "declared_signal"]
    normalized_terms: list[str] = Field(default_factory=list)
    supporting_snippets: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    reasoning_note: str


class OpenAICandidateThematicRef(BaseModel):
    """Raw AI reference used for thematic alignments."""

    source_type: Literal[
        "experience",
        "project",
        "education",
        "certificate",
        "language",
        "skill",
        "soft_skill",
        "interest",
    ]
    source_id: str
    supporting_snippet: str


class OpenAICandidateLanguageNormalization(BaseModel):
    """Raw AI output for one language normalization entry."""

    source_id: str
    normalized_cefr: Literal["a1", "a2", "b1", "b2", "c1", "c2"] | None = None
    semantic_descriptors: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    reasoning_note: str


class OpenAICandidateThematicAlignment(BaseModel):
    """Raw AI output for one thematic alignment entry."""

    theme_label: str
    normalized_terms: list[str] = Field(default_factory=list)
    source_refs: list[OpenAICandidateThematicRef] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    reasoning_note: str


class OpenAICandidateProfileUnderstandingRawOutput(BaseModel):
    """Raw structured output returned by OpenAI before deterministic post-processing."""

    source_signals: list[OpenAICandidateSourceSignal] = Field(default_factory=list)
    language_normalizations: list[OpenAICandidateLanguageNormalization] = Field(default_factory=list)
    thematic_alignments: list[OpenAICandidateThematicAlignment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def evaluate_candidate_profile_understanding_with_openai(
    candidate_profile: CandidateProfile,
) -> CandidateProfileUnderstanding:
    """Build a grounded semantic understanding of the full candidate profile with OpenAI."""

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "tu_wkleisz_swoj_klucz":
        raise CandidateProfileUnderstandingOpenAIError(
            "OpenAI API key is missing. Skipping candidate profile understanding.",
            reason="missing_api_key",
        )

    model_name = resolve_matching_model(
        legacy_env_name="OPENAI_CANDIDATE_PROFILE_UNDERSTANDING_MODEL",
    )
    client = OpenAI(api_key=api_key)
    source_catalog, source_lookup, language_ids = _build_source_catalog(candidate_profile)

    try:
        response = client.responses.parse(
            **_build_responses_parse_kwargs(
                candidate_profile,
                source_catalog,
                model_name,
            )
        )
    except OpenAIError as exc:
        raise CandidateProfileUnderstandingOpenAIError(
            "OpenAI candidate profile understanding failed. Skipping semantic profile layer.",
            reason="openai_error",
            details={"model": model_name, "reason": str(exc)},
        ) from exc
    except Exception as exc:
        raise CandidateProfileUnderstandingOpenAIError(
            "Unexpected OpenAI candidate profile understanding failure. Skipping semantic profile layer.",
            reason="openai_error",
            details={"model": model_name, "reason": str(exc)},
        ) from exc

    raw_output = response.output_parsed
    if raw_output is None:
        raise CandidateProfileUnderstandingOpenAIError(
            "OpenAI returned no structured candidate profile understanding output. Skipping semantic profile layer.",
            reason="invalid_ai_output",
            details={"model": model_name},
        )

    return _build_candidate_profile_understanding(
        raw_output,
        source_lookup,
        language_ids,
    )


def get_candidate_profile_understanding(
    candidate_profile: CandidateProfile,
) -> CandidateProfileUnderstanding:
    """Return a safe profile-understanding object or an empty layer when unavailable."""

    try:
        return evaluate_candidate_profile_understanding_with_openai(candidate_profile)
    except CandidateProfileUnderstandingOpenAIError:
        return CandidateProfileUnderstanding()


def _build_responses_parse_kwargs(
    candidate_profile: CandidateProfile,
    source_catalog: list[dict[str, Any]],
    model_name: str,
) -> dict[str, Any]:
    """Build the structured Responses API payload for profile understanding."""

    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "instructions": CANDIDATE_PROFILE_UNDERSTANDING_INSTRUCTIONS,
        "input": _build_candidate_profile_understanding_input(
            candidate_profile,
            source_catalog,
        ),
        "text_format": OpenAICandidateProfileUnderstandingRawOutput,
    }
    request_kwargs.update(_build_optional_parse_kwargs(model_name))
    return request_kwargs


def _build_candidate_profile_understanding_input(
    candidate_profile: CandidateProfile,
    source_catalog: list[dict[str, Any]],
) -> str:
    """Build a compact but traceable evidence pack for profile understanding."""

    evidence_pack = {
        "profile_context": {
            "target_roles": candidate_profile.target_roles,
            "professional_summary_base": candidate_profile.professional_summary_base,
            "immutable_rules": candidate_profile.immutable_rules.model_dump(mode="json"),
        },
        "source_catalog": source_catalog,
    }

    return (
        "Build a grounded semantic understanding of this candidate profile from the JSON evidence pack.\n\n"
        f"{json.dumps(evidence_pack, ensure_ascii=False, indent=2)}"
    )


def _build_source_catalog(
    candidate_profile: CandidateProfile,
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, str]], set[str]]:
    """Build all AI-addressable source options and their validation lookup."""

    catalog: list[dict[str, Any]] = []
    lookup: dict[tuple[str, str], dict[str, str]] = {}
    language_ids: set[str] = set()

    def register(
        *,
        source_type: str,
        source_id: str,
        source_title: str,
        source_excerpt: str,
        payload: dict[str, Any],
    ) -> None:
        catalog.append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "source_title": source_title,
                "source_excerpt": source_excerpt,
                **payload,
            }
        )
        lookup[(source_type, source_id)] = {
            "source_title": source_title,
            "source_excerpt": source_excerpt,
        }
        if source_type == "language":
            language_ids.add(source_id)

    for experience in candidate_profile.experience_entries:
        excerpt = _build_source_excerpt(
            experience.position_title,
            experience.company_name,
            *experience.technologies_used,
            *experience.keywords,
            *experience.responsibilities,
            *experience.achievements,
        )
        register(
            source_type="experience",
            source_id=experience.id,
            source_title=f"{experience.position_title} at {experience.company_name}",
            source_excerpt=excerpt,
            payload={
                "position_title": experience.position_title,
                "company_name": experience.company_name,
                "technologies_used": experience.technologies_used,
                "keywords": experience.keywords,
                "responsibilities": experience.responsibilities,
                "achievements": experience.achievements,
            },
        )

    for project in candidate_profile.project_entries:
        excerpt = _build_source_excerpt(
            project.project_name,
            project.role,
            project.description,
            *project.technologies_used,
            *project.keywords,
            *project.outcomes,
        )
        register(
            source_type="project",
            source_id=project.id,
            source_title=project.project_name,
            source_excerpt=excerpt,
            payload={
                "project_name": project.project_name,
                "role": project.role,
                "description": project.description,
                "technologies_used": project.technologies_used,
                "keywords": project.keywords,
                "outcomes": project.outcomes,
            },
        )

    for index, education in enumerate(candidate_profile.education_entries, start=1):
        source_id = f"education_{index:03d}"
        excerpt = _build_source_excerpt(
            education.degree,
            education.field_of_study,
            education.institution_name,
        )
        register(
            source_type="education",
            source_id=source_id,
            source_title=f"{education.degree} in {education.field_of_study}",
            source_excerpt=excerpt,
            payload={
                "degree": education.degree,
                "field_of_study": education.field_of_study,
                "institution_name": education.institution_name,
                "is_current": education.is_current,
            },
        )

    for index, certificate in enumerate(candidate_profile.certificate_entries, start=1):
        source_id = f"certificate_{index:03d}"
        excerpt = _build_source_excerpt(
            certificate.certificate_name,
            certificate.issuer,
            certificate.notes,
        )
        register(
            source_type="certificate",
            source_id=source_id,
            source_title=certificate.certificate_name,
            source_excerpt=excerpt,
            payload={
                "certificate_name": certificate.certificate_name,
                "issuer": certificate.issuer,
                "notes": certificate.notes,
            },
        )

    for index, language in enumerate(candidate_profile.language_entries, start=1):
        source_id = f"language_{index:03d}"
        excerpt = _build_source_excerpt(
            language.language_name,
            language.proficiency_level,
        )
        register(
            source_type="language",
            source_id=source_id,
            source_title=language.language_name,
            source_excerpt=excerpt,
            payload={
                "language_name": language.language_name,
                "proficiency_level": language.proficiency_level,
            },
        )

    for index, skill in enumerate(candidate_profile.skill_entries, start=1):
        source_id = f"skill_{index:03d}"
        excerpt = _build_source_excerpt(
            skill.name,
            skill.level,
            *skill.aliases,
        )
        register(
            source_type="skill",
            source_id=source_id,
            source_title=skill.name,
            source_excerpt=excerpt,
            payload={
                "name": skill.name,
                "level": skill.level,
                "aliases": skill.aliases,
                "years_of_experience": skill.years_of_experience,
            },
        )

    for index, soft_skill in enumerate(candidate_profile.soft_skill_entries, start=1):
        source_id = f"soft_skill_{index:03d}"
        register(
            source_type="soft_skill",
            source_id=source_id,
            source_title=soft_skill,
            source_excerpt=_build_source_excerpt(soft_skill),
            payload={"value": soft_skill},
        )

    for index, interest in enumerate(candidate_profile.interest_entries, start=1):
        source_id = f"interest_{index:03d}"
        register(
            source_type="interest",
            source_id=source_id,
            source_title=interest,
            source_excerpt=_build_source_excerpt(interest),
            payload={"value": interest},
        )

    return catalog, lookup, language_ids


def _build_source_excerpt(*parts: str | None) -> str:
    """Build a normalized source excerpt that grounding snippets must point back to."""

    return " | ".join(part.strip() for part in parts if part and part.strip())


def _build_candidate_profile_understanding(
    raw_output: OpenAICandidateProfileUnderstandingRawOutput,
    source_lookup: dict[tuple[str, str], dict[str, str]],
    language_ids: set[str],
) -> CandidateProfileUnderstanding:
    """Validate, clean and post-process raw AI output into the final internal sidecar."""

    source_signals: list[CandidateSourceSignal] = []
    dropped_source_signal_count = 0

    for raw_signal in raw_output.source_signals:
        validated_signal = _validate_and_build_source_signal(raw_signal, source_lookup)
        if validated_signal is None:
            dropped_source_signal_count += 1
            continue
        source_signals.append(validated_signal)

    language_normalizations = [
        _validate_and_build_language_normalization(raw_item, source_lookup, language_ids)
        for raw_item in raw_output.language_normalizations
    ]
    _validate_language_coverage(language_normalizations, language_ids)

    thematic_alignments: list[CandidateThematicAlignment] = []
    dropped_alignment_count = 0
    for raw_alignment in raw_output.thematic_alignments:
        validated_alignment = _validate_and_build_thematic_alignment(raw_alignment, source_lookup)
        if validated_alignment is None:
            dropped_alignment_count += 1
            continue
        thematic_alignments.append(validated_alignment)

    warnings = [warning.strip() for warning in raw_output.warnings if warning and warning.strip()]
    if dropped_source_signal_count:
        warnings.append(
            "Some low-quality or overly generic candidate source signals were dropped during post-processing."
        )
    if dropped_alignment_count:
        warnings.append(
            "Some low-quality thematic alignments were dropped during post-processing."
        )

    return CandidateProfileUnderstanding(
        source_signals=source_signals,
        profile_signals=_build_profile_signals(source_signals),
        language_normalizations=language_normalizations,
        thematic_alignments=thematic_alignments,
        warnings=warnings,
    )


def _validate_and_build_source_signal(
    raw_signal: OpenAICandidateSourceSignal,
    source_lookup: dict[tuple[str, str], dict[str, str]],
) -> CandidateSourceSignal | None:
    """Validate one raw source signal and return a cleaned signal or None when it becomes too generic."""

    source_meta = _resolve_source_meta(source_lookup, raw_signal.source_type, raw_signal.source_id)
    _validate_signal_evidence_class(raw_signal)
    _validate_supporting_snippets(
        raw_signal.supporting_snippets,
        source_meta["source_excerpt"],
        source_type=raw_signal.source_type,
        source_id=raw_signal.source_id,
    )

    cleaned_terms = _clean_signal_terms(raw_signal.normalized_terms)
    cleaned_label = _clean_signal_label(raw_signal.signal_label, cleaned_terms)
    if not cleaned_label:
        return None
    if not cleaned_terms:
        cleaned_terms = [cleaned_label]

    return CandidateSourceSignal(
        source_type=raw_signal.source_type,
        source_id=raw_signal.source_id,
        source_title=source_meta["source_title"],
        signal_label=cleaned_label,
        signal_kind=raw_signal.signal_kind,
        evidence_class=raw_signal.evidence_class,
        normalized_terms=cleaned_terms,
        supporting_snippets=[snippet.strip() for snippet in raw_signal.supporting_snippets if snippet.strip()],
        confidence=raw_signal.confidence,
        reasoning_note=raw_signal.reasoning_note.strip(),
    )


def _validate_and_build_language_normalization(
    raw_item: OpenAICandidateLanguageNormalization,
    source_lookup: dict[tuple[str, str], dict[str, str]],
    language_ids: set[str],
) -> CandidateLanguageNormalization:
    """Validate one raw language normalization and enrich it with source metadata."""

    if raw_item.source_id not in language_ids:
        raise CandidateProfileUnderstandingOpenAIError(
            "OpenAI returned an unknown language source ID. Skipping semantic profile layer.",
            reason="invalid_ai_output",
            details={"source_id": raw_item.source_id},
        )

    source_meta = _resolve_source_meta(source_lookup, "language", raw_item.source_id)
    excerpt_parts = [part.strip() for part in source_meta["source_excerpt"].split("|") if part.strip()]
    language_name = excerpt_parts[0] if excerpt_parts else ""
    source_level = excerpt_parts[1] if len(excerpt_parts) >= 2 else ""

    descriptors = _clean_language_descriptors(raw_item.semantic_descriptors)
    normalized_cefr = raw_item.normalized_cefr
    if normalized_cefr is not None and normalized_cefr not in _ALLOWED_CEFR_LEVELS:
        raise CandidateProfileUnderstandingOpenAIError(
            "OpenAI returned an invalid CEFR level. Skipping semantic profile layer.",
            reason="invalid_ai_output",
            details={"source_id": raw_item.source_id, "normalized_cefr": normalized_cefr},
        )
    if not descriptors and normalized_cefr is not None:
        descriptors = _default_language_descriptors_from_cefr(normalized_cefr)

    return CandidateLanguageNormalization(
        source_id=raw_item.source_id,
        language_name=language_name,
        source_level=source_level,
        normalized_cefr=normalized_cefr,
        semantic_descriptors=descriptors,
        confidence=raw_item.confidence,
        reasoning_note=raw_item.reasoning_note.strip(),
    )


def _validate_language_coverage(
    language_normalizations: list[CandidateLanguageNormalization],
    language_ids: set[str],
) -> None:
    """Ensure the output covers every supplied language source exactly once."""

    returned_ids = [item.source_id for item in language_normalizations]
    if len(returned_ids) != len(language_ids):
        raise CandidateProfileUnderstandingOpenAIError(
            "OpenAI returned incomplete language normalization coverage. Skipping semantic profile layer.",
            reason="invalid_ai_output",
            details={"expected_language_ids": sorted(language_ids), "returned_ids": returned_ids},
        )

    duplicate_ids = [source_id for source_id in returned_ids if returned_ids.count(source_id) > 1]
    missing_ids = [source_id for source_id in language_ids if source_id not in returned_ids]
    if duplicate_ids or missing_ids:
        raise CandidateProfileUnderstandingOpenAIError(
            "OpenAI returned invalid language normalization coverage. Skipping semantic profile layer.",
            reason="invalid_ai_output",
            details={
                "duplicate_ids": sorted(set(duplicate_ids)),
                "missing_ids": sorted(set(missing_ids)),
            },
        )


def _validate_and_build_thematic_alignment(
    raw_alignment: OpenAICandidateThematicAlignment,
    source_lookup: dict[tuple[str, str], dict[str, str]],
) -> CandidateThematicAlignment | None:
    """Validate one raw thematic alignment entry."""

    cleaned_terms = _clean_signal_terms(raw_alignment.normalized_terms)
    cleaned_label = _clean_signal_label(raw_alignment.theme_label, cleaned_terms)
    if not cleaned_label:
        return None
    if not cleaned_terms:
        cleaned_terms = [cleaned_label]

    source_refs = [
        _validate_and_build_thematic_ref(raw_ref, source_lookup)
        for raw_ref in raw_alignment.source_refs
    ]
    unique_source_refs = list(dict.fromkeys((ref.source_type, ref.source_id) for ref in source_refs))
    if len(unique_source_refs) < 2:
        return None

    return CandidateThematicAlignment(
        theme_label=cleaned_label,
        normalized_terms=cleaned_terms,
        source_refs=[
            CandidateProfileSourceRef(source_type=source_type, source_id=source_id)
            for source_type, source_id in unique_source_refs
        ],
        confidence=raw_alignment.confidence,
        reasoning_note=raw_alignment.reasoning_note.strip(),
    )


def _validate_and_build_thematic_ref(
    raw_ref: OpenAICandidateThematicRef,
    source_lookup: dict[tuple[str, str], dict[str, str]],
) -> CandidateProfileSourceRef:
    """Validate one thematic reference against the allowed source catalog."""

    source_meta = _resolve_source_meta(source_lookup, raw_ref.source_type, raw_ref.source_id)
    _validate_supporting_snippets(
        [raw_ref.supporting_snippet],
        source_meta["source_excerpt"],
        source_type=raw_ref.source_type,
        source_id=raw_ref.source_id,
    )
    return CandidateProfileSourceRef(
        source_type=raw_ref.source_type,
        source_id=raw_ref.source_id,
    )


def _resolve_source_meta(
    source_lookup: dict[tuple[str, str], dict[str, str]],
    source_type: str,
    source_id: str,
) -> dict[str, str]:
    """Resolve source metadata or fail when the AI referenced an unknown source."""

    source_meta = source_lookup.get((source_type, source_id))
    if source_meta is None:
        raise CandidateProfileUnderstandingOpenAIError(
            "OpenAI returned an unknown candidate source reference. Skipping semantic profile layer.",
            reason="invalid_ai_output",
            details={"source_type": source_type, "source_id": source_id},
        )
    return source_meta


def _validate_signal_evidence_class(raw_signal: OpenAICandidateSourceSignal) -> None:
    """Enforce that declared sources stay declared and hard-evidence sources stay hard."""

    if raw_signal.source_type in {"soft_skill", "interest"} and raw_signal.evidence_class != "declared_signal":
        raise CandidateProfileUnderstandingOpenAIError(
            "OpenAI tried to turn a declared source into hard evidence. Skipping semantic profile layer.",
            reason="invalid_ai_output",
            details={"source_type": raw_signal.source_type, "source_id": raw_signal.source_id},
        )
    if raw_signal.source_type not in {"soft_skill", "interest"} and raw_signal.evidence_class != "hard_evidence":
        raise CandidateProfileUnderstandingOpenAIError(
            "OpenAI returned a non-declared evidence source with the wrong evidence class. Skipping semantic profile layer.",
            reason="invalid_ai_output",
            details={"source_type": raw_signal.source_type, "source_id": raw_signal.source_id},
        )


def _validate_supporting_snippets(
    snippets: list[str],
    source_excerpt: str,
    *,
    source_type: str,
    source_id: str,
) -> None:
    """Ensure all snippets are grounded inside the allowed source excerpt."""

    normalized_excerpt = _normalize_grounding_text(source_excerpt)
    if not normalized_excerpt:
        raise CandidateProfileUnderstandingOpenAIError(
            "Source excerpt was unexpectedly empty during profile-understanding validation.",
            reason="invalid_ai_output",
            details={"source_type": source_type, "source_id": source_id},
        )

    for snippet in snippets:
        normalized_snippet = _normalize_grounding_text(snippet)
        if not normalized_snippet or normalized_snippet not in normalized_excerpt:
            raise CandidateProfileUnderstandingOpenAIError(
                "OpenAI returned an ungrounded supporting snippet. Skipping semantic profile layer.",
                reason="invalid_ai_output",
                details={
                    "source_type": source_type,
                    "source_id": source_id,
                    "snippet": snippet,
                },
            )


def _normalize_grounding_text(value: str | None) -> str:
    """Normalize whitespace and case for snippet grounding checks."""

    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip().lower()


def _clean_signal_label(label: str, cleaned_terms: list[str]) -> str:
    """Return a meaningful canonical label or an empty string when the signal is too generic."""

    cleaned_label = _canonicalize_term(label)
    if _is_meaningful_signal_term(cleaned_label):
        return cleaned_label
    if cleaned_terms:
        return cleaned_terms[0]
    return ""


def _clean_signal_terms(values: list[str]) -> list[str]:
    """Normalize, deduplicate and filter candidate signal terms."""

    cleaned_terms: list[str] = []
    seen_terms: set[str] = set()

    for value in values:
        canonical_value = _canonicalize_term(value)
        normalized_key = canonical_value.lower()
        if not canonical_value or not _is_meaningful_signal_term(canonical_value):
            continue
        if normalized_key in seen_terms:
            continue
        seen_terms.add(normalized_key)
        cleaned_terms.append(canonical_value)

    return cleaned_terms


def _canonicalize_term(value: str | None) -> str:
    """Return a display-usable canonical term without allowing generic umbrella labels."""

    if not value:
        return ""

    collapsed = _WHITESPACE_RE.sub(" ", value).strip(" ,;:.").strip()
    normalized_key = collapsed.lower()
    if normalized_key in _SHORT_TERM_CANONICAL_MAP:
        return _SHORT_TERM_CANONICAL_MAP[normalized_key]
    return collapsed


def _is_meaningful_signal_term(value: str | None) -> bool:
    """Return whether a signal term is specific enough to survive post-processing."""

    if not value:
        return False

    normalized_value = value.strip().lower()
    if normalized_value in _GENERIC_SIGNAL_TERMS:
        return False

    is_single_alpha_token = normalized_value.isalpha() and " " not in normalized_value
    if is_single_alpha_token and len(normalized_value) < 4:
        return normalized_value in _SHORT_TERM_CANONICAL_MAP

    return True


def _clean_language_descriptors(values: list[str]) -> list[str]:
    """Keep only allowed, unique semantic language descriptors."""

    cleaned_descriptors: list[str] = []
    seen_descriptors: set[str] = set()

    for value in values:
        normalized_value = _canonicalize_language_descriptor(value)
        if not normalized_value or normalized_value not in _ALLOWED_LANGUAGE_DESCRIPTORS:
            continue
        if normalized_value in seen_descriptors:
            continue
        seen_descriptors.add(normalized_value)
        cleaned_descriptors.append(normalized_value)

    return cleaned_descriptors


def _canonicalize_language_descriptor(value: str | None) -> str:
    """Normalize language descriptors into the allowed canonical vocabulary."""

    if not value:
        return ""

    normalized_value = _WHITESPACE_RE.sub("_", value.strip().lower())
    descriptor_aliases = {
        "professional_written_communication": "professional_written",
        "professional_spoken_communication": "professional_spoken",
        "business_working_proficiency": "business_working",
    }
    return descriptor_aliases.get(normalized_value, normalized_value)


def _default_language_descriptors_from_cefr(normalized_cefr: str) -> list[str]:
    """Provide conservative default descriptors for normalized CEFR levels."""

    if normalized_cefr in {"c1", "c2"}:
        return ["fluent", "written", "spoken", "professional_written", "professional_spoken"]
    if normalized_cefr == "b2":
        return ["written", "spoken", "business_working"]
    if normalized_cefr == "b1":
        return ["spoken", "conversational"]
    return []


def _build_profile_signals(source_signals: list[CandidateSourceSignal]) -> list[CandidateProfileSignal]:
    """Aggregate source-level grounded signals into canonical profile-level signals."""

    aggregated: dict[tuple[str, str, str], dict[str, Any]] = {}

    for source_signal in source_signals:
        if not source_signal.normalized_terms:
            continue

        primary_term_key = source_signal.normalized_terms[0].lower()
        aggregation_key = (
            source_signal.signal_kind,
            source_signal.evidence_class,
            primary_term_key,
        )
        entry = aggregated.setdefault(
            aggregation_key,
            {
                "signal_label": source_signal.signal_label,
                "signal_kind": source_signal.signal_kind,
                "evidence_class": source_signal.evidence_class,
                "normalized_terms": [],
                "source_refs": [],
                "confidence_values": [],
            },
        )
        _extend_unique(entry["normalized_terms"], source_signal.normalized_terms)
        source_ref = CandidateProfileSourceRef(
            source_type=source_signal.source_type,
            source_id=source_signal.source_id,
        )
        if source_ref not in entry["source_refs"]:
            entry["source_refs"].append(source_ref)
        entry["confidence_values"].append(source_signal.confidence)

        if _is_better_signal_label(source_signal.signal_label, entry["signal_label"]):
            entry["signal_label"] = source_signal.signal_label

    profile_signals: list[CandidateProfileSignal] = []
    for aggregation_entry in aggregated.values():
        source_count = len(aggregation_entry["source_refs"])
        confidence = _select_highest_confidence(aggregation_entry["confidence_values"])
        profile_signals.append(
            CandidateProfileSignal(
                signal_label=aggregation_entry["signal_label"],
                signal_kind=aggregation_entry["signal_kind"],
                evidence_class=aggregation_entry["evidence_class"],
                normalized_terms=aggregation_entry["normalized_terms"],
                source_refs=aggregation_entry["source_refs"],
                confidence=confidence,
                reasoning_note=(
                    f"Canonical profile signal aggregated from {source_count} grounded source signal"
                    f"{'' if source_count == 1 else 's'}."
                ),
            )
        )

    return sorted(
        profile_signals,
        key=lambda signal: (
            signal.evidence_class != "hard_evidence",
            signal.signal_kind,
            signal.signal_label.lower(),
        ),
    )


def _extend_unique(target: list[str], values: list[str]) -> None:
    """Extend a list with unique items while preserving order."""

    for value in values:
        if value not in target:
            target.append(value)


def _is_better_signal_label(candidate_label: str, current_label: str) -> bool:
    """Prefer more specific labels when aggregating profile signals."""

    if not current_label:
        return True
    if len(candidate_label) > len(current_label):
        return True
    return False


def _select_highest_confidence(confidence_values: list[str]) -> Literal["high", "medium", "low"]:
    """Return the strongest confidence value present in a group."""

    if not confidence_values:
        return "low"
    return sorted(confidence_values, key=lambda value: _CONFIDENCE_ORDER.get(value, 2))[0]


def _build_optional_parse_kwargs(model_name: str) -> dict[str, Any]:
    """Add optional sampling params only for supported model families."""

    optional_kwargs: dict[str, Any] = {}

    if _model_supports_sampling_params(model_name):
        temperature = _read_optional_float_env(
            "OPENAI_CANDIDATE_PROFILE_UNDERSTANDING_TEMPERATURE",
            min_value=0.0,
            max_value=2.0,
        )
        if temperature is not None:
            optional_kwargs["temperature"] = temperature

        top_p = _read_optional_float_env(
            "OPENAI_CANDIDATE_PROFILE_UNDERSTANDING_TOP_P",
            min_value=0.0,
            max_value=1.0,
        )
        if top_p is not None:
            optional_kwargs["top_p"] = top_p

    return optional_kwargs


def _model_supports_sampling_params(model_name: str) -> bool:
    """Return whether the selected model family supports explicit sampling params."""

    normalized_model_name = model_name.strip().lower()
    return normalized_model_name.startswith(_SAMPLING_CAPABLE_MODEL_PREFIXES)


def _read_optional_float_env(
    env_name: str,
    *,
    min_value: float,
    max_value: float,
) -> float | None:
    """Read an optional float env var and validate its allowed range."""

    raw_value = os.getenv(env_name)
    if raw_value is None or raw_value.strip() == "":
        return None

    try:
        parsed_value = float(raw_value)
    except ValueError as exc:
        raise CandidateProfileUnderstandingOpenAIError(
            f"Invalid value for {env_name}. Skipping semantic profile layer.",
            reason="openai_error",
            details={"env_name": env_name, "value": raw_value},
        ) from exc

    if parsed_value < min_value or parsed_value > max_value:
        raise CandidateProfileUnderstandingOpenAIError(
            f"Invalid value for {env_name}. Skipping semantic profile layer.",
            reason="openai_error",
            details={"env_name": env_name, "value": raw_value},
        )

    return parsed_value
