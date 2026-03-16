"""Optional Playwright fallback for pages that standard HTTP fetch cannot read well."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

_DEFAULT_TIMEOUT_SECONDS = 25.0
_DEFAULT_WAIT_AFTER_LOAD_MS = 1500
_DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_TIMEOUT_ENV = "JOB_URL_BROWSER_FALLBACK_TIMEOUT_SECONDS"
_WAIT_AFTER_LOAD_ENV = "JOB_URL_BROWSER_FALLBACK_WAIT_MS"


class BrowserPageFetchError(Exception):
    """Raised when the browser-based fallback cannot fetch a page."""
    pass


@dataclass(slots=True)
class BrowserFetchedPage:
    """Browser-fetched HTML payload returned by the fallback fetcher."""
    requested_url: str
    final_url: str
    raw_html: str


def fetch_page_with_browser(url: str) -> BrowserFetchedPage:
    """Fetch a page with Playwright and return rendered HTML.

    Args:
        url: Public page URL to open in the browser fallback.

    Returns:
        BrowserFetchedPage with the final URL and rendered HTML.
    """
    load_dotenv()

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserPageFetchError(
            "Playwright is not installed. Install it and run 'playwright install chromium'."
        ) from exc

    timeout_ms = int(_read_float_env(_TIMEOUT_ENV, default=_DEFAULT_TIMEOUT_SECONDS) * 1000)
    wait_after_load_ms = _read_int_env(_WAIT_AFTER_LOAD_ENV, default=_DEFAULT_WAIT_AFTER_LOAD_MS)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=_DEFAULT_BROWSER_USER_AGENT,
                    locale="en-US",
                )
                try:
                    page = context.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    try:
                        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5000))
                    except PlaywrightTimeoutError:
                        pass
                    page.wait_for_timeout(wait_after_load_ms)
                    return BrowserFetchedPage(
                        requested_url=url,
                        final_url=page.url,
                        raw_html=page.content(),
                    )
                finally:
                    context.close()
            finally:
                browser.close()
    except BrowserPageFetchError:
        raise
    except Exception as exc:
        raise BrowserPageFetchError(str(exc)) from exc


def _read_float_env(env_name: str, *, default: float) -> float:
    """Read a float env var and fall back to the provided default on errors."""
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except ValueError:
        return default


def _read_int_env(env_name: str, *, default: int) -> int:
    """Read an integer env var and fall back to the provided default on errors."""
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default

    try:
        return int(raw_value)
    except ValueError:
        return default
