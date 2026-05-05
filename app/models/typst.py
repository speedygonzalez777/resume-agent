"""Contracts for the Typst CV prepare/render flow."""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.resume import ResumeDraft

TYPST_LIMIT_CONFIG: dict[str, Any] = {
    "summary": {
        "max_items": 1,
        "target_chars": 370,
        "hard_chars": 390,
    },
    "education": {
        "exact_items": 2,
        "institution_target_chars": 55,
        "institution_hard_chars": 75,
        "degree_target_chars": 110,
        "degree_hard_chars": 120,
        "date_hard_chars": 25,
        "thesis_max_items": 1,
        "thesis_target_chars": 140,
        "thesis_hard_chars": 155,
    },
    "experience": {
        "exact_items": 2,
        "bullets_per_entry": 2,
        "header_left_target_chars": 50,
        "header_left_hard_chars": 65,
        "date_hard_chars": 25,
        "bullet_target_chars": 195,
        "bullet_hard_chars": 205,
    },
    "projects": {
        "exact_items": 2,
        "entry_total_target_chars": 230,
        "entry_total_hard_chars": 240,
    },
    "skills": {
        "exact_items": 3,
        "entry_target_chars": 145,
        "entry_hard_chars": 150,
    },
    "languages_certificates": {
        "max_items": 6,
        "entry_target_chars": 30,
        "entry_hard_chars": 35,
    },
    "header": {
        "full_name_hard_chars": 35,
        "email_hard_chars": 35,
        "phone_hard_chars": 25,
        "linkedin_hard_chars": 90,
        "github_hard_chars": 70,
    },
}


class TypstLanguage(str, Enum):
    """Supported Typst CV output languages."""

    EN = "en"
    PL = "pl"


class TypstConsentMode(str, Enum):
    """Supported consent rendering modes for the Typst CV."""

    DEFAULT = "default"
    CUSTOM = "custom"
    NONE = "none"


class TypstDraftVariant(str, Enum):
    """Stored resume-draft variant that can be used as the Typst source."""

    BASE = "base"
    REFINED = "refined"


class TypstRenderOptions(BaseModel):
    """User-selected options that affect the Typst CV output."""

    language: TypstLanguage
    include_photo: bool
    consent_mode: TypstConsentMode
    custom_consent_text: str | None = None
    photo_asset_id: str | None = None

    @model_validator(mode="after")
    def validate_custom_consent_text(self) -> "TypstRenderOptions":
        """Require explicit consent text only when the custom mode is selected."""

        if self.consent_mode is TypstConsentMode.CUSTOM:
            if not (self.custom_consent_text or "").strip():
                raise ValueError("custom_consent_text is required when consent_mode='custom'.")
        return self


class TypstProfilePayload(BaseModel):
    """Header payload consumed by the Typst template."""

    full_name: str
    email: str
    phone: str
    linkedin: str | None = None
    github: str | None = None


class TypstEducationEntry(BaseModel):
    """One structured education entry prepared for the Typst template."""

    institution: str
    degree: str
    date: str
    thesis: str | None = None


class TypstExperienceEntry(BaseModel):
    """One structured experience entry prepared for the Typst template."""

    company: str
    role: str
    date: str
    bullets: list[str] = Field(default_factory=list)


class TypstProjectEntry(BaseModel):
    """One structured project entry prepared for the Typst template."""

    name: str
    description: str


class TypstPayload(BaseModel):
    """Final payload expected by the Typst template renderer."""

    template_name: str = "cv_one_page"
    language: TypstLanguage
    include_photo: bool
    consent_mode: TypstConsentMode
    custom_consent_text: str | None = None
    photo_asset_id: str | None = None
    profile: TypstProfilePayload
    summary_text: str
    education_entries: list[TypstEducationEntry] = Field(default_factory=list)
    experience_entries: list[TypstExperienceEntry] = Field(default_factory=list)
    project_entries: list[TypstProjectEntry] = Field(default_factory=list)
    skill_entries: list[str] = Field(default_factory=list)
    language_certificate_entries: list[str] = Field(default_factory=list)


class TypstSourceEvidenceItem(BaseModel):
    """Compact source facts for one Typst payload entry used by fit-to-page."""

    entry_type: Literal["experience", "project", "summary"]
    payload_index: int | None = None
    source_id: str | None = None
    match_confidence: Literal["high", "medium", "low"] = "low"
    title: str | None = None
    organization: str | None = None
    role: str | None = None
    date: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source_highlights: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TypstConceptGrounding(BaseModel):
    """Relationship guidance for a term found in the source evidence pack."""

    term: str
    source_context: str | None = None
    term_type: str | None = None
    safe_usage: str | None = None
    unsafe_usage: str | None = None
    relationship_notes: str | None = None
    confidence: Literal["high", "medium", "low"] = "low"
    needs_external_verification: bool = False
    manual_review_reason: str | None = None


