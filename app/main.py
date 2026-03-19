"""FastAPI application entrypoint for the local Resume Tailoring Agent backend."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_job import router as job_router
from app.api.routes_match import router as match_router
from app.api.routes_profile import router as profile_router
from app.api.routes_resume import router as resume_router
from app.db import init_db, reset_database_state

_ALLOWED_FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize application resources on startup and release them on shutdown."""
    init_db()
    try:
        yield
    finally:
        reset_database_state()


app = FastAPI(
    title="Resume Tailoring Agent",
    version="0.1.0",
    description="Backend MVP do dopasowywania CV do ofert pracy.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile_router)
app.include_router(job_router)
app.include_router(match_router)
app.include_router(resume_router)


@app.get("/")
def root() -> dict[str, str]:
    """Return a minimal root payload proving that the API is reachable."""
    return {"message": "Resume Tailoring Agent API dziala"}


@app.get("/health")
def health() -> dict[str, str]:
    """Return the health status used by local smoke checks and the frontend MVP."""
    return {"status": "ok"}
