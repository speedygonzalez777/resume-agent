"""Resume draft generation, refinement and persistence endpoints."""

from datetime import datetime
import logging

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.contracts import MatchingHandoffPayload
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting
from app.models.match import MatchResult
from app.models.resume import (
    ChangeReport,
    ResumeDraft,
    ResumeDraftRefinementGuidance,
    ResumeDraftRefinementPatch,
    ResumeFallbackReason,
    ResumeGenerationMode,
    ResumeMatchResultSource,
)
from app.models.typst import (
    TypstPrepareRequest,
    TypstPrepareResponse,
    TypstFitToPageRequest,
    TypstFitToPageResponse,
    TypstPhotoUploadResponse,
    TypstQualityAnalysisRequest,
    TypstQualityAnalysisResponse,
    TypstRenderRequest,
    TypstRenderResponse,
)
from app.services.openai_typst_quality_analysis_service import (
    TypstQualityAnalysisOpenAIError,
    analyze_typst_render_quality_with_openai,
)
from app.services.openai_resume_draft_refinement_service import (
    ResumeDraftRefinementOpenAIError,
)
from app.services.resume_generation_service import generate_resume_artifacts
from app.services.resume_draft_refinement_service import (
    ResumeDraftRefinementMergeError,
    refine_resume_draft as refine_resume_draft_service,
)
from app.services.resume_typst_service import (
    TypstArtifactError,
    TypstFitToPageError,
    TypstPrepareError,
    TypstPrepareSourceError,
    fit_typst_payload_to_page,
    prepare_typst_payload,
    render_typst_payload,
    resolve_typst_render_artifact,
    save_typst_photo_asset,
    TypstRenderError,
)
from app.services.persistence_service import (
    get_resume_draft,
    list_resume_drafts,
    save_resume_draft,
    update_resume_draft_refinement,
)

router = APIRouter(prefix="/resume", tags=["resume"])
logger = logging.getLogger(__name__)


class ResumeGenerationRequest(BaseModel):
    """Request payload for CV draft generation and optional persistence links."""

    candidate_profile: CandidateProfile
    job_posting: JobPosting
    match_result: MatchResult | None = None
    matching_handoff: MatchingHandoffPayload | None = None
    candidate_profile_id: int | None = None
    job_posting_id: int | None = None
    match_result_id: int | None = None


class ResumeGenerationResponse(BaseModel):
    """Response payload returned by the resume generation endpoint."""

    resume_draft: ResumeDraft
    change_report: ChangeReport
    generation_mode: ResumeGenerationMode
    match_result_source: ResumeMatchResultSource
    fallback_reason: ResumeFallbackReason | None = None
    generation_notes: list[str] = Field(default_factory=list)
    offer_signal_debug: dict[str, object] | None = None
    generation_debug: dict[str, object] | None = None
    resume_draft_record_id: int | None = None
    resume_draft_saved_at: datetime | None = None
    persistence_warning: str | None = None


class ResumeDebugEnvelope(BaseModel):
    """Stored developer-facing debug envelope for the resume generation flow."""

    matching_handoff: bool | None = None
    request_body: dict[str, object] | None = None
    response_body: dict[str, object] | None = None
    request_body_unavailable_reason: str | None = None


class ResumeDraftRefinementRequest(BaseModel):
    """Request payload for optional AI refinement of an existing ResumeDraft."""

    resume_draft: ResumeDraft
    guidance: ResumeDraftRefinementGuidance
    resume_draft_record_id: int | None = None


class ResumeDraftRefinementResponse(BaseModel):
    """Response payload returned by the AI draft-refinement endpoint."""

    refined_resume_draft: ResumeDraft
    refinement_patch: ResumeDraftRefinementPatch
    resume_draft_record_id: int | None = None
    resume_draft_updated_at: datetime | None = None
    persistence_warning: str | None = None


class ResumeDraftListItem(BaseModel):
    """Compact saved-resume-draft item used in list responses."""

    id: int
    saved_at: datetime
    updated_at: datetime
    candidate_profile_id: int | None = None
    job_posting_id: int | None = None
    match_result_id: int | None = None
    target_job_title: str | None = None
    target_company_name: str | None = None
    generation_mode: ResumeGenerationMode
    has_refined_version: bool


class StoredResumeDraftResponse(BaseModel):
    """Full stored resume-draft record returned for detail responses."""

    id: int
    saved_at: datetime
    updated_at: datetime
    candidate_profile_id: int | None = None
    job_posting_id: int | None = None
    match_result_id: int | None = None
    target_job_title: str | None = None
    target_company_name: str | None = None
    generation_mode: ResumeGenerationMode
    has_refined_version: bool
    base_resume_artifacts: ResumeGenerationResponse
    resume_debug_envelope: ResumeDebugEnvelope
    refined_resume_artifacts: ResumeDraftRefinementResponse | None = None


