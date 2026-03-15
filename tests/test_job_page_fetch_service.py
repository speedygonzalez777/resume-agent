import httpx
import pytest

from app.services.browser_page_fetch_service import BrowserPageFetchError
from app.services.job_page_fetch_service import fetch_job_page
from app.services.job_parse_errors import JobPageContentTooPoorError, JobPageFetchFailedError


class _FakeHttpxClient:
    def __init__(self, response_or_error: httpx.Response | Exception) -> None:
        self._response_or_error = response_or_error

    def __enter__(self) -> "_FakeHttpxClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def get(self, url: str) -> httpx.Response:
        if isinstance(self._response_or_error, Exception):
            raise self._response_or_error
        return self._response_or_error


def test_fetch_job_page_returns_usable_standard_http_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_http_client(
        monkeypatch,
        _build_html_response("https://jobs.example.com/python-role", _build_job_offer_html("Python Developer")),
    )
    monkeypatch.setenv("JOB_URL_BROWSER_FALLBACK_ENABLED", "false")
    monkeypatch.delenv("JOB_URL_BROWSER_FALLBACK_DOMAINS", raising=False)
    monkeypatch.setattr(
        "app.services.job_page_fetch_service.fetch_page_with_browser",
        lambda url: (_ for _ in ()).throw(AssertionError("Browser fallback should not be used.")),
    )

    fetched_page = fetch_job_page("https://jobs.example.com/python-role")

    assert fetched_page.final_url == "https://jobs.example.com/python-role"
    assert fetched_page.source_hint == "example"
    assert "Python Developer" in fetched_page.cleaned_text


def test_fetch_job_page_uses_browser_fallback_for_blocked_or_antibot_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser_calls: list[str] = []

    def fake_browser_fetch(url: str) -> object:
        browser_calls.append(url)
        return _BrowserPageStub(url, _build_job_offer_html("Python Developer from Browser"))

    monkeypatch.setenv("JOB_URL_BROWSER_FALLBACK_ENABLED", "true")
    monkeypatch.delenv("JOB_URL_BROWSER_FALLBACK_DOMAINS", raising=False)
    monkeypatch.setattr("app.services.job_page_fetch_service.fetch_page_with_browser", fake_browser_fetch)

    _patch_http_client(
        monkeypatch,
        _build_html_response(
            "https://www.pracuj.pl/praca/python-role",
            "<html><body><h1>Forbidden</h1><p>Blocked by target site.</p></body></html>",
            status_code=403,
        ),
    )
    blocked_result = fetch_job_page("https://www.pracuj.pl/praca/python-role")

    _patch_http_client(
        monkeypatch,
        _build_html_response(
            "https://www.pracuj.pl/praca/python-role",
            (
                "<html><head><title>Attention Required</title></head>"
                "<body><h1>Verify you are human</h1><p>Please complete the CAPTCHA.</p></body></html>"
            ),
        ),
    )
    antibot_result = fetch_job_page("https://www.pracuj.pl/praca/python-role")

    assert browser_calls == [
        "https://www.pracuj.pl/praca/python-role",
        "https://www.pracuj.pl/praca/python-role",
    ]
    assert "Python Developer from Browser" in blocked_result.cleaned_text
    assert "Python Developer from Browser" in antibot_result.cleaned_text


def test_fetch_job_page_returns_fetch_failed_when_browser_fallback_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_http_client(
        monkeypatch,
        _build_html_response(
            "https://www.pracuj.pl/praca/python-role",
            "<html><body><h1>Forbidden</h1><p>Blocked by target site.</p></body></html>",
            status_code=403,
        ),
    )
    monkeypatch.setenv("JOB_URL_BROWSER_FALLBACK_ENABLED", "true")
    monkeypatch.delenv("JOB_URL_BROWSER_FALLBACK_DOMAINS", raising=False)
    monkeypatch.setattr(
        "app.services.job_page_fetch_service.fetch_page_with_browser",
        lambda url: (_ for _ in ()).throw(BrowserPageFetchError("Playwright is not installed.")),
    )

    with pytest.raises(JobPageFetchFailedError) as exc_info:
        fetch_job_page("https://www.pracuj.pl/praca/python-role")

    assert exc_info.value.details["fetch_method_attempted"] == "both"
    assert exc_info.value.details["blocked_by_target_site"] is True
    assert exc_info.value.details["http_status"] == 403
    assert "browser_fallback_failed" in exc_info.value.details["reason"]


def test_fetch_job_page_returns_page_content_too_poor_when_browser_content_is_still_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_http_client(
        monkeypatch,
        _build_html_response(
            "https://www.pracuj.pl/praca/python-role",
            '<html><body><div id="root"></div><script src="/assets/app.js"></script></body></html>',
        ),
    )
    monkeypatch.setenv("JOB_URL_BROWSER_FALLBACK_ENABLED", "true")
    monkeypatch.delenv("JOB_URL_BROWSER_FALLBACK_DOMAINS", raising=False)
    monkeypatch.setattr(
        "app.services.job_page_fetch_service.fetch_page_with_browser",
        lambda url: _BrowserPageStub(url, "<html><body><h1>Python role</h1><p>Remote</p></body></html>"),
    )

    with pytest.raises(JobPageContentTooPoorError) as exc_info:
        fetch_job_page("https://www.pracuj.pl/praca/python-role")

    assert exc_info.value.details["fetch_method_attempted"] == "both"
    assert exc_info.value.details["reason"].startswith("standard_http: spa_shell_or_unrendered_dynamic_page")
    assert exc_info.value.details["content_lines"] < 6


class _BrowserPageStub:
    def __init__(self, url: str, raw_html: str) -> None:
        self.requested_url = url
        self.final_url = url
        self.raw_html = raw_html


def _patch_http_client(
    monkeypatch: pytest.MonkeyPatch,
    response_or_error: httpx.Response | Exception,
) -> None:
    monkeypatch.setattr(
        "app.services.job_page_fetch_service.httpx.Client",
        lambda *args, **kwargs: _FakeHttpxClient(response_or_error),
    )


def _build_html_response(url: str, html: str, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        headers={"content-type": "text/html; charset=utf-8"},
        text=html,
        request=httpx.Request("GET", url),
    )


def _build_job_offer_html(title: str) -> str:
    return f"""
    <html>
      <head><title>{title}</title></head>
      <body>
        <main>
          <h1>{title}</h1>
          <p>Example Tech</p>
          <p>Remote work available from Warsaw.</p>
          <section>
            <h2>Responsibilities</h2>
            <ul>
              <li>Build backend services in Python and FastAPI.</li>
              <li>Work with APIs, integrations and background jobs.</li>
              <li>Collaborate with product and engineering teams.</li>
            </ul>
          </section>
          <section>
            <h2>Requirements</h2>
            <ul>
              <li>Commercial experience with Python and web services.</li>
              <li>Knowledge of REST APIs, SQL and Git.</li>
              <li>Ability to communicate clearly in English.</li>
            </ul>
          </section>
        </main>
      </body>
    </html>
    """
