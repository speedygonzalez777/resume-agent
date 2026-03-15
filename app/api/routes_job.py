from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from app.models.job import JobPosting
from app.services.job_parse_errors import JobParseError
from app.services.job_url_parse_service import parse_job_posting_from_url

router = APIRouter(prefix="/job", tags=["job"])


class JobParseUrlRequest(BaseModel):
    url: HttpUrl = Field(..., description="URL do pojedynczej oferty pracy")


@router.post("/validate")
def validate_job(job: JobPosting) -> dict:
    return {
        "message": "Job posting is valid",
        "title": job.title,
        "company_name": job.company_name,
        "requirements_count": len(job.requirements),
        "responsibilities_count": len(job.responsibilities),
        "keywords_count": len(job.keywords)
    }


@router.post("/parse-url", response_model=JobPosting)
def parse_job_url(payload: JobParseUrlRequest) -> JobPosting:
    try:
        return parse_job_posting_from_url(str(payload.url))
    except JobParseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_http_detail()) from exc
