"""Small repository helpers for CRUD-like access to SQLite persistence tables."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select

from app.db.database import session_scope
from app.db.models import (
    CandidateProfileRecord,
    JobPostingRecord,
    MatchResultRecord,
    ResumeDraftRecord,
)


def save_candidate_profile_record(*, full_name: str, email: str, payload_json: str) -> dict[str, Any]:
    """Insert a candidate profile row and return its stored representation."""
    with session_scope() as session:
        record = CandidateProfileRecord(
            full_name=full_name,
            email=email,
            payload_json=payload_json,
        )
        session.add(record)
        session.flush()
        return _candidate_profile_record_to_dict(record, include_payload=True)


def update_candidate_profile_record(
    profile_id: int,
    *,
    full_name: str,
    email: str,
    payload_json: str,
) -> dict[str, Any] | None:
    """Update one candidate profile row in place and return its stored representation."""
    with session_scope() as session:
        record = session.get(CandidateProfileRecord, profile_id)
        if record is None:
            return None

        record.full_name = full_name
        record.email = email
        record.payload_json = payload_json
        record.saved_at = datetime.now(UTC)
        session.flush()
        return _candidate_profile_record_to_dict(record, include_payload=True)


def get_candidate_profile_record(profile_id: int) -> dict[str, Any] | None:
    """Load a single stored candidate profile row by ID."""
    with session_scope() as session:
        record = session.get(CandidateProfileRecord, profile_id)
        if record is None:
            return None
        return _candidate_profile_record_to_dict(record, include_payload=True)


def list_candidate_profile_records(limit: int = 50) -> list[dict[str, Any]]:
    """List candidate profile rows ordered from newest to oldest."""
    with session_scope() as session:
        statement = select(CandidateProfileRecord).order_by(desc(CandidateProfileRecord.id)).limit(limit)
        records = session.execute(statement).scalars().all()
        return [_candidate_profile_record_to_dict(record, include_payload=False) for record in records]


def delete_candidate_profile_record(profile_id: int) -> bool:
    """Delete one stored candidate profile row by ID.

    Args:
        profile_id: Database identifier of the stored candidate profile.

    Returns:
        True when the row existed and was deleted, otherwise False.
    """
    with session_scope() as session:
        record = session.get(CandidateProfileRecord, profile_id)
        if record is None:
            return False

        session.delete(record)
        session.flush()
        return True


def save_job_posting_record(
    *,
    source: str,
    source_url: str | None,
    title: str,
    company_name: str,
    location: str,
    payload_json: str,
) -> dict[str, Any]:
    """Insert a job posting row and return its stored representation."""
    with session_scope() as session:
        record = JobPostingRecord(
            source=source,
            source_url=source_url,
            title=title,
            company_name=company_name,
            location=location,
            payload_json=payload_json,
        )
        session.add(record)
        session.flush()
        return _job_posting_record_to_dict(record, include_payload=True)


def get_job_posting_record(job_posting_id: int) -> dict[str, Any] | None:
    """Load a single stored job posting row by ID."""
    with session_scope() as session:
        record = session.get(JobPostingRecord, job_posting_id)
        if record is None:
            return None
        return _job_posting_record_to_dict(record, include_payload=True)


def list_job_posting_records(limit: int = 50) -> list[dict[str, Any]]:
    """List job posting rows ordered from newest to oldest."""
    with session_scope() as session:
        statement = select(JobPostingRecord).order_by(desc(JobPostingRecord.id)).limit(limit)
        records = session.execute(statement).scalars().all()
        return [_job_posting_record_to_dict(record, include_payload=False) for record in records]


def delete_job_posting_record(job_posting_id: int) -> bool:
    """Delete one stored job posting row by ID.

    Args:
        job_posting_id: Database identifier of the stored job posting.

    Returns:
        True when the row existed and was deleted, otherwise False.
    """
    with session_scope() as session:
        record = session.get(JobPostingRecord, job_posting_id)
        if record is None:
            return False

        session.delete(record)
        session.flush()
        return True


def save_match_result_record(
    *,
    candidate_profile_id: int | None,
    job_posting_id: int | None,
    overall_score: float,
    fit_classification: str,
    recommendation: str,
    payload_json: str,
) -> dict[str, Any]:
    """Insert a match result row and return its stored representation."""
    with session_scope() as session:
        record = MatchResultRecord(
            candidate_profile_id=candidate_profile_id,
            job_posting_id=job_posting_id,
            overall_score=overall_score,
            fit_classification=fit_classification,
            recommendation=recommendation,
            payload_json=payload_json,
        )
        session.add(record)
        session.flush()
        return _match_result_record_to_dict(record, include_payload=True)


def get_match_result_record(match_result_id: int) -> dict[str, Any] | None:
    """Load a single stored match result row by ID."""
    with session_scope() as session:
        record = session.get(MatchResultRecord, match_result_id)
        if record is None:
            return None
        return _match_result_record_to_dict(record, include_payload=True)


def list_match_result_records(limit: int = 50) -> list[dict[str, Any]]:
    """List match result rows ordered from newest to oldest."""
    with session_scope() as session:
        statement = select(MatchResultRecord).order_by(desc(MatchResultRecord.id)).limit(limit)
        records = session.execute(statement).scalars().all()
        return [_match_result_record_to_dict(record, include_payload=False) for record in records]


def save_resume_draft_record(
    *,
    candidate_profile_id: int | None,
    job_posting_id: int | None,
    match_result_id: int | None,
    target_job_title: str | None,
    target_company_name: str | None,
    generation_mode: str,
    base_resume_artifacts_json: str,
) -> dict[str, Any]:
    """Insert a resume draft row and return its stored representation."""
    with session_scope() as session:
        record = ResumeDraftRecord(
            candidate_profile_id=candidate_profile_id,
            job_posting_id=job_posting_id,
            match_result_id=match_result_id,
            target_job_title=target_job_title,
            target_company_name=target_company_name,
            generation_mode=generation_mode,
            has_refined_version=False,
            base_resume_artifacts_json=base_resume_artifacts_json,
        )
        session.add(record)
        session.flush()
        return _resume_draft_record_to_dict(record, include_payload=True)


def update_resume_draft_record_refinement(
    draft_id: int,
    *,
    refined_resume_artifacts_json: str,
) -> dict[str, Any] | None:
    """Attach or replace the refined artifacts for one stored resume draft."""
    with session_scope() as session:
        record = session.get(ResumeDraftRecord, draft_id)
        if record is None:
            return None

        record.refined_resume_artifacts_json = refined_resume_artifacts_json
        record.has_refined_version = True
        record.updated_at = datetime.now(UTC)
        session.flush()
        return _resume_draft_record_to_dict(record, include_payload=True)


def get_resume_draft_record(draft_id: int) -> dict[str, Any] | None:
    """Load a single stored resume draft row by ID."""
    with session_scope() as session:
        record = session.get(ResumeDraftRecord, draft_id)
        if record is None:
            return None
        return _resume_draft_record_to_dict(record, include_payload=True)


def list_resume_draft_records(
    *,
    limit: int = 50,
    candidate_profile_id: int | None = None,
    job_posting_id: int | None = None,
) -> list[dict[str, Any]]:
    """List stored resume draft rows ordered from newest update to oldest."""
    with session_scope() as session:
        statement = select(ResumeDraftRecord)

        if candidate_profile_id is not None:
            statement = statement.where(ResumeDraftRecord.candidate_profile_id == candidate_profile_id)
        if job_posting_id is not None:
            statement = statement.where(ResumeDraftRecord.job_posting_id == job_posting_id)

        statement = statement.order_by(desc(ResumeDraftRecord.updated_at), desc(ResumeDraftRecord.id)).limit(limit)
        records = session.execute(statement).scalars().all()
        return [_resume_draft_record_to_dict(record, include_payload=False) for record in records]


def _candidate_profile_record_to_dict(
    record: CandidateProfileRecord,
    *,
    include_payload: bool,
) -> dict[str, Any]:
    """Convert a candidate profile ORM row into the repository return shape."""
    payload: dict[str, Any] = {
        "id": record.id,
        "saved_at": record.saved_at,
        "full_name": record.full_name,
        "email": record.email,
    }
    if include_payload:
        payload["payload_json"] = record.payload_json
    return payload


def _job_posting_record_to_dict(
    record: JobPostingRecord,
    *,
    include_payload: bool,
) -> dict[str, Any]:
    """Convert a job posting ORM row into the repository return shape."""
    payload: dict[str, Any] = {
        "id": record.id,
        "saved_at": record.saved_at,
        "source": record.source,
        "source_url": record.source_url,
        "title": record.title,
        "company_name": record.company_name,
        "location": record.location,
    }
    if include_payload:
        payload["payload_json"] = record.payload_json
    return payload


def _match_result_record_to_dict(
    record: MatchResultRecord,
    *,
    include_payload: bool,
) -> dict[str, Any]:
    """Convert a match result ORM row into the repository return shape."""
    payload: dict[str, Any] = {
        "id": record.id,
        "saved_at": record.saved_at,
        "candidate_profile_id": record.candidate_profile_id,
        "job_posting_id": record.job_posting_id,
        "overall_score": record.overall_score,
        "fit_classification": record.fit_classification,
        "recommendation": record.recommendation,
    }
    if include_payload:
        payload["payload_json"] = record.payload_json
    return payload


def _resume_draft_record_to_dict(
    record: ResumeDraftRecord,
    *,
    include_payload: bool,
) -> dict[str, Any]:
    """Convert a resume draft ORM row into the repository return shape."""
    payload: dict[str, Any] = {
        "id": record.id,
        "saved_at": record.saved_at,
        "updated_at": record.updated_at,
        "candidate_profile_id": record.candidate_profile_id,
        "job_posting_id": record.job_posting_id,
        "match_result_id": record.match_result_id,
        "target_job_title": record.target_job_title,
        "target_company_name": record.target_company_name,
        "generation_mode": record.generation_mode,
        "has_refined_version": record.has_refined_version,
    }
    if include_payload:
        payload["base_resume_artifacts_json"] = record.base_resume_artifacts_json
        payload["refined_resume_artifacts_json"] = record.refined_resume_artifacts_json
    return payload
