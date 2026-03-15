from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.candidate import CandidateProfile
from app.services.persistence_service import get_candidate_profile, save_candidate_profile

router = APIRouter(prefix="/profile", tags=["profile"])


class StoredCandidateProfileResponse(BaseModel):
    id: int
    saved_at: datetime
    full_name: str
    email: str
    payload: CandidateProfile


@router.post("/validate")
def validate_profile(profile: CandidateProfile) -> dict:
    return {
        "message": "Candidate profile is valid",
        "full_name": profile.personal_info.full_name,
        "target_roles_count": len(profile.target_roles),
        "experience_count": len(profile.experience_entries),
        "project_count": len(profile.project_entries),
        "skills_count": len(profile.skill_entries),
    }


@router.post("/save", response_model=StoredCandidateProfileResponse)
def save_profile(profile: CandidateProfile) -> StoredCandidateProfileResponse:
    return StoredCandidateProfileResponse.model_validate(save_candidate_profile(profile))


@router.get("/{profile_id}", response_model=StoredCandidateProfileResponse)
def get_profile(profile_id: int) -> StoredCandidateProfileResponse:
    stored_profile = get_candidate_profile(profile_id)
    if stored_profile is None:
        raise HTTPException(status_code=404, detail="Candidate profile not found")
    return StoredCandidateProfileResponse.model_validate(stored_profile)
