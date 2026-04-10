"""Minimal SQLAlchemy table models used for local JSON-based persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class CandidateProfileRecord(Base):
    """Stored candidate profile metadata plus serialized JSON payload."""
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class JobPostingRecord(Base):
    """Stored job posting metadata plus serialized JSON payload."""
    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class MatchResultRecord(Base):
    """Stored match result metadata plus serialized JSON payload."""
    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    candidate_profile_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    job_posting_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    fit_classification: Mapped[str] = mapped_column(String(50), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class ResumeDraftRecord(Base):
    """Stored resume draft metadata plus serialized base and refined artifacts."""
    __tablename__ = "resume_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    candidate_profile_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    job_posting_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_result_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generation_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    has_refined_version: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    base_resume_artifacts_json: Mapped[str] = mapped_column(Text, nullable=False)
    refined_resume_artifacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
