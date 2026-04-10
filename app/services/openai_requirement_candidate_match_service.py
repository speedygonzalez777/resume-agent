"""OpenAI-backed grounded semantic matching for small blocks of job requirements."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from app.models.analysis import MatchAnalysisRequest
from app.models.job import Requirement
from app.models.match import RequirementMatch
from app.prompts.requirement_candidate_match_prompt import (
    REQUIREMENT_CANDIDATE_MATCH_INSTRUCTIONS,
)
from app.services.openai_candidate_profile_understanding_service import (
    CandidateProfileUnderstanding,
)
from app.services.openai_model_resolver import resolve_matching_model
from app.services.openai_requirement_priority_service import OpenAIRequirementPriorityItem

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
_HARD_EVIDENCE_SOURCE_TYPES = {
    "experience",
    "project",
    "education",
    "certificate",
    "language",
    "skill",
}
_DECLARED_SOURCE_TYPES = {"soft_skill", "interest"}


class RequirementCandidateMatchOpenAIError(Exception):
    """Raised when semantic requirement matching cannot return a safe structured result."""

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


class RequirementCandidateEvidenceRef(BaseModel):
    """One grounded evidence reference used by the semantic matcher."""

    source_type: Literal[
        "experience",
        "project",
        "education",
        "certificate",
        "language",
        "skill",
        "soft_skill",
        "interest",
    ] = Field(..., description="Source type taken from the supplied candidate source catalog.")
    source_id: str = Field(..., description="Source ID taken from the supplied candidate source catalog.")
    supporting_snippet: str = Field(
        ...,
        description="Short snippet copied from the supplied source excerpt.",
    )


class OpenAIRequirementCandidateMatchRawItem(BaseModel):
    """Raw structured AI output for one requirement decision."""

    requirement_id: str = Field(..., description="Target requirement ID from the supplied target block.")
    suggested_status: Literal["matched", "partial", "missing", "not_verifiable"] = Field(
        ...,
        description="Suggested semantic match status for the target requirement.",
    )
    grounding_strength: Literal["strong", "moderate", "weak"] = Field(
        ...,
        description="How strongly the decision is grounded in the supplied evidence.",
    )
    reasoning_note: str = Field(
        ...,
        description="One short grounded explanation for the decision.",
    )
    evidence_refs: list[RequirementCandidateEvidenceRef] = Field(
        default_factory=list,
        description="Grounded evidence refs taken only from the supplied source catalog.",
    )
    supporting_signal_labels: list[str] = Field(
        default_factory=list,
        description="Concrete meaningful signal labels that support the decision.",
    )
    missing_elements: list[str] = Field(
        default_factory=list,
        description="Concrete missing elements that keep the requirement from a fuller match.",
    )


class OpenAIRequirementCandidateMatchRawOutput(BaseModel):
    """Raw block output returned by OpenAI before deterministic validation."""

    items: list[OpenAIRequirementCandidateMatchRawItem] = Field(
        default_factory=list,
        description="One semantic decision for each supplied target requirement.",
    )


class RequirementCandidateMatchItem(BaseModel):
    """Validated semantic decision consumed by the matcher merge layer."""

    requirement_id: str
    suggested_status: Literal["matched", "partial", "missing", "not_verifiable"]
    grounding_strength: Literal["strong", "moderate", "weak"]
    evidence_basis: Literal["hard_evidence", "mixed", "declared_only", "thematic_only", "none"]
    reasoning_note: str
    evidence_refs: list[RequirementCandidateEvidenceRef] = Field(default_factory=list)
    supporting_signal_labels: list[str] = Field(default_factory=list)
    missing_elements: list[str] = Field(default_factory=list)


class RequirementCandidateMatchOutput(BaseModel):
    """Validated block output used by the matcher merge layer."""

    items: list[RequirementCandidateMatchItem] = Field(default_factory=list)


def evaluate_requirement_candidate_block_with_openai(
    payload: MatchAnalysisRequest,
    *,
    target_requirements: list[Requirement],
    requirement_groups: dict[str, str],
    deterministic_match_lookup: dict[str, RequirementMatch],
    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem],
    candidate_profile_understanding: CandidateProfileUnderstanding,
) -> RequirementCandidateMatchOutput:
    """Evaluate one small requirement block against the full candidate context."""

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "tu_wkleisz_swoj_klucz":
        raise RequirementCandidateMatchOpenAIError(
            "OpenAI API key is missing. Skipping semantic requirement-to-candidate matching.",
            reason="missing_api_key",
        )

    if not target_requirements:
        return RequirementCandidateMatchOutput()

    model_name = resolve_matching_model(
        legacy_env_name="OPENAI_REQUIREMENT_CANDIDATE_MATCH_MODEL",
    )
    client = OpenAI(api_key=api_key)
    candidate_source_catalog, candidate_source_lookup = build_candidate_match_source_catalog(
        payload.candidate_profile,
    )

    try:
        response = client.responses.parse(
            **_build_responses_parse_kwargs(
                payload,
                target_requirements=target_requirements,
                requirement_groups=requirement_groups,
                deterministic_match_lookup=deterministic_match_lookup,
                requirement_priority_lookup=requirement_priority_lookup,
                candidate_profile_understanding=candidate_profile_understanding,
                candidate_source_catalog=candidate_source_catalog,
                model_name=model_name,
            )
        )
    except OpenAIError as exc:
        raise RequirementCandidateMatchOpenAIError(
            "OpenAI semantic requirement matching failed. Falling back to deterministic matching.",
            reason="openai_error",
            details={"model": model_name, "reason": str(exc)},
        ) from exc
    except Exception as exc:
        raise RequirementCandidateMatchOpenAIError(
            "Unexpected OpenAI semantic requirement matching failure. Falling back to deterministic matching.",
            reason="openai_error",
            details={"model": model_name, "reason": str(exc)},
        ) from exc

    raw_output = response.output_parsed
    if raw_output is None:
        raise RequirementCandidateMatchOpenAIError(
            "OpenAI returned no structured semantic match output. Falling back to deterministic matching.",
            reason="invalid_ai_output",
            details={"model": model_name},
        )

    return _build_requirement_candidate_match_output(
        raw_output,
        target_requirements=target_requirements,
        candidate_source_lookup=candidate_source_lookup,
        candidate_profile_understanding=candidate_profile_understanding,
    )


def build_candidate_match_source_catalog(candidate_profile) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, str]]]:
    """Build the source catalog used both for AI grounding and match-service evidence texts."""

    catalog: list[dict[str, Any]] = []
    lookup: dict[tuple[str, str], dict[str, str]] = {}

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

    return catalog, lookup


def _build_source_excerpt(*parts: str | None) -> str:
    return " | ".join(part.strip() for part in parts if part and part.strip())


def _build_responses_parse_kwargs(
    payload: MatchAnalysisRequest,
    *,
    target_requirements: list[Requirement],
    requirement_groups: dict[str, str],
    deterministic_match_lookup: dict[str, RequirementMatch],
    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem],
    candidate_profile_understanding: CandidateProfileUnderstanding,
    candidate_source_catalog: list[dict[str, Any]],
    model_name: str,
) -> dict[str, Any]:
    request_kwargs: dict[str, Any] = {
        "model": model_name,
        "instructions": REQUIREMENT_CANDIDATE_MATCH_INSTRUCTIONS,
        "input": _build_requirement_candidate_match_input(
            payload,
            target_requirements=target_requirements,
            requirement_groups=requirement_groups,
            deterministic_match_lookup=deterministic_match_lookup,
            requirement_priority_lookup=requirement_priority_lookup,
            candidate_profile_understanding=candidate_profile_understanding,
            candidate_source_catalog=candidate_source_catalog,
        ),
        "text_format": OpenAIRequirementCandidateMatchRawOutput,
    }
    request_kwargs.update(_build_optional_parse_kwargs(model_name))
    return request_kwargs


def _build_requirement_candidate_match_input(
    payload: MatchAnalysisRequest,
    *,
    target_requirements: list[Requirement],
    requirement_groups: dict[str, str],
    deterministic_match_lookup: dict[str, RequirementMatch],
    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem],
    candidate_profile_understanding: CandidateProfileUnderstanding,
    candidate_source_catalog: list[dict[str, Any]],
) -> str:
    evidence_pack = {
        "job_context": {
            "title": payload.job_posting.title,
            "company_name": payload.job_posting.company_name,
            "seniority_level": payload.job_posting.seniority_level,
            "employment_type": payload.job_posting.employment_type,
            "work_mode": payload.job_posting.work_mode,
            "role_summary": payload.job_posting.role_summary,
            "responsibilities": payload.job_posting.responsibilities,
        },
        "all_requirements_context": [
            {
                "id": requirement.id,
                "text": requirement.text,
                "category": requirement.category,
                "normalized_group": requirement_groups.get(requirement.id),
                "requirement_type": requirement.requirement_type,
                "importance": requirement.importance,
                "priority_tier": (
                    requirement_priority_lookup[requirement.id].priority_tier
                    if requirement.id in requirement_priority_lookup
                    else None
                ),
                "priority_reasoning": (
                    requirement_priority_lookup[requirement.id].reasoning_note
                    if requirement.id in requirement_priority_lookup
                    else None
                ),
                "extracted_keywords": requirement.extracted_keywords,
            }
            for requirement in payload.job_posting.requirements
        ],
        "target_requirements": [
            {
                "id": requirement.id,
                "text": requirement.text,
                "category": requirement.category,
                "normalized_group": requirement_groups.get(requirement.id),
                "requirement_type": requirement.requirement_type,
                "importance": requirement.importance,
                "priority_tier": (
                    requirement_priority_lookup[requirement.id].priority_tier
                    if requirement.id in requirement_priority_lookup
                    else None
                ),
                "extracted_keywords": requirement.extracted_keywords,
                "deterministic_baseline": {
                    "status": deterministic_match_lookup[requirement.id].match_status,
                    "explanation": deterministic_match_lookup[requirement.id].explanation,
                    "missing_elements": deterministic_match_lookup[requirement.id].missing_elements,
                    "matched_skill_names": deterministic_match_lookup[requirement.id].matched_skill_names,
                    "matched_experience_ids": deterministic_match_lookup[requirement.id].matched_experience_ids,
                    "matched_project_ids": deterministic_match_lookup[requirement.id].matched_project_ids,
                },
            }
            for requirement in target_requirements
        ],
        "candidate_context": {
            "target_roles": payload.candidate_profile.target_roles,
            "professional_summary_base": payload.candidate_profile.professional_summary_base,
            "soft_skill_entries": payload.candidate_profile.soft_skill_entries,
            "interest_entries": payload.candidate_profile.interest_entries,
        },
        "candidate_profile_understanding": candidate_profile_understanding.model_dump(mode="json"),
        "candidate_source_catalog": candidate_source_catalog,
    }

    return (
        "Semantically evaluate only the supplied target requirement block against the grounded candidate evidence pack. "
        "Use the full context, but return requirement-level decisions only for the target block.\n\n"
        f"{json.dumps(evidence_pack, ensure_ascii=False, indent=2)}"
    )


def _build_requirement_candidate_match_output(
    raw_output: OpenAIRequirementCandidateMatchRawOutput,
    *,
    target_requirements: list[Requirement],
    candidate_source_lookup: dict[tuple[str, str], dict[str, str]],
    candidate_profile_understanding: CandidateProfileUnderstanding,
) -> RequirementCandidateMatchOutput:
    target_requirement_ids = [requirement.id for requirement in target_requirements]
    returned_ids = [item.requirement_id for item in raw_output.items]
    if sorted(returned_ids) != sorted(target_requirement_ids):
        raise RequirementCandidateMatchOpenAIError(
            "OpenAI returned invalid requirement coverage for semantic matching. Falling back to deterministic matching.",
            reason="invalid_ai_output",
            details={
                "expected_requirement_ids": target_requirement_ids,
                "returned_requirement_ids": returned_ids,
            },
        )

    label_origin_lookup = _build_signal_label_origin_lookup(candidate_profile_understanding)
    items = [
        _validate_and_build_requirement_candidate_match_item(
            raw_item,
            candidate_source_lookup=candidate_source_lookup,
            label_origin_lookup=label_origin_lookup,
        )
        for raw_item in raw_output.items
    ]

    return RequirementCandidateMatchOutput(
        items=sorted(
            items,
            key=lambda item: target_requirement_ids.index(item.requirement_id),
        )
    )


def _validate_and_build_requirement_candidate_match_item(
    raw_item: OpenAIRequirementCandidateMatchRawItem,
    *,
    candidate_source_lookup: dict[tuple[str, str], dict[str, str]],
    label_origin_lookup: dict[str, set[str]],
) -> RequirementCandidateMatchItem:
    evidence_refs = [
        _validate_evidence_ref(raw_ref, candidate_source_lookup)
        for raw_ref in raw_item.evidence_refs
    ]
    supporting_signal_labels = _clean_signal_labels(raw_item.supporting_signal_labels)
    evidence_basis = _determine_evidence_basis(evidence_refs, supporting_signal_labels, label_origin_lookup)

    if raw_item.suggested_status in {"matched", "partial"} and (
        not evidence_refs or evidence_basis == "none"
    ):
        raise RequirementCandidateMatchOpenAIError(
            "OpenAI semantic matcher returned a positive decision without grounded evidence refs. Falling back to deterministic matching.",
            reason="invalid_ai_output",
            details={"requirement_id": raw_item.requirement_id},
        )

    return RequirementCandidateMatchItem(
        requirement_id=raw_item.requirement_id,
        suggested_status=raw_item.suggested_status,
        grounding_strength=raw_item.grounding_strength,
        evidence_basis=evidence_basis,
        reasoning_note=raw_item.reasoning_note.strip(),
        evidence_refs=evidence_refs,
        supporting_signal_labels=supporting_signal_labels,
        missing_elements=_clean_missing_elements(raw_item.missing_elements),
    )


def _validate_evidence_ref(
    raw_ref: RequirementCandidateEvidenceRef,
    candidate_source_lookup: dict[tuple[str, str], dict[str, str]],
) -> RequirementCandidateEvidenceRef:
    source_meta = candidate_source_lookup.get((raw_ref.source_type, raw_ref.source_id))
    if source_meta is None:
        raise RequirementCandidateMatchOpenAIError(
            "OpenAI semantic matcher returned an unknown candidate evidence ref. Falling back to deterministic matching.",
            reason="invalid_ai_output",
            details={"source_type": raw_ref.source_type, "source_id": raw_ref.source_id},
        )

    if _normalize_grounding_text(raw_ref.supporting_snippet) not in _normalize_grounding_text(
        source_meta["source_excerpt"]
    ):
        raise RequirementCandidateMatchOpenAIError(
            "OpenAI semantic matcher returned an ungrounded supporting snippet. Falling back to deterministic matching.",
            reason="invalid_ai_output",
            details={
                "source_type": raw_ref.source_type,
                "source_id": raw_ref.source_id,
                "snippet": raw_ref.supporting_snippet,
            },
        )

    return RequirementCandidateEvidenceRef(
        source_type=raw_ref.source_type,
        source_id=raw_ref.source_id,
        supporting_snippet=raw_ref.supporting_snippet.strip(),
    )


def _normalize_grounding_text(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip().lower()


def _build_signal_label_origin_lookup(
    candidate_profile_understanding: CandidateProfileUnderstanding,
) -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = {}

    def register(label: str, origin: str) -> None:
        normalized_label = _normalize_label_key(label)
        if not normalized_label:
            return
        lookup.setdefault(normalized_label, set()).add(origin)

    for signal in candidate_profile_understanding.source_signals:
        register(
            signal.signal_label,
            "hard" if signal.evidence_class == "hard_evidence" else "declared",
        )
        for term in signal.normalized_terms:
            register(
                term,
                "hard" if signal.evidence_class == "hard_evidence" else "declared",
            )

    for signal in candidate_profile_understanding.profile_signals:
        register(
            signal.signal_label,
            "hard" if signal.evidence_class == "hard_evidence" else "declared",
        )
        for term in signal.normalized_terms:
            register(
                term,
                "hard" if signal.evidence_class == "hard_evidence" else "declared",
            )

    for normalization in candidate_profile_understanding.language_normalizations:
        register(normalization.language_name, "hard")
        register(normalization.source_level, "hard")
        if normalization.normalized_cefr:
            register(normalization.normalized_cefr.upper(), "hard")
        for descriptor in normalization.semantic_descriptors:
            register(descriptor, "hard")

    for alignment in candidate_profile_understanding.thematic_alignments:
        register(alignment.theme_label, "thematic")
        for term in alignment.normalized_terms:
            register(term, "thematic")

    return lookup


def _determine_evidence_basis(
    evidence_refs: list[RequirementCandidateEvidenceRef],
    supporting_signal_labels: list[str],
    label_origin_lookup: dict[str, set[str]],
) -> Literal["hard_evidence", "mixed", "declared_only", "thematic_only", "none"]:
    has_hard = any(ref.source_type in _HARD_EVIDENCE_SOURCE_TYPES for ref in evidence_refs)
    has_declared = any(ref.source_type in _DECLARED_SOURCE_TYPES for ref in evidence_refs)
    has_thematic = False

    for label in supporting_signal_labels:
        origins = label_origin_lookup.get(_normalize_label_key(label), set())
        has_hard = has_hard or "hard" in origins
        has_declared = has_declared or "declared" in origins
        has_thematic = has_thematic or "thematic" in origins

    if has_hard and has_declared:
        return "mixed"
    if has_hard:
        return "hard_evidence"
    if has_declared:
        return "declared_only"
    if has_thematic:
        return "thematic_only"
    return "none"


def _clean_signal_labels(values: list[str]) -> list[str]:
    cleaned_labels: list[str] = []
    seen: set[str] = set()

    for value in values:
        canonical_value = _canonicalize_term(value)
        normalized_key = _normalize_label_key(canonical_value)
        if not canonical_value or not _is_meaningful_signal_term(canonical_value):
            continue
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        cleaned_labels.append(canonical_value)

    return cleaned_labels


def _clean_missing_elements(values: list[str]) -> list[str]:
    cleaned_elements: list[str] = []
    seen: set[str] = set()

    for value in values:
        canonical_value = _WHITESPACE_RE.sub(" ", value).strip(" ,;:.").strip()
        normalized_key = canonical_value.lower()
        if not canonical_value or normalized_key in seen:
            continue
        seen.add(normalized_key)
        cleaned_elements.append(canonical_value)

    return cleaned_elements


def _canonicalize_term(value: str | None) -> str:
    if not value:
        return ""

    collapsed = _WHITESPACE_RE.sub(" ", value).strip(" ,;:.").strip()
    normalized_key = collapsed.lower()
    if normalized_key in _SHORT_TERM_CANONICAL_MAP:
        return _SHORT_TERM_CANONICAL_MAP[normalized_key]
    return collapsed


def _is_meaningful_signal_term(value: str | None) -> bool:
    if not value:
        return False

    normalized_value = value.strip().lower()
    if normalized_value in _GENERIC_SIGNAL_TERMS:
        return False

    is_single_alpha_token = normalized_value.isalpha() and " " not in normalized_value
    if is_single_alpha_token and len(normalized_value) < 4:
        return normalized_value in _SHORT_TERM_CANONICAL_MAP

    return True


def _normalize_label_key(value: str | None) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip().lower() if value else ""


def _build_optional_parse_kwargs(model_name: str) -> dict[str, Any]:
    optional_kwargs: dict[str, Any] = {}

    if _model_supports_sampling_params(model_name):
        temperature = _read_optional_float_env(
            "OPENAI_REQUIREMENT_CANDIDATE_MATCH_TEMPERATURE",
            min_value=0.0,
            max_value=2.0,
        )
        if temperature is not None:
            optional_kwargs["temperature"] = temperature

        top_p = _read_optional_float_env(
            "OPENAI_REQUIREMENT_CANDIDATE_MATCH_TOP_P",
            min_value=0.0,
            max_value=1.0,
        )
        if top_p is not None:
            optional_kwargs["top_p"] = top_p

    return optional_kwargs


def _model_supports_sampling_params(model_name: str) -> bool:
    normalized_model_name = model_name.strip().lower()
    return normalized_model_name.startswith(_SAMPLING_CAPABLE_MODEL_PREFIXES)


def _read_optional_float_env(
    env_name: str,
    *,
    min_value: float,
    max_value: float,
) -> float | None:
    raw_value = os.getenv(env_name)
    if raw_value is None or raw_value.strip() == "":
        return None

    try:
        parsed_value = float(raw_value)
    except ValueError as exc:
        raise RequirementCandidateMatchOpenAIError(
            f"Invalid value for {env_name}. Falling back to deterministic matching.",
            reason="openai_error",
            details={"env_name": env_name, "value": raw_value},
        ) from exc

    if parsed_value < min_value or parsed_value > max_value:
        raise RequirementCandidateMatchOpenAIError(
            f"Invalid value for {env_name}. Falling back to deterministic matching.",
            reason="openai_error",
            details={"env_name": env_name, "value": raw_value},
        )

    return parsed_value
