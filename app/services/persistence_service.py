from __future__ import annotations

import json
from typing import Any

from app.db.repositories import (
    get_candidate_profile_record,
    get_job_posting_record,
    get_match_result_record,
    list_candidate_profile_records,
    list_job_posting_records,
    list_match_result_records,
    save_candidate_profile_record,
    save_job_posting_record,
    save_match_result_record,
)
from app.models.candidate import CandidateProfile
from app.models.job import JobPosting
from app.models.match import MatchResult


def save_candidate_profile(profile: CandidateProfile) -> dict[str, Any]:
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


def get_candidate_profile(profile_id: int) -> dict[str, Any] | None:
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


def save_job_posting(job_posting: JobPosting, *, source_url: str | None = None) -> dict[str, Any]:
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


def save_match_result(
    match_result: MatchResult,
    *,
    candidate_profile_id: int | None = None,
    job_posting_id: int | None = None,
) -> dict[str, Any]:
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


def _serialize_model(model: Any) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False)


def _deserialize_model(payload_json: str, model_type: type[Any]) -> Any:
    return model_type.model_validate(json.loads(payload_json))