class TypstSourceEvidencePack(BaseModel):
    """Runtime-only source context for evidence-backed Typst fit-to-page patches."""

    experience_items: list[TypstSourceEvidenceItem] = Field(default_factory=list)
    project_items: list[TypstSourceEvidenceItem] = Field(default_factory=list)
    summary_context: TypstSourceEvidenceItem | None = None
    concept_grounding: list[TypstConceptGrounding] = Field(default_factory=list)
    mapping_warnings: list[str] = Field(default_factory=list)
    token_budget_notes: list[str] = Field(default_factory=list)


class TypstPrepareDebug(BaseModel):
    """Debug metadata returned by the prepare endpoint before real fitting is added."""

    source_mode: str
    draft_variant: TypstDraftVariant | None = None
    stored_resume_draft_id: int | None = None
    resolved_candidate_profile_id: int | None = None
    candidate_profile_available: bool = False
    stub_mode: bool = True
    fitter_model: str | None = None
    translation_applied: bool = False
    profile_assisted_sections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    section_counts: dict[str, int] = Field(default_factory=dict)
    char_metrics: dict[str, Any] = Field(default_factory=dict)
    limit_config: dict[str, Any] = Field(default_factory=lambda: deepcopy(TYPST_LIMIT_CONFIG))


class TypstPrepareRequest(BaseModel):
    """Request payload used to prepare a Typst payload from a final resume draft."""

    draft_id: int | None = Field(default=None, ge=1)
    draft_variant: TypstDraftVariant | None = None
    final_resume_draft: ResumeDraft | None = None
    candidate_profile_id: int | None = Field(default=None, ge=1)
    options: TypstRenderOptions

    @model_validator(mode="after")
    def validate_source_selection(self) -> "TypstPrepareRequest":
        """Accept exactly one source mode: stored draft or inline final draft."""

        has_stored_source = self.draft_id is not None
        has_inline_source = self.final_resume_draft is not None

        if has_stored_source == has_inline_source:
            raise ValueError("Provide exactly one source: either draft_id or final_resume_draft.")

        if has_stored_source:
            if self.draft_variant is None:
                raise ValueError("draft_variant is required when draft_id is provided.")
            if self.candidate_profile_id is not None:
                raise ValueError("candidate_profile_id is only allowed with final_resume_draft.")
            return self

        if self.candidate_profile_id is None:
            raise ValueError("candidate_profile_id is required when final_resume_draft is provided.")
        if self.draft_variant is not None:
            raise ValueError("draft_variant is only allowed with draft_id.")
        return self


class TypstPrepareResponse(BaseModel):
    """Prepared Typst payload plus debug metadata."""

    typst_payload: TypstPayload
    prepare_debug: TypstPrepareDebug | None = None


class TypstArtifactRef(BaseModel):
    """Metadata reference to one generated Typst-related artifact."""

    artifact_type: str
    filename: str
    relative_path: str
    absolute_path: str | None = None
    media_type: str
    size_bytes: int | None = None


class TypstPhotoUploadResponse(BaseModel):
    """Response returned after storing a controlled local photo asset."""

    photo_asset_id: str
    photo_artifact: TypstArtifactRef
    warnings: list[str] = Field(default_factory=list)


class TypstPdfLayoutMetrics(BaseModel):
    """Local PDF layout measurements extracted from a rendered Typst PDF."""

    page_count: int
    is_single_page: bool
    page_width_pt: float
    page_height_pt: float
    main_content_bottom_y: float | None = None
    footer_top_y: float | None = None
    free_space_before_footer_pt: float | None = None
    estimated_fill_ratio: float | None = None
    underfilled: bool = False
    overfilled: bool = False
    footer_overlap_risk: bool = False
    footer_detected: bool = False
    analysis_warnings: list[str] = Field(default_factory=list)


class TypstFitToPagePlan(BaseModel):
    """AI recommendation for a future explicit fit-to-page step."""

    action: Literal["none", "expand", "shorten", "review"]
    priority_sections: list[str] = Field(default_factory=list)
    avoid_sections: list[str] = Field(default_factory=list)
    intensity: Literal["small", "moderate", "large"]
    reason: str


class TypstQualityAnalysisRequest(BaseModel):
    """Request used to analyze the quality of a rendered Typst document."""

    typst_payload: TypstPayload
    layout_metrics: TypstPdfLayoutMetrics | None = None
    char_metrics: dict[str, Any] = Field(default_factory=dict)
    limit_config: dict[str, Any] = Field(default_factory=lambda: deepcopy(TYPST_LIMIT_CONFIG))
    render_warnings: list[str] = Field(default_factory=list)


