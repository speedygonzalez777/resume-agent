from pathlib import Path

import pytest

from app.services.typst_pdf_layout_analysis_service import analyze_typst_pdf_layout

fitz = pytest.importorskip("fitz")


def _write_pdf(path: Path, *, page_count: int = 1, include_footer: bool = True) -> None:
    document = fitz.open()
    for page_index in range(page_count):
        page = document.new_page(width=595.28, height=841.89)
        page.insert_text((48, 72), f"SUMMARY page {page_index + 1}", fontsize=10.6)
        page.insert_text((48, 120), "Experience bullet with concrete content.", fontsize=10.6)
        if include_footer:
            page.insert_text(
                (48, 782),
                "I consent to the processing of my personal data in accordance with GDPR 2016/679.",
                fontsize=8,
            )
    document.save(path)
    document.close()


def test_typst_pdf_layout_analysis_counts_pages_and_footer(tmp_path) -> None:
    pdf_path = tmp_path / "one-page.pdf"
    _write_pdf(pdf_path)

    metrics = analyze_typst_pdf_layout(pdf_path)

    assert metrics.page_count == 1
    assert metrics.is_single_page is True
    assert metrics.footer_detected is True
    assert metrics.footer_top_y is not None
    assert metrics.free_space_before_footer_pt is not None
    assert metrics.underfilled is True
    assert metrics.overfilled is False
    assert any("underfilled" in warning.lower() for warning in metrics.analysis_warnings)


def test_typst_pdf_layout_analysis_flags_multiple_pages_as_overfilled(tmp_path) -> None:
    pdf_path = tmp_path / "two-page.pdf"
    _write_pdf(pdf_path, page_count=2)

    metrics = analyze_typst_pdf_layout(pdf_path)

    assert metrics.page_count == 2
    assert metrics.is_single_page is False
    assert metrics.overfilled is True
    assert "Rendered PDF has more than one page." in metrics.analysis_warnings


def test_typst_pdf_layout_analysis_warns_when_footer_missing(tmp_path) -> None:
    pdf_path = tmp_path / "no-footer.pdf"
    _write_pdf(pdf_path, include_footer=False)

    metrics = analyze_typst_pdf_layout(pdf_path)

    assert metrics.footer_detected is False
    assert any("footer" in warning.lower() for warning in metrics.analysis_warnings)
