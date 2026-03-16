"""Profile validation and persistence endpoints."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models.candidate import CandidateProfile
from app.services.persistence_service import delete_candidate_profile, get_candidate_profile, list_candidate_profiles, save_candidate_profile

router = APIRouter(prefix="/profile", tags=["profile"])


class StoredCandidateProfileResponse(BaseModel):
    """Response payload returned for a stored candidate profile."""
    id: int
    saved_at: datetime
    full_name: str
    email: str
    payload: CandidateProfile


class CandidateProfileListItem(BaseModel):
    """Compact candidate profile item used in list responses."""

    id: int
    saved_at: datetime
    full_name: str
    email: str


class DeleteCandidateProfileResponse(BaseModel):
    """Response payload returned after deleting a stored candidate profile."""

    id: int
    deleted: bool
    message: str


@router.post("/validate")
def validate_profile(profile: CandidateProfile) -> dict:
    """Validate a candidate profile payload and return lightweight summary counts."""
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
    """Persist a candidate profile in SQLite and return stored metadata."""
    return StoredCandidateProfileResponse.model_validate(save_candidate_profile(profile))


@router.get("", response_model=list[CandidateProfileListItem])
def list_profiles(limit: int = Query(default=50, ge=1, le=100)) -> list[CandidateProfileListItem]:
    """List stored candidate profiles ordered from newest to oldest."""
    return [CandidateProfileListItem.model_validate(item) for item in list_candidate_profiles(limit=limit)]


@router.get("/{profile_id}", response_model=StoredCandidateProfileResponse)
def get_profile(profile_id: int) -> StoredCandidateProfileResponse:
    """Load a previously stored candidate profile by ID."""
    stored_profile = get_candidate_profile(profile_id)
    if stored_profile is None:
        raise HTTPException(status_code=404, detail="Candidate profile not found")
    return StoredCandidateProfileResponse.model_validate(stored_profile)


@router.delete("/{profile_id}", response_model=DeleteCandidateProfileResponse)
def delete_profile(profile_id: int) -> DeleteCandidateProfileResponse:
    """Delete a stored candidate profile by ID."""
    was_deleted = delete_candidate_profile(profile_id)
    if not was_deleted:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    return DeleteCandidateProfileResponse(
        id=profile_id,
        deleted=True,
        message="Candidate profile deleted",
    )
