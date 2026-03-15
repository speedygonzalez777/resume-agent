from __future__ import annotations

from app.models.job import JobPosting, Requirement
from app.services.job_page_fetch_service import FetchedJobPage
from app.services.openai_job_parser_service import parse_job_posting_with_openai


def test_parse_job_posting_with_openai_omits_sampling_params_by_default(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_job_posting = _build_job_posting()

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_job_posting})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.delenv("OPENAI_JOB_PARSER_TEMPERATURE", raising=False)
    monkeypatch.delenv("OPENAI_JOB_PARSER_TOP_P", raising=False)
    monkeypatch.setenv("OPENAI_JOB_PARSER_MODEL", "gpt-5-mini")
    monkeypatch.setattr("app.services.openai_job_parser_service.OpenAI", FakeOpenAI)

    result = parse_job_posting_with_openai(_build_fetched_page())

    assert result == expected_job_posting
    assert captured_kwargs["model"] == "gpt-5-mini"
    assert "temperature" not in captured_kwargs
    assert "top_p" not in captured_kwargs


def test_parse_job_posting_with_openai_ignores_sampling_params_for_unsupported_model(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_job_posting = _build_job_posting()

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_job_posting})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_JOB_PARSER_MODEL", "gpt-5-mini")
    monkeypatch.setenv("OPENAI_JOB_PARSER_TEMPERATURE", "0.2")
    monkeypatch.setenv("OPENAI_JOB_PARSER_TOP_P", "0.8")
    monkeypatch.setattr("app.services.openai_job_parser_service.OpenAI", FakeOpenAI)

    result = parse_job_posting_with_openai(_build_fetched_page())

    assert result == expected_job_posting
    assert "temperature" not in captured_kwargs
    assert "top_p" not in captured_kwargs


def test_parse_job_posting_with_openai_includes_sampling_params_for_supported_model(
    monkeypatch,
) -> None:
    captured_kwargs: dict[str, object] = {}
    expected_job_posting = _build_job_posting()

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.responses = self

        def parse(self, **kwargs):
            captured_kwargs.update(kwargs)
            return type("FakeResponse", (), {"output_parsed": expected_job_posting})()

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_JOB_PARSER_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_JOB_PARSER_TEMPERATURE", "0.2")
    monkeypatch.setenv("OPENAI_JOB_PARSER_TOP_P", "0.8")
    monkeypatch.setattr("app.services.openai_job_parser_service.OpenAI", FakeOpenAI)

    result = parse_job_posting_with_openai(_build_fetched_page())

    assert result == expected_job_posting
    assert captured_kwargs["temperature"] == 0.2
    assert captured_kwargs["top_p"] == 0.8


def _build_fetched_page() -> FetchedJobPage:
    return FetchedJobPage(
        requested_url="https://justjoin.it/job-offer/example",
        final_url="https://justjoin.it/job-offer/example",
        source_hint="justjoin",
        page_title="Junior Python Developer",
        extracted_lines=[
            "Junior Python Developer",
            "Example Tech",
            "Build backend APIs",
        ],
        cleaned_text="Junior Python Developer\nExample Tech\nBuild backend APIs",
        raw_html="<html><title>Junior Python Developer</title></html>",
    )


def _build_job_posting() -> JobPosting:
    return JobPosting(
        source="justjoin",
        title="Junior Python Developer",
        company_name="Example Tech",
        location="Gdansk, Poland",
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
