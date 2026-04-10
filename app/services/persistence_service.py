"""Service layer for storing and loading domain models from SQLite JSON payloads."""

from __future__ import annotations

import json
from typing import Any

from app.db.repositories import (
    delete_candidate_profile_record,
    delete_job_posting_record,
    get_candidate_profile_record,
    get_job_posting_record,
    get_match_result_record,
    get_resume_draft_record,
    list_candidate_profile_records,
    list_job_posting_records,
    list_match_result_records,
    list_resume_draft_records,
    save_candidate_profile_record,
    save_job_posting_record,
    save_match_result_record,
    save_resume_draft_record,
    update_candidate_profile_record,
    update_resume_draft_record_refinement,
)
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting
from app.models.match import MatchResult


def save_candidate_profile(profile: CandidateProfile) -> dict[str, Any]:
    """Persist a candidate profile and return stored metadata with the payload."""
    record = save_candidate_profile_record(
        full_name=profile.personal_info.full_name,
        email=profile.personal_info.email,
        payload_json=_serialize_model(profile),
    )
    return {
        "id": record["id"],
        "saved_at": record["saved_at"],
        "full_name": record["full_name"],
        "email": record["email"],
        "payload": profile,
    }


def update_candidate_profile(profile_id: int, profile: CandidateProfile) -> dict[str, Any] | None:
    """Update one stored candidate profile and return the refreshed metadata with payload."""
    record = update_candidate_profile_record(
        profile_id,
        full_name=profile.personal_info.full_name,
        email=profile.personal_info.email,
        payload_json=_serialize_model(profile),
    )
    if record is None:
        return None
    return {
        "id": record["id"],
        "saved_at": record["saved_at"],
        "full_name": record["full_name"],
        "email": record["email"],
        "payload": profile,
    }


def get_candidate_profile(profile_id: int) -> dict[str, Any] | None:
    """Load a stored candidate profile by database ID."""
    record = get_candidate_profile_record(profile_id)
    if record is None:
        return None
    return {
        "id": record["id"],
        "saved_at": record["saved_at"],
        "full_name": record["full_name"],
        "email": record["email"],
        "payload": _deserialize_model(record["payload_json"], CandidateProfile),
    }


def list_candidate_profiles(limit: int = 50) -> list[dict[str, Any]]:
    """List stored candidate profiles without loading full payload JSON."""
    records = list_candidate_profile_records(limit=limit)
    return [
        {
            "id": record["id"],
            "saved_at": record["saved_at"],
            "full_name": record["full_name"],
            "email": record["email"],
        }
        for record in records
    ]


def delete_candidate_profile(profile_id: int) -> bool:
    """Delete a stored candidate profile by database ID.

    Args:
        profile_id: Database identifier of the stored candidate profile.

    Returns:
        True when the record existed and was deleted, otherwise False.
    """
    return delete_candidate_profile_record(profile_id)


def save_job_posting(job_posting: JobPosting, *, source_url: str | None = None) -> dict[str, Any]:
    """Persist a parsed job posting together with lightweight listing metadata."""
    record = save_job_posting_record(
        source=job_posting.source,
        source_url=source_url,
        title=job_posting.title,
        company_name=job_posting.company_name,
        location=job_posting.location,
        payload_json=_serialize_model(job_posting),
    )
    return {
        "id": record["id"],
        "saved_at": record["saved_at"],
        "source": record["source"],
        "source_url": record["source_url"],
        "title": record["title"],
        "company_name": record["company_name"],
        "location": record["location"],
        "payload": job_posting,
    }


def get_job_posting(job_posting_id: int) -> dict[str, Any] | None:
    """Load a stored job posting by database ID."""
    record = get_job_posting_record(job_posting_id)
    if record is None:
        return None
    return {
        "id": record["id"],
        "saved_at": record["saved_at"],
        "source": record["source"],
        "source_url": record["source_url"],
        "title": record["title"],
        "company_name": record["company_name"],
        "location": record["location"],
        "payload": _deserialize_model(record["payload_json"], JobPosting),
    }


