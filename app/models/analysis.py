from pydantic import BaseModel, Field
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting


class MatchAnalysisRequest(BaseModel):
    candidate_profile: CandidateProfile = Field(
        ...,
        description="Profil kandydata do analizy"
    )
    job_posting: JobPosting = Field(
        ...,
        description="Oferta pracy do porównania"
    )