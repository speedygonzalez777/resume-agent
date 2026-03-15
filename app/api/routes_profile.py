from fastapi import APIRouter
from app.models.candidate import CandidateProfile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.post("/validate")
def validate_profile(profile: CandidateProfile) -> dict:
    return {
        "message": "Candidate profile is valid",
        "full_name": profile.personal_info.full_name,
        "target_roles_count": len(profile.target_roles),
        "experience_count": len(profile.experience_entries),
        "project_count": len(profile.project_entries),
        "skills_count": len(profile.skill_entries)
    }