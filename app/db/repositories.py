from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select

from app.db.database import session_scope
from app.db.models import CandidateProfileRecord, JobPostingRecord, MatchResultRecord


def save_candidate_profile_record(*, full_name: str, email: str, payload_json: str) -> dict[str, Any]:
    with session_scope() as session:
        record = CandidateProfileRecord(
            full_name=full_name,
            email=email,
            payload_json=payload_json,
        )
        session.add(record)
        session.flush()
        return _candidate_profile_record_to_dict(record, include_payload=True)


def get_candidate_profile_record(profile_id: int) -> dict[str, Any] | None:
    with session_scope() as session:
        record = session.get(CandidateProfileRecord, profile_id)
        if record is None:
            return None
        return _candidate_profile_record_to_dict(record, include_payload=True)


def list_candidate_profile_records(limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as session:
        statement = select(CandidateProfileRecord).order_by(desc(CandidateProfileRecord.id)).limit(limit)
        records = session.execute(statement).scalars().all()
        return [_candidate_profile_record_to_dict(record, include_payload=False) for record in records]


def save_job_posting_record(
    *,
    source: str,
    source_url: str | None,
    title: str,
    company_name: str,
    location: str,
    payload_json: str,
) -> dict[str, Any]:
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
    with session_scope() as session:
        record = session.get(JobPostingRecord, job_posting_id)
        if record is None:
            return None
        return _job_posting_record_to_dict(record, include_payload=True)


def list_job_posting_records(limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as session:
        statement = select(JobPostingRecord).order_by(desc(JobPostingRecord.id)).limit(limit)
        records = session.execute(statement).scalars().all()
        return [_job_posting_record_to_dict(record, include_payload=False) for record in records]


def save_match_result_record(
    *,
    candidate_profile_id: int | None,
    job_posting_id: int | None,
    overall_score: float,
    fit_classification: str,
    recommendation: str,
    payload_json: str,
) -> dict[str, Any]:
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
    with session_scope() as session:
        record = session.get(MatchResultRecord, match_result_id)
        if record is None:
            return None
        return _match_result_record_to_dict(record, include_payload=True)


def list_match_result_records(limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as session:
        statement = select(MatchResultRecord).order_by(desc(MatchResultRecord.id)).limit(limit)
        records = session.execute(statement).scalars().all()
        return [_match_result_record_to_dict(record, include_payload=False) for record in records]


def _candidate_profile_record_to_dict(
    record: CandidateProfileRecord,
    *,
    include_payload: bool,
) -> dict[str, Any]:
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
