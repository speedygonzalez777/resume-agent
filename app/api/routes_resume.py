"""Resume draft generation endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.models.candidate import CandidateProfile
from app.models.job import JobPosting
from app.models.match import MatchResult
from app.models.resume import ChangeReport, ResumeDraft
from app.services.resume_generation_service import generate_resume_artifacts

router = APIRouter(prefix="/resume", tags=["resume"])


class ResumeGenerationRequest(BaseModel):
    """Request payload for stateless CV draft generation."""

    candidate_profile: CandidateProfile
    job_posting: JobPosting
    match_result: MatchResult


class ResumeGenerationResponse(BaseModel):
    """Response payload returned by the resume generation endpoint."""

    resume_draft: ResumeDraft
    change_report: ChangeReport


@router.post("/generate", response_model=ResumeGenerationResponse)
def generate_resume(payload: ResumeGenerationRequest) -> ResumeGenerationResponse:
    """Generate a ResumeDraft and ChangeReport without persisting any new records."""
    artifacts = generate_resume_artifacts(
        payload.candidate_profile,
        payload.job_posting,
        payload.match_result,
    )
    return ResumeGenerationResponse.model_validate(artifacts)
