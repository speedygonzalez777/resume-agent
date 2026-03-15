from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.models.analysis import MatchAnalysisRequest
from app.models.match import MatchResult
from app.services.match_service import analyze_match_basic
from app.services.persistence_service import get_match_result, list_match_results, save_match_result

router = APIRouter(prefix="/match", tags=["match"])


class SaveMatchResultRequest(BaseModel):
    match_result: MatchResult
    candidate_profile_id: int | None = Field(default=None)
    job_posting_id: int | None = Field(default=None)


class StoredMatchResultResponse(BaseModel):
    id: int
    saved_at: datetime
    candidate_profile_id: int | None = None
    job_posting_id: int | None = None
    overall_score: float
    fit_classification: str
    recommendation: str
    payload: MatchResult


class MatchResultListItem(BaseModel):
    id: int
    saved_at: datetime
    candidate_profile_id: int | None = None
    job_posting_id: int | None = None
    overall_score: float
    fit_classification: str
    recommendation: str


@router.post("/analyze", response_model=MatchResult)
def analyze_match(payload: MatchAnalysisRequest) -> MatchResult:
    return analyze_match_basic(payload)


@router.post("/save", response_model=StoredMatchResultResponse)
def save_match(payload: SaveMatchResultRequest) -> StoredMatchResultResponse:
    stored_match = save_match_result(
        payload.match_result,
        candidate_profile_id=payload.candidate_profile_id,
        job_posting_id=payload.job_posting_id,
    )
    return StoredMatchResultResponse.model_validate(stored_match)


@router.get("", response_model=list[MatchResultListItem])
def list_matches(limit: int = Query(default=50, ge=1, le=100)) -> list[MatchResultListItem]:
    return [MatchResultListItem.model_validate(item) for item in list_match_results(limit=limit)]


@router.get("/{match_result_id}", response_model=StoredMatchResultResponse)
def get_match(match_result_id: int) -> StoredMatchResultResponse:
    stored_match = get_match_result(match_result_id)
    if stored_match is None:
        raise HTTPException(status_code=404, detail="Match result not found")
    return StoredMatchResultResponse.model_validate(stored_match)
