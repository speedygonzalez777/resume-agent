"""Orchestrate the URL-first flow from fetch to validated JobPosting."""

from __future__ import annotations

from app.models.job import JobPosting
from app.services.job_page_fetch_service import fetch_job_page
from app.services.job_parse_errors import ParsedJobPostingIncompleteError
from app.services.openai_job_parser_service import parse_job_posting_with_openai


def parse_job_posting_from_url(url: str) -> JobPosting:
    """Fetch, parse and validate a job posting from a public URL.

    Args:
        url: Public URL pointing to a single job posting.

    Returns:
        Normalized and validated JobPosting parsed from the fetched page.
    """
    fetched_page = fetch_job_page(url)
    parsed_job_posting = parse_job_posting_with_openai(fetched_page)

    normalized_job_posting = parsed_job_posting.model_copy(
        update={
            "source": fetched_page.source_hint or _normalize_str(parsed_job_posting.source) or "url",
            "title": _normalize_str(parsed_job_posting.title),
            "company_name": _normalize_str(parsed_job_posting.company_name),
            "location": _normalize_str(parsed_job_posting.location),
            "role_summary": _normalize_optional_str(parsed_job_posting.role_summary),
            "work_mode": _normalize_optional_str(parsed_job_posting.work_mode),
            "employment_type": _normalize_optional_str(parsed_job_posting.employment_type),
            "seniority_level": _normalize_optional_str(parsed_job_posting.seniority_level),
            "language_of_offer": _normalize_optional_str(parsed_job_posting.language_of_offer),
        }
    )

    _validate_parsed_job_posting(normalized_job_posting)
    return normalized_job_posting


def _validate_parsed_job_posting(job_posting: JobPosting) -> None:
    """Reject parsed results that miss critical JobPosting fields."""
    missing_elements: list[str] = []

    if not job_posting.title:
        missing_elements.append("title")
    if not job_posting.company_name:
        missing_elements.append("company_name")
    if not job_posting.requirements and not job_posting.responsibilities:
        missing_elements.append("requirements or responsibilities")

    if missing_elements:
        raise ParsedJobPostingIncompleteError(
            "Parsed JobPosting is incomplete and was rejected.",
            details={"missing_elements": missing_elements},
        )


def _normalize_str(value: str) -> str:
    """Collapse whitespace and trim a required string field."""
    return " ".join(value.split()).strip()


def _normalize_optional_str(value: str | None) -> str | None:
    """Normalize an optional string field and preserve None when empty."""
    if value is None:
        return None

    normalized = _normalize_str(value)
    return normalized or None
