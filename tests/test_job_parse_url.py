import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.job import JobPosting, Requirement
from app.services.job_page_fetch_service import FetchedJobPage
from app.services.job_parse_errors import (
    AIJobParsingFailedError,
    JobPageContentTooPoorError,
    JobPageFetchFailedError,
    ParsedJobPostingIncompleteError,
)
from app.services.job_url_parse_service import parse_job_posting_from_url


def test_parse_job_url_returns_job_posting(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_job_posting = JobPosting(
        source="justjoin",
        title="Junior Python Developer",
        company_name="Example Tech",
        location="Example City, Poland",
        work_mode="hybrid",
        employment_type="b2b",
        seniority_level="junior",
        role_summary="Junior backend role focused on Python services.",
        responsibilities=[
            "Build and maintain backend APIs.",
            "Work with the team on new product features.",
        ],
        requirements=[
            Requirement(
                id="req_001",
                text="Commercial experience with Python.",
                category="experience",
                requirement_type="must_have",
                importance="high",
                extracted_keywords=["python"],
            )
        ],
        keywords=["python", "fastapi", "api"],
        language_of_offer="en",
    )

    def fake_parse_job_posting_from_url(url: str) -> JobPosting:
        assert url == "https://justjoin.it/job-offer/example"
        return expected_job_posting

    monkeypatch.setattr(
        "app.api.routes_job.parse_job_posting_from_url",
        fake_parse_job_posting_from_url,
    )

    client = TestClient(app)
    response = client.post("/job/parse-url", json={"url": "https://justjoin.it/job-offer/example"})

    assert response.status_code == 200
    assert response.json() == expected_job_posting.model_dump(mode="json")


@pytest.mark.parametrize(
    ("raised_error", "expected_status", "expected_error_code"),
    [
        (
            JobPageFetchFailedError("Failed to fetch the job posting page."),
            502,
            "fetch_failed",
        ),
        (
            JobPageContentTooPoorError("Fetched page content is too poor to parse as a job posting."),
            422,
            "page_content_too_poor",
        ),
        (
            AIJobParsingFailedError("OpenAI failed to parse the fetched job page into JobPosting."),
            502,
            "ai_parsing_failed",
        ),
        (
            ParsedJobPostingIncompleteError("Parsed JobPosting is incomplete and was rejected."),
            422,
            "parsed_result_incomplete",
        ),
    ],
)
def test_parse_job_url_returns_clear_error_responses(
    monkeypatch: pytest.MonkeyPatch,
    raised_error: Exception,
    expected_status: int,
    expected_error_code: str,
) -> None:
    def fake_parse_job_posting_from_url(url: str) -> JobPosting:
        raise raised_error

    monkeypatch.setattr(
        "app.api.routes_job.parse_job_posting_from_url",
        fake_parse_job_posting_from_url,
    )

    client = TestClient(app)
    response = client.post("/job/parse-url", json={"url": "https://example.com/job-offer"})

    assert response.status_code == expected_status
    assert response.json()["detail"]["error"] == expected_error_code


def test_parse_job_posting_from_url_uses_source_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    fetched_page = FetchedJobPage(
        requested_url="https://jobs.example.com/python-role",
        final_url="https://jobs.example.com/python-role",
        source_hint="example",
        page_title="Python role",
        extracted_lines=["Python role", "Work on APIs"],
        cleaned_text="Python role\nWork on APIs\nRequirements: Python",
        raw_html="<html><title>Python role</title></html>",
    )

    parsed_job_posting = JobPosting(
        source="manual",
        title="Python Developer",
        company_name="Example Company",
        location="Remote",
        work_mode="remote",
        employment_type="b2b",
        seniority_level="mid",
        role_summary="Backend work in Python.",
        responsibilities=["Build APIs."],
        requirements=[],
        keywords=["python"],
        language_of_offer="en",
    )

    monkeypatch.setattr("app.services.job_url_parse_service.fetch_job_page", lambda url: fetched_page)
    monkeypatch.setattr(
        "app.services.job_url_parse_service.parse_job_posting_with_openai",
        lambda page: parsed_job_posting,
    )

    result = parse_job_posting_from_url("https://jobs.example.com/python-role")

    assert result.source == "example"
    assert result.title == "Python Developer"


def test_parse_job_posting_from_url_rejects_incomplete_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetched_page = FetchedJobPage(
        requested_url="https://jobs.example.com/python-role",
        final_url="https://jobs.example.com/python-role",
        source_hint="example",
        page_title="Python role",
        extracted_lines=["Python role"],
        cleaned_text="Python role",
        raw_html="<html><title>Python role</title></html>",
    )

    incomplete_job_posting = JobPosting(
        source="manual",
        title="",
        company_name="",
        location="",
        work_mode=None,
        employment_type=None,
        seniority_level=None,
        role_summary=None,
        responsibilities=[],
        requirements=[],
        keywords=[],
        language_of_offer=None,
    )

    monkeypatch.setattr("app.services.job_url_parse_service.fetch_job_page", lambda url: fetched_page)
    monkeypatch.setattr(
        "app.services.job_url_parse_service.parse_job_posting_with_openai",
        lambda page: incomplete_job_posting,
    )

    with pytest.raises(ParsedJobPostingIncompleteError):
        parse_job_posting_from_url("https://jobs.example.com/python-role")