def list_job_postings(limit: int = 50) -> list[dict[str, Any]]:
    """List stored job postings without hydrating full JobPosting payloads."""
    records = list_job_posting_records(limit=limit)
    return [
        {
            "id": record["id"],
            "saved_at": record["saved_at"],
            "source": record["source"],
            "source_url": record["source_url"],
            "title": record["title"],
            "company_name": record["company_name"],
            "location": record["location"],
        }
        for record in records
    ]


def delete_job_posting(job_posting_id: int) -> bool:
    """Delete a stored job posting by database ID.

    Args:
        job_posting_id: Database identifier of the stored job posting.

    Returns:
        True when the record existed and was deleted, otherwise False.
    """
    return delete_job_posting_record(job_posting_id)


def save_match_result(
    match_result: MatchResult,
    *,
    candidate_profile_id: int | None = None,
    job_posting_id: int | None = None,
) -> dict[str, Any]:
    """Persist a MatchResult and optional links to stored profile and job records."""
    record = save_match_result_record(
        candidate_profile_id=candidate_profile_id,
        job_posting_id=job_posting_id,
        overall_score=match_result.overall_score,
        fit_classification=match_result.fit_classification,
        recommendation=match_result.recommendation,
        payload_json=_serialize_model(match_result),
    )
    return {
        "id": record["id"],
        "saved_at": record["saved_at"],
        "candidate_profile_id": record["candidate_profile_id"],
        "job_posting_id": record["job_posting_id"],
        "overall_score": record["overall_score"],
        "fit_classification": record["fit_classification"],
        "recommendation": record["recommendation"],
        "payload": match_result,
    }


def get_match_result(match_result_id: int) -> dict[str, Any] | None:
    """Load a stored match result by database ID."""
    record = get_match_result_record(match_result_id)
    if record is None:
        return None
    return {
        "id": record["id"],
        "saved_at": record["saved_at"],
        "candidate_profile_id": record["candidate_profile_id"],
        "job_posting_id": record["job_posting_id"],
        "overall_score": record["overall_score"],
        "fit_classification": record["fit_classification"],
        "recommendation": record["recommendation"],
        "payload": _deserialize_model(record["payload_json"], MatchResult),
    }


def list_match_results(limit: int = 50) -> list[dict[str, Any]]:
    """List stored match results without loading the nested MatchResult payload."""
    records = list_match_result_records(limit=limit)
    return [
        {
            "id": record["id"],
            "saved_at": record["saved_at"],
            "candidate_profile_id": record["candidate_profile_id"],
            "job_posting_id": record["job_posting_id"],
            "overall_score": record["overall_score"],
            "fit_classification": record["fit_classification"],
            "recommendation": record["recommendation"],
        }
        for record in records
    ]


def save_resume_draft(
    *,
    candidate_profile_id: int | None = None,
    job_posting_id: int | None = None,
    match_result_id: int | None = None,
    target_job_title: str | None = None,
    target_company_name: str | None = None,
    generation_mode: str,
    base_resume_artifacts: dict[str, Any],
) -> dict[str, Any]:
    """Persist one generated resume-draft artifact bundle."""
    record = save_resume_draft_record(
        candidate_profile_id=candidate_profile_id,
        job_posting_id=job_posting_id,
        match_result_id=match_result_id,
        target_job_title=target_job_title,
        target_company_name=target_company_name,
        generation_mode=generation_mode,
        base_resume_artifacts_json=_serialize_json_like(base_resume_artifacts),
    )
    return {
        "id": record["id"],
        "saved_at": record["saved_at"],
        "updated_at": record["updated_at"],
        "candidate_profile_id": record["candidate_profile_id"],
        "job_posting_id": record["job_posting_id"],
        "match_result_id": record["match_result_id"],
        "target_job_title": record["target_job_title"],
        "target_company_name": record["target_company_name"],
        "generation_mode": record["generation_mode"],
        "has_refined_version": record["has_refined_version"],
        "base_resume_artifacts": base_resume_artifacts,
        "refined_resume_artifacts": None,
    }


