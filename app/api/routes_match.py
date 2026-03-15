from fastapi import APIRouter
from app.models.analysis import MatchAnalysisRequest
from app.models.match import MatchResult
from app.services.match_service import analyze_match_basic

router = APIRouter(prefix="/match", tags=["match"])


@router.post("/analyze", response_model=MatchResult)
def analyze_match(payload: MatchAnalysisRequest) -> MatchResult:
    return analyze_match_basic(payload)
