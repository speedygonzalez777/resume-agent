from __future__ import annotations

import os
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from app.services.browser_page_fetch_service import BrowserPageFetchError, fetch_page_with_browser
from app.services.job_parse_errors import JobPageContentTooPoorError, JobPageFetchFailedError

_FETCH_TIMEOUT_SECONDS = 15.0
_MIN_CONTENT_LINES = 6
_MIN_CONTENT_CHARS = 300
_MAX_SECTION_LINES = 120
_STANDARD_HTTP_FETCH_METHOD = "standard_http"
_BROWSER_FALLBACK_FETCH_METHOD = "browser_fallback"
_BROWSER_FALLBACK_ENABLED_ENV = "JOB_URL_BROWSER_FALLBACK_ENABLED"
_BROWSER_FALLBACK_DOMAINS_ENV = "JOB_URL_BROWSER_FALLBACK_DOMAINS"
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}
_BLOCKED_STATUS_CODES = {403, 429}
_BLOCKED_PAGE_MARKERS = (
    "access denied",
    "attention required",
    "captcha",
    "cf-browser-verification",
    "cf-chl",
    "enable javascript and cookies to continue",
    "press and hold",
    "security check",
    "sorry, you have been blocked",
    "unusual traffic",
    "verify you are human",
)
_SPA_SHELL_MARKERS = (
    "application error: a client-side exception has occurred",
    "enable javascript to run this app",
    'id="__next"></div>',
    'id="app"></div>',
    'id="root"></div>',
    "please enable javascript",
    "you need to enable javascript",
)


@dataclass(slots=True)
class FetchedJobPage:
    requested_url: str
    final_url: str
    source_hint: str
    page_title: str
    extracted_lines: list[str]
    cleaned_text: str
    raw_html: str

    def build_ai_input(self) -> str:
        extracted_lines_preview = "\n".join(f"- {line}" for line in self.extracted_lines[:_MAX_SECTION_LINES])
        return (
            f"Requested URL: {self.requested_url}\n"
            f"Final URL: {self.final_url}\n"
            f"Source hint: {self.source_hint}\n"
            f"HTML title: {self.page_title}\n\n"
            f"Extracted lines:\n{extracted_lines_preview}\n\n"
            f"Cleaned page text:\n{self.cleaned_text}"
        )


@dataclass(slots=True)
class _FetchAttempt:
    requested_url: str
    final_url: str | None
    raw_html: str
    page_title: str
    extracted_lines: list[str]
    cleaned_text: str
    http_status: int | None
    fetch_method: str
    error_code: str | None
    reason: str
    blocked_by_target_site: bool


class _VisibleTextHTMLParser(HTMLParser):
    _BLOCK_TAGS = {
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "section",
        "table",
        "tr",
        "td",
        "th",
        "ul",
    }
    _SKIP_TAGS = {"script", "style", "noscript", "svg", "iframe"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page_title = ""
        self._tag_stack: list[str] = []
        self._skip_tag_stack: list[str] = []
        self._current_tokens: list[str] = []
        self._lines: list[str] = []

    @property
    def lines(self) -> list[str]:
        return self._lines

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self._SKIP_TAGS:
            self._skip_tag_stack.append(tag)
            return
        if self._skip_tag_stack:
            return
        if tag in self._BLOCK_TAGS:
            self._flush_current_tokens()
        self._tag_stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_tag_stack:
            if tag == self._skip_tag_stack[-1]:
                self._skip_tag_stack.pop()
            return
        if tag == "title":
            title_text = self._consume_current_tokens()
            if title_text and not self.page_title:
                self.page_title = title_text
            self._pop_tag(tag)
            return
        if tag in self._BLOCK_TAGS:
            self._flush_current_tokens()
        self._pop_tag(tag)

    def handle_data(self, data: str) -> None:
        if self._skip_tag_stack:
            return
        cleaned = " ".join(data.split())
        if cleaned:
            self._current_tokens.append(cleaned)

    def close(self) -> None:
        self._flush_current_tokens()
        super().close()

    def _consume_current_tokens(self) -> str:
        text = " ".join(self._current_tokens).strip()
        self._current_tokens = []
        return text

    def _flush_current_tokens(self) -> None:
        text = self._consume_current_tokens()
        if text:
            self._lines.append(text)

    def _pop_tag(self, tag: str) -> None:
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()


def derive_source_from_url(url: str) -> str:
    hostname = _hostname_from_url(url)
    if hostname.startswith("www."):
        hostname = hostname[4:]
    if not hostname:
        return "url"

    parts = [part for part in hostname.split(".") if part]
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "gov"}:
        return parts[-3]
    if len(parts) >= 2:
        return parts[-2]
    return parts[0]


def fetch_job_page(url: str) -> FetchedJobPage:
    load_dotenv()

    standard_attempt = _fetch_with_standard_http(url)
    if standard_attempt.error_code is None:
        return _to_fetched_job_page(standard_attempt)

    browser_attempt: _FetchAttempt | None = None
    if _should_try_browser_fallback(url, standard_attempt):
        browser_attempt = _fetch_with_browser_fallback(url)
        if browser_attempt.error_code is None:
            return _to_fetched_job_page(browser_attempt)

    _raise_attempt_error(url, standard_attempt, browser_attempt)
    raise AssertionError("Unreachable")


def _fetch_with_standard_http(url: str) -> _FetchAttempt:
    try:
        with httpx.Client(
            follow_redirects=True,
            headers=_DEFAULT_HEADERS,
            timeout=httpx.Timeout(_FETCH_TIMEOUT_SECONDS, connect=10.0),
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        return _failed_attempt(
            url=url,
            final_url=None,
            http_status=None,
            fetch_method=_STANDARD_HTTP_FETCH_METHOD,
            reason=f"http_request_failed: {exc}",
        )

    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type and "text/plain" not in content_type:
        return _failed_attempt(
            url=url,
            final_url=str(response.url),
            http_status=response.status_code,
            fetch_method=_STANDARD_HTTP_FETCH_METHOD,
            reason=f"unsupported_content_type: {content_type or 'unknown'}",
        )

    return _assess_attempt(
        url=url,
        final_url=str(response.url),
        raw_html=response.text,
        http_status=response.status_code,
        fetch_method=_STANDARD_HTTP_FETCH_METHOD,
    )


def _fetch_with_browser_fallback(url: str) -> _FetchAttempt:
    try:
        browser_page = fetch_page_with_browser(url)
    except BrowserPageFetchError as exc:
        return _failed_attempt(
            url=url,
            final_url=None,
            http_status=None,
            fetch_method=_BROWSER_FALLBACK_FETCH_METHOD,
            reason=f"browser_fallback_failed: {exc}",
        )

    return _assess_attempt(
        url=url,
        final_url=browser_page.final_url,
        raw_html=browser_page.raw_html,
        http_status=None,
        fetch_method=_BROWSER_FALLBACK_FETCH_METHOD,
    )


def _assess_attempt(
    *,
    url: str,
    final_url: str,
    raw_html: str,
    http_status: int | None,
    fetch_method: str,
) -> _FetchAttempt:
    page_title, extracted_lines, cleaned_text = _extract_page_content(raw_html)
    blocked_by_target_site, fetch_failure_reason = _detect_fetch_failure(
        http_status=http_status,
        raw_html=raw_html,
        page_title=page_title,
        cleaned_text=cleaned_text,
    )
    if fetch_failure_reason:
        return _FetchAttempt(
            requested_url=url,
            final_url=final_url,
            raw_html=raw_html,
            page_title=page_title,
            extracted_lines=extracted_lines,
            cleaned_text=cleaned_text,
            http_status=http_status,
            fetch_method=fetch_method,
            error_code="fetch_failed",
            reason=fetch_failure_reason,
            blocked_by_target_site=blocked_by_target_site,
        )

    poor_content_reason = _detect_poor_content_reason(raw_html, extracted_lines, cleaned_text)
    if poor_content_reason:
        return _FetchAttempt(
            requested_url=url,
            final_url=final_url,
            raw_html=raw_html,
            page_title=page_title,
            extracted_lines=extracted_lines,
            cleaned_text=cleaned_text,
            http_status=http_status,
            fetch_method=fetch_method,
            error_code="page_content_too_poor",
            reason=poor_content_reason,
            blocked_by_target_site=False,
        )

    return _FetchAttempt(
        requested_url=url,
        final_url=final_url,
        raw_html=raw_html,
        page_title=page_title,
        extracted_lines=extracted_lines,
        cleaned_text=cleaned_text,
        http_status=http_status,
        fetch_method=fetch_method,
        error_code=None,
        reason="ok",
        blocked_by_target_site=False,
    )


def _extract_page_content(raw_html: str) -> tuple[str, list[str], str]:
    parser = _VisibleTextHTMLParser()
    parser.feed(raw_html)
    parser.close()
    extracted_lines = _normalize_lines(parser.lines)
    return parser.page_title, extracted_lines, "\n".join(extracted_lines)


def _detect_fetch_failure(
    *,
    http_status: int | None,
    raw_html: str,
    page_title: str,
    cleaned_text: str,
) -> tuple[bool, str | None]:
    if http_status in _BLOCKED_STATUS_CODES:
        return True, f"http_status_{http_status}"
    if http_status is not None and http_status >= 400:
        return False, f"http_status_{http_status}"

    scan_blob = "\n".join(part for part in (page_title, cleaned_text[:4000], raw_html[:4000]) if part).lower()
    if any(marker in scan_blob for marker in _BLOCKED_PAGE_MARKERS):
        return True, "anti_bot_or_blocked_page"
    return False, None


def _detect_poor_content_reason(raw_html: str, extracted_lines: list[str], cleaned_text: str) -> str | None:
    is_too_short = len(extracted_lines) < _MIN_CONTENT_LINES or len(cleaned_text) < _MIN_CONTENT_CHARS
    if is_too_short:
        scan_blob = "\n".join((cleaned_text[:2000], raw_html[:4000])).lower()
        if any(marker in scan_blob for marker in _SPA_SHELL_MARKERS):
            return "spa_shell_or_unrendered_dynamic_page"
    if not raw_html.strip():
        return "empty_page_content"
    if is_too_short:
        return "page_content_too_poor"
    return None


def _normalize_lines(lines: Iterable[str]) -> list[str]:
    normalized_lines: list[str] = []
    seen_lines: set[str] = set()
    for line in lines:
        normalized = " ".join(line.split()).strip(" -\t\r\n")
        if len(normalized) < 2 or sum(character.isalpha() for character in normalized) < 2:
            continue
        normalized_key = normalized.lower()
        if normalized_key in seen_lines:
            continue
        seen_lines.add(normalized_key)
        normalized_lines.append(normalized)
    return normalized_lines


def _to_fetched_job_page(attempt: _FetchAttempt) -> FetchedJobPage:
    final_url = attempt.final_url or attempt.requested_url
    return FetchedJobPage(
        requested_url=attempt.requested_url,
        final_url=final_url,
        source_hint=derive_source_from_url(final_url),
        page_title=attempt.page_title,
        extracted_lines=attempt.extracted_lines,
        cleaned_text=attempt.cleaned_text,
        raw_html=attempt.raw_html,
    )


def _failed_attempt(
    *,
    url: str,
    final_url: str | None,
    http_status: int | None,
    fetch_method: str,
    reason: str,
) -> _FetchAttempt:
    return _FetchAttempt(
        requested_url=url,
        final_url=final_url,
        raw_html="",
        page_title="",
        extracted_lines=[],
        cleaned_text="",
        http_status=http_status,
        fetch_method=fetch_method,
        error_code="fetch_failed",
        reason=reason,
        blocked_by_target_site=http_status in _BLOCKED_STATUS_CODES,
    )


def _should_try_browser_fallback(url: str, attempt: _FetchAttempt) -> bool:
    if attempt.error_code is None or not _read_bool_env(_BROWSER_FALLBACK_ENABLED_ENV):
        return False

    allowed_domains = _read_csv_env(_BROWSER_FALLBACK_DOMAINS_ENV)
    if not allowed_domains:
        return True

    hostname = _hostname_from_url(attempt.final_url or url)
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains)