def update_resume_draft_refinement(
    draft_id: int,
    *,
    refined_resume_artifacts: dict[str, Any],
) -> dict[str, Any] | None:
    """Persist the refined artifact bundle for one existing resume draft."""
    record = update_resume_draft_record_refinement(
        draft_id,
        refined_resume_artifacts_json=_serialize_json_like(refined_resume_artifacts),
    )
    if record is None:
        return None
    return {
        "id": record["id"],
        "saved_at": record["saved_at"],
        "updated_at": record["updated_at"],
        "candidate_profile_id": record["candidate_profile_id"],
        "job_posting_id": record["job_posting_id"],
        "match_result_id": record["match_result_id"],
        "target_job_title": record["target_job_title"],
        "target_company_name": record["target_company_name"],
        "generation_mode": record["generation_mode"],
        "has_refined_version": record["has_refined_version"],
        "base_resume_artifacts": _deserialize_json_like(record["base_resume_artifacts_json"]),
        "refined_resume_artifacts": refined_resume_artifacts,
    }


def get_resume_draft(draft_id: int) -> dict[str, Any] | None:
    """Load one stored resume draft bundle by database ID."""
    record = get_resume_draft_record(draft_id)
    if record is None:
        return None
    return _deserialize_resume_draft_record(record)


def list_resume_drafts(
    *,
    limit: int = 50,
    candidate_profile_id: int | None = None,
    job_posting_id: int | None = None,
) -> list[dict[str, Any]]:
    """List stored resume drafts without hydrating nested JSON payloads."""
    records = list_resume_draft_records(
        limit=limit,
        candidate_profile_id=candidate_profile_id,
        job_posting_id=job_posting_id,
    )
    return [
        {
            "id": record["id"],
            "saved_at": record["saved_at"],
            "updated_at": record["updated_at"],
            "candidate_profile_id": record["candidate_profile_id"],
            "job_posting_id": record["job_posting_id"],
            "match_result_id": record["match_result_id"],
            "target_job_title": record["target_job_title"],
            "target_company_name": record["target_company_name"],
            "generation_mode": record["generation_mode"],
            "has_refined_version": record["has_refined_version"],
        }
        for record in records
    ]


def _serialize_model(model: Any) -> str:
    """Serialize a Pydantic model to JSON text for SQLite storage."""
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False)


def _deserialize_model(payload_json: str, model_type: type[Any]) -> Any:
    """Deserialize stored JSON text back into the requested Pydantic model."""
    return model_type.model_validate(json.loads(payload_json))


def _serialize_json_like(payload: Any) -> str:
    """Serialize a JSON-like dict payload to SQLite text."""
    return json.dumps(payload, ensure_ascii=False)


def _deserialize_json_like(payload_json: str | None) -> Any:
    """Deserialize stored JSON-like text payloads."""
    if payload_json is None:
        return None
    return json.loads(payload_json)


def _deserialize_resume_draft_record(record: dict[str, Any]) -> dict[str, Any]:
    """Hydrate one stored resume-draft record back into nested JSON-like payloads."""
    return {
        "id": record["id"],
        "saved_at": record["saved_at"],
        "updated_at": record["updated_at"],
        "candidate_profile_id": record["candidate_profile_id"],
        "job_posting_id": record["job_posting_id"],
        "match_result_id": record["match_result_id"],
        "target_job_title": record["target_job_title"],
        "target_company_name": record["target_company_name"],
        "generation_mode": record["generation_mode"],
        "has_refined_version": record["has_refined_version"],
        "base_resume_artifacts": _deserialize_json_like(record["base_resume_artifacts_json"]),
        "refined_resume_artifacts": _deserialize_json_like(record["refined_resume_artifacts_json"]),
    }