class TypstQualityAnalysis(BaseModel):
    """Structured AI diagnosis of a rendered Typst document."""

    overall_status: Literal["good", "underfilled", "overfilled", "needs_review"]
    summary: str
    recommended_actions: list[str] = Field(default_factory=list)
    sections_to_expand: list[str] = Field(default_factory=list)
    sections_to_shorten: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    should_offer_fit_to_page: bool
    fit_to_page_plan: TypstFitToPagePlan
    confidence: float = Field(ge=0.0, le=1.0)


class TypstQualityAnalysisResponse(BaseModel):
    """Response returned by the Typst render quality-analysis endpoint."""

    analysis: TypstQualityAnalysis
    model: str
    warnings: list[str] = Field(default_factory=list)


class TypstExperienceBulletPatch(BaseModel):
    """One allowed fit-to-page update for an existing experience bullet."""

    model_config = ConfigDict(extra="forbid")

    entry_index: int = Field(ge=0)
    bullet_index: int = Field(ge=0)
    text: str
    reason: str


class TypstProjectDescriptionPatch(BaseModel):
    """One allowed fit-to-page update for an existing project description."""

    model_config = ConfigDict(extra="forbid")

    entry_index: int = Field(ge=0)
    description: str
    reason: str


class TypstFitToPagePatch(BaseModel):
    """Patch returned by AI for the explicit fit-to-page step."""

    model_config = ConfigDict(extra="forbid")

    summary_text: str | None = None
    experience_bullet_updates: list[TypstExperienceBulletPatch] = Field(default_factory=list)
    project_description_updates: list[TypstProjectDescriptionPatch] = Field(default_factory=list)
    rationale: str
    warnings: list[str] = Field(default_factory=list)


class TypstFitToPageRequest(BaseModel):
    """Request used to create a safe text-only fit-to-page patch."""

    typst_payload: TypstPayload
    layout_metrics: TypstPdfLayoutMetrics | None = None
    quality_analysis: TypstQualityAnalysis
    char_metrics: dict[str, Any] = Field(default_factory=dict)
    limit_config: dict[str, Any] = Field(default_factory=lambda: deepcopy(TYPST_LIMIT_CONFIG))
    render_warnings: list[str] = Field(default_factory=list)
    force: bool = False
    draft_id: int | None = Field(default=None, ge=1)
    stored_resume_draft_id: int | None = Field(default=None, ge=1)
    draft_variant: TypstDraftVariant | None = None
    source_evidence_pack: TypstSourceEvidencePack | None = None

    @model_validator(mode="after")
    def validate_source_context(self) -> "TypstFitToPageRequest":
        """Keep optional stored-draft context unambiguous."""

        if (
            self.draft_id is not None
            and self.stored_resume_draft_id is not None
            and self.draft_id != self.stored_resume_draft_id
        ):
            raise ValueError("draft_id and stored_resume_draft_id must refer to the same draft.")

        if (self.draft_id is not None or self.stored_resume_draft_id is not None) and self.draft_variant is None:
            raise ValueError("draft_variant is required when fit-to-page source draft context is provided.")
        return self


class TypstFitToPageDebug(BaseModel):
    """Debug metadata for the explicit fit-to-page patch step."""

    model: str
    changed_sections: list[str] = Field(default_factory=list)
    changed_fields: list[str] = Field(default_factory=list)
    rationale: str
    retry_attempted: bool = False
    retry_feedback: str | None = None
    initial_validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    char_metrics: dict[str, Any] = Field(default_factory=dict)
    section_counts: dict[str, int] = Field(default_factory=dict)
    source_evidence_pack_built: bool = False
    source_evidence_pack_used: bool = False
    source_evidence_entry_counts: dict[str, int] = Field(default_factory=dict)
    source_evidence_low_confidence_entries: list[str] = Field(default_factory=list)
    source_evidence_mapping_warnings: list[str] = Field(default_factory=list)


class TypstFitToPageResponse(BaseModel):
    """Response returned after merging and validating a fit-to-page patch."""

    patch: TypstFitToPagePatch
    typst_payload: TypstPayload
    fit_debug: TypstFitToPageDebug


class TypstRenderRequest(BaseModel):
    """Request payload used by the Typst render endpoint."""

    typst_payload: TypstPayload


class TypstRenderResponse(BaseModel):
    """Response returned by the Typst render endpoint."""

    status: str
    message: str
    render_id: str | None = None
    template_name: str
    typ_source_artifact: TypstArtifactRef | None = None
    pdf_artifact: TypstArtifactRef | None = None
    layout_metrics: TypstPdfLayoutMetrics | None = None
    warnings: list[str] = Field(default_factory=list)