def _raise_attempt_error(
    requested_url: str,
    standard_attempt: _FetchAttempt,
    browser_attempt: _FetchAttempt | None,
) -> None:
    final_attempt = browser_attempt or standard_attempt
    details = {
        "url": requested_url,
        "final_url": final_attempt.final_url or standard_attempt.final_url or requested_url,
        "domain": _hostname_from_url(final_attempt.final_url or requested_url),
        "http_status": final_attempt.http_status
        if final_attempt.http_status is not None
        else standard_attempt.http_status,
        "blocked_by_target_site": standard_attempt.blocked_by_target_site
        or bool(browser_attempt and browser_attempt.blocked_by_target_site),
        "fetch_method_attempted": "both" if browser_attempt else standard_attempt.fetch_method,
        "reason": _combine_reason(standard_attempt, browser_attempt),
    }
    if final_attempt.error_code == "page_content_too_poor":
        details["content_lines"] = len(final_attempt.extracted_lines)
        details["content_chars"] = len(final_attempt.cleaned_text)
        raise JobPageContentTooPoorError(
            "Fetched page content is too poor to parse as a job posting.",
            details=details,
        )

    raise JobPageFetchFailedError(
        "Failed to fetch the job posting page.",
        details=details,
    )


def _combine_reason(standard_attempt: _FetchAttempt, browser_attempt: _FetchAttempt | None) -> str:
    if browser_attempt is None:
        return standard_attempt.reason
    return (
        f"{_STANDARD_HTTP_FETCH_METHOD}: {standard_attempt.reason}; "
        f"{_BROWSER_FALLBACK_FETCH_METHOD}: {browser_attempt.reason}"
    )


def _hostname_from_url(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _read_bool_env(env_name: str) -> bool:
    raw_value = os.getenv(env_name, "").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _read_csv_env(env_name: str) -> set[str]:
    raw_value = os.getenv(env_name, "")
    return {
        chunk.strip().lower().removeprefix("www.")
        for chunk in raw_value.split(",")
        if chunk.strip()
    }
