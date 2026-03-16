"""Domain-level exceptions used by the job posting parsing flow."""

from __future__ import annotations

from typing import Any


class JobParseError(Exception):
    """Base error for the URL-first job parsing flow."""
    error_code = "job_parse_error"
    status_code = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        """Store a machine-readable error payload alongside the message."""
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_http_detail(self) -> dict[str, Any]:
        """Convert the exception into the HTTP error payload used by routers."""
        detail: dict[str, Any] = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.details:
            detail["details"] = self.details
        return detail


class JobPageFetchFailedError(JobParseError):
    """Raised when the backend cannot fetch a job page at all."""
    error_code = "fetch_failed"
    status_code = 502


class JobPageContentTooPoorError(JobParseError):
    """Raised when fetched content is too poor to parse as a real offer."""
    error_code = "page_content_too_poor"
    status_code = 422


class AIJobParsingFailedError(JobParseError):
    """Raised when OpenAI fails to turn fetched content into JobPosting."""
    error_code = "ai_parsing_failed"
    status_code = 502


class ParsedJobPostingIncompleteError(JobParseError):
    """Raised when structured parsing succeeds but the result is incomplete."""
    error_code = "parsed_result_incomplete"
    status_code = 422
