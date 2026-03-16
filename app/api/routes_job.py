"""Job validation, parsing and persistence endpoints."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl

from app.models.job import JobPosting
from app.services.job_parse_errors import JobParseError
from app.services.job_url_parse_service import parse_job_posting_from_url
from app.services.persistence_service import delete_job_posting, get_job_posting, list_job_postings, save_job_posting

router = APIRouter(prefix="/job", tags=["job"])


class JobParseUrlRequest(BaseModel):
    """Request payload for parsing a single job posting URL."""
    url: HttpUrl = Field(..., description="URL do pojedynczej oferty pracy")


class SaveJobPostingRequest(BaseModel):
    """Request payload for saving a parsed JobPosting with optional source metadata."""
    job_posting: JobPosting
    source_url: HttpUrl | None = Field(default=None, description="Opcjonalny URL zrodlowy oferty")


class StoredJobPostingResponse(BaseModel):
    """Response payload returned for a stored job posting."""
    id: int
    saved_at: datetime
    source: str
    source_url: str | None = None
    title: str
    company_name: str
    location: str
    payload: JobPosting


class JobPostingListItem(BaseModel):
    """Compact job posting item used in list responses."""
    id: int
    saved_at: datetime
    source: str
    source_url: str | None = None
    title: str
    company_name: str
    location: str


class DeleteJobPostingResponse(BaseModel):
    """Response payload returned after deleting a stored job posting."""

    id: int
    deleted: bool
    message: str


@router.post("/validate")
def validate_job(job: JobPosting) -> dict:
    """Validate a JobPosting payload and return lightweight summary counts."""
    return {
        "message": "Job posting is valid",
        "title": job.title,
        "company_name": job.company_name,
        "requirements_count": len(job.requirements),
        "responsibilities_count": len(job.responsibilities),
        "keywords_count": len(job.keywords),
    }


@router.post("/parse-url", response_model=JobPosting)
def parse_job_url(payload: JobParseUrlRequest) -> JobPosting:
    """Parse a public job URL into a structured JobPosting."""
    try:
        return parse_job_posting_from_url(str(payload.url))
    except JobParseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_http_detail()) from exc


@router.post("/save", response_model=StoredJobPostingResponse)
def save_job(payload: SaveJobPostingRequest) -> StoredJobPostingResponse:
    """Persist a parsed JobPosting and return stored metadata."""
    stored_job = save_job_posting(
        payload.job_posting,
        source_url=str(payload.source_url) if payload.source_url else None,
    )
    return StoredJobPostingResponse.model_validate(stored_job)


@router.get("", response_model=list[JobPostingListItem])
def list_jobs(limit: int = Query(default=50, ge=1, le=100)) -> list[JobPostingListItem]:
    """List stored job postings ordered from newest to oldest."""
    return [JobPostingListItem.model_validate(item) for item in list_job_postings(limit=limit)]


@router.get("/{job_posting_id}", response_model=StoredJobPostingResponse)
def get_job(job_posting_id: int) -> StoredJobPostingResponse:
    """Load a stored job posting by ID."""
    stored_job = get_job_posting(job_posting_id)
    if stored_job is None:
        raise HTTPException(status_code=404, detail="Job posting not found")
    return StoredJobPostingResponse.model_validate(stored_job)


@router.delete("/{job_posting_id}", response_model=DeleteJobPostingResponse)
def delete_job(job_posting_id: int) -> DeleteJobPostingResponse:
    """Delete a stored job posting by ID."""
    was_deleted = delete_job_posting(job_posting_id)
    if not was_deleted:
        raise HTTPException(status_code=404, detail="Job posting not found")

    return DeleteJobPostingResponse(
        id=job_posting_id,
        deleted=True,
        message="Job posting deleted",
    )