@router.post("/generate", response_model=ResumeGenerationResponse)
def generate_resume(payload: ResumeGenerationRequest) -> ResumeGenerationResponse:
    """Generate a ResumeDraft and save it when SQLite persistence is available."""
    requirement_priority_lookup = None
    candidate_profile_understanding = None
    requirement_priority_lookup_provided = False
    candidate_profile_understanding_provided = False

    if payload.matching_handoff is not None:
        requirement_priority_lookup = payload.matching_handoff.requirement_priority_lookup
        candidate_profile_understanding = payload.matching_handoff.candidate_profile_understanding
        requirement_priority_lookup_provided = (
            payload.matching_handoff.requirement_priority_lookup is not None
        )
        candidate_profile_understanding_provided = (
            payload.matching_handoff.candidate_profile_understanding is not None
        )

    artifacts = generate_resume_artifacts(
        payload.candidate_profile,
        payload.job_posting,
        payload.match_result,
        requirement_priority_lookup=requirement_priority_lookup,
        candidate_profile_understanding=candidate_profile_understanding,
        requirement_priority_lookup_provided=requirement_priority_lookup_provided,
        candidate_profile_understanding_provided=candidate_profile_understanding_provided,
        matching_handoff_supplied=payload.matching_handoff is not None,
    )
    response_payload = ResumeGenerationResponse.model_validate(artifacts)
    resume_debug_envelope = {
        "matching_handoff": payload.matching_handoff is not None,
        "request_body": payload.model_dump(mode="json"),
    }

    try:
        stored_record = save_resume_draft(
            candidate_profile_id=payload.candidate_profile_id,
            job_posting_id=payload.job_posting_id,
            match_result_id=payload.match_result_id,
            target_job_title=response_payload.resume_draft.target_job_title or payload.job_posting.title,
            target_company_name=response_payload.resume_draft.target_company_name or payload.job_posting.company_name,
            generation_mode=response_payload.generation_mode.value,
            base_resume_artifacts={
                **response_payload.model_dump(
                    mode="json",
                    exclude={"resume_draft_record_id", "resume_draft_saved_at", "persistence_warning"},
                ),
                "resume_debug_envelope": resume_debug_envelope,
            },
        )
    except Exception:
        logger.exception("Failed to persist generated resume draft")
        return response_payload.model_copy(
            update={
                "resume_draft_record_id": None,
                "resume_draft_saved_at": None,
                "persistence_warning": "Generated draft could not be saved to local SQLite storage.",
            }
        )

    return response_payload.model_copy(
        update={
            "resume_draft_record_id": stored_record["id"],
            "resume_draft_saved_at": stored_record["saved_at"],
            "persistence_warning": None,
        }
    )


@router.post("/refine-draft", response_model=ResumeDraftRefinementResponse)
def refine_resume_draft(
    payload: ResumeDraftRefinementRequest,
) -> ResumeDraftRefinementResponse:
    """Apply optional AI refinement to an existing ResumeDraft."""
    try:
        artifacts = refine_resume_draft_service(
            payload.resume_draft,
            payload.guidance,
        )
    except ResumeDraftRefinementOpenAIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ResumeDraftRefinementMergeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response_payload = ResumeDraftRefinementResponse.model_validate(artifacts)

    if payload.resume_draft_record_id is None:
        return response_payload

    try:
        stored_record = update_resume_draft_refinement(
            payload.resume_draft_record_id,
            refined_resume_artifacts=response_payload.model_dump(
                mode="json",
                exclude={"resume_draft_record_id", "resume_draft_updated_at", "persistence_warning"},
            ),
        )
    except Exception:
        logger.exception("Failed to persist refined resume draft")
        return response_payload.model_copy(
            update={
                "resume_draft_record_id": payload.resume_draft_record_id,
                "resume_draft_updated_at": None,
                "persistence_warning": "Refined draft could not be saved to local SQLite storage.",
            }
        )

    if stored_record is None:
        return response_payload.model_copy(
            update={
                "resume_draft_record_id": payload.resume_draft_record_id,
                "resume_draft_updated_at": None,
                "persistence_warning": "Stored resume draft record was not found, so the refined version was returned only for this session.",
            }
        )

    return response_payload.model_copy(
        update={
            "resume_draft_record_id": stored_record["id"],
            "resume_draft_updated_at": stored_record["updated_at"],
            "persistence_warning": None,
        }
    )


@router.post("/typst/prepare", response_model=TypstPrepareResponse)
def prepare_typst_resume(payload: TypstPrepareRequest) -> TypstPrepareResponse:
    """Resolve one final draft source and return a placeholder Typst payload."""

    try:
        return prepare_typst_payload(payload)
    except (TypstPrepareSourceError, TypstPrepareError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_error_detail(stage="prepare")) from exc


@router.post("/typst/photo-assets", response_model=TypstPhotoUploadResponse)
async def upload_typst_resume_photo(file: UploadFile = File(...)) -> TypstPhotoUploadResponse:
    """Store a validated local photo asset for the Typst resume renderer."""

    try:
        content = await file.read()
        return save_typst_photo_asset(
            original_filename=file.filename or "",
            content_type=file.content_type,
            content=content,
        )
    except TypstArtifactError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/typst/render", response_model=TypstRenderResponse)
def render_typst_resume(payload: TypstRenderRequest) -> TypstRenderResponse:
    """Render an already prepared Typst payload into .typ and .pdf artifacts."""

    try:
        return render_typst_payload(payload.typst_payload)
    except TypstRenderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_error_detail(stage="render")) from exc


@router.post("/typst/analyze-render", response_model=TypstQualityAnalysisResponse)
def analyze_typst_render_quality(payload: TypstQualityAnalysisRequest) -> TypstQualityAnalysisResponse:
    """Analyze a rendered Typst CV with OpenAI without modifying the TypstPayload."""

    try:
        return analyze_typst_render_quality_with_openai(payload)
    except TypstQualityAnalysisOpenAIError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error_code": "typst_quality_analysis_failed",
                "message": exc.message,
                "stage": "analyze-render",
                **exc.details,
            },
        ) from exc


@router.post("/typst/fit-to-page", response_model=TypstFitToPageResponse)
def fit_typst_resume_to_page(payload: TypstFitToPageRequest) -> TypstFitToPageResponse:
    """Create a safe text-only patch for a prepared TypstPayload without rendering it."""

    try:
        return fit_typst_payload_to_page(payload)
    except TypstFitToPageError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.to_error_detail(stage="fit-to-page"),
        ) from exc


@router.get("/typst/artifacts/{render_id}/{artifact_type}")
def download_typst_resume_artifact(
    render_id: str,
    artifact_type: str,
    disposition: str = Query(default="attachment"),
) -> FileResponse:
    """Download one generated Typst source or PDF artifact from the controlled artifacts directory."""

    normalized_disposition = (disposition or "").strip().lower()
    if normalized_disposition not in {"attachment", "inline"}:
        raise HTTPException(status_code=400, detail="Invalid disposition. Use 'attachment' or 'inline'.")

    try:
        artifact_path, media_type = resolve_typst_render_artifact(
            render_id=render_id,
            artifact_type=artifact_type,
        )
    except TypstArtifactError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    response_disposition = "inline" if artifact_type.strip().lower() == "pdf" else "attachment"
    if normalized_disposition == "attachment":
        response_disposition = "attachment"

    return FileResponse(
        path=artifact_path,
        media_type=media_type,
        filename=artifact_path.name,
        content_disposition_type=response_disposition,
    )


@router.get("/drafts", response_model=list[ResumeDraftListItem])
def list_saved_resume_drafts(
    limit: int = Query(default=50, ge=1, le=100),
    candidate_profile_id: int | None = Query(default=None),
    job_posting_id: int | None = Query(default=None),
) -> list[ResumeDraftListItem]:
    """List stored resume drafts ordered from the newest update to the oldest."""
    return [
        ResumeDraftListItem.model_validate(item)
        for item in list_resume_drafts(
            limit=limit,
            candidate_profile_id=candidate_profile_id,
            job_posting_id=job_posting_id,
        )
    ]


@router.get("/drafts/{draft_id}", response_model=StoredResumeDraftResponse)
def get_saved_resume_draft(draft_id: int) -> StoredResumeDraftResponse:
    """Load one stored resume draft together with its base and refined artifacts."""
    stored_record = get_resume_draft(draft_id)
    if stored_record is None:
        raise HTTPException(status_code=404, detail="Resume draft not found")

    stored_base_resume_artifacts = dict(stored_record["base_resume_artifacts"])
    stored_resume_debug_envelope = stored_base_resume_artifacts.pop("resume_debug_envelope", None)
    response_body = {
        **stored_base_resume_artifacts,
        "resume_draft_record_id": stored_record["id"],
        "resume_draft_saved_at": stored_record["saved_at"],
        "persistence_warning": None,
    }

    base_resume_artifacts = ResumeGenerationResponse.model_validate(
        {
            **response_body,
        }
    )
    resume_debug_envelope = ResumeDebugEnvelope.model_validate(
        {
            "matching_handoff": (
                stored_resume_debug_envelope.get("matching_handoff")
                if isinstance(stored_resume_debug_envelope, dict)
                else None
            ),
            "request_body": (
                stored_resume_debug_envelope.get("request_body")
                if isinstance(stored_resume_debug_envelope, dict)
                else None
            ),
            "response_body": response_body,
            "request_body_unavailable_reason": (
                None
                if isinstance(stored_resume_debug_envelope, dict)
                and stored_resume_debug_envelope.get("request_body") is not None
                else "Historyczny request resume nie zostal zapisany dla tego draftu."
            ),
        }
    )

    refined_resume_artifacts = None
    if stored_record["refined_resume_artifacts"] is not None:
        refined_resume_artifacts = ResumeDraftRefinementResponse.model_validate(
            {
                **stored_record["refined_resume_artifacts"],
                "resume_draft_record_id": stored_record["id"],
                "resume_draft_updated_at": stored_record["updated_at"],
                "persistence_warning": None,
            }
        )

    return StoredResumeDraftResponse.model_validate(
        {
            **stored_record,
            "base_resume_artifacts": base_resume_artifacts,
            "resume_debug_envelope": resume_debug_envelope,
            "refined_resume_artifacts": refined_resume_artifacts,
        }
    )
