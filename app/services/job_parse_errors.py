from __future__ import annotations

from typing import Any


class JobParseError(Exception):
    error_code = "job_parse_error"
    status_code = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_http_detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.details:
            detail["details"] = self.details
        return detail


class JobPageFetchFailedError(JobParseError):
    error_code = "fetch_failed"
    status_code = 502


class JobPageContentTooPoorError(JobParseError):
    error_code = "page_content_too_poor"
    status_code = 422


class AIJobParsingFailedError(JobParseError):
    error_code = "ai_parsing_failed"
    status_code = 502


class ParsedJobPostingIncompleteError(JobParseError):
    error_code = "parsed_result_incomplete"
    status_code = 422
