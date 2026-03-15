from fastapi import FastAPI
from app.api.routes_profile import router as profile_router
from app.api.routes_job import router as job_router
from app.api.routes_match import router as match_router

app = FastAPI(
    title="Resume Tailoring Agent",
    version="0.1.0",
    description="Backend MVP do dopasowywania CV do ofert pracy."
)

app.include_router(profile_router)
app.include_router(job_router)
app.include_router(match_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Resume Tailoring Agent API działa"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}