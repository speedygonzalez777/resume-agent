"""Local PDF layout analysis for rendered Typst CV artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.typst import TypstPdfLayoutMetrics

_FOOTER_PHRASES = (
    "i consent",
    "gdpr",
    "wyrażam zgodę",
    "wyrazam zgode",
    "rodo",
    "2016/679",
)
_UNDERFILLED_FREE_SPACE_THRESHOLD_PT = 120.0
_UNDERFILLED_FILL_RATIO_THRESHOLD = 0.80
_FOOTER_OVERLAP_THRESHOLD_PT = 15.0
_BOTTOM_FOOTER_ZONE_RATIO = 0.82
_MAX_FOOTER_FONT_SIZE_PT = 8.5


class TypstPdfLayoutAnalysisError(Exception):
    """Raised when local PDF layout analysis cannot produce metrics."""


@dataclass(frozen=True)
class _TextBlock:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    max_font_size: float | None


def analyze_typst_pdf_layout(pdf_path: Path) -> TypstPdfLayoutMetrics:
    """Analyze one rendered PDF without OCR and return layout fill metrics."""

    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on environment packaging
        raise TypstPdfLayoutAnalysisError("PyMuPDF is not installed.") from exc

    try:
        document = fitz.open(pdf_path)
    except Exception as exc:  # pragma: no cover - PyMuPDF wraps parser failures
        raise TypstPdfLayoutAnalysisError(f"PDF could not be opened: {exc}") from exc

    try:
        page_count = int(document.page_count)
        if page_count <= 0:
            raise TypstPdfLayoutAnalysisError("PDF contains no pages.")

        first_page = document[0]
        page_rect = first_page.rect
        page_width_pt = float(page_rect.width)
        page_height_pt = float(page_rect.height)
        warnings: list[str] = []
        overfilled = page_count > 1
        if overfilled:
            warnings.append("Rendered PDF has more than one page.")

        blocks = _extract_text_blocks(first_page.get_text("dict"))
        if not blocks:
            warnings.append("No text blocks were detected on the first PDF page.")

        footer_blocks = [block for block in blocks if _looks_like_footer(block, page_height_pt)]
        footer_detected = bool(footer_blocks)
        if footer_detected:
            footer_top_y = min(block.y0 for block in footer_blocks)
        else:
            footer_top_y = None
            warnings.append("Consent/footer block was not detected.")

        main_blocks = [block for block in blocks if block not in footer_blocks]
        main_content_bottom_y = max((block.y1 for block in main_blocks), default=None)
        if main_content_bottom_y is None:
            warnings.append("Main content bottom could not be estimated.")

        free_space_before_footer_pt = None
        footer_overlap_risk = False
        estimated_fill_ratio = None
        underfilled = False

        if main_content_bottom_y is not None:
            usable_bottom_y = footer_top_y if footer_top_y is not None else page_height_pt
            if footer_top_y is not None:
                gap_before_footer = footer_top_y - main_content_bottom_y
                free_space_before_footer_pt = max(gap_before_footer, 0.0)
                footer_overlap_risk = gap_before_footer < _FOOTER_OVERLAP_THRESHOLD_PT
            else:
                free_space_before_footer_pt = max(page_height_pt - main_content_bottom_y, 0.0)

            if usable_bottom_y > 0:
                estimated_fill_ratio = min(max(main_content_bottom_y / usable_bottom_y, 0.0), 1.0)

            underfilled = (
                not overfilled
                and not footer_overlap_risk
                and (
                    free_space_before_footer_pt > _UNDERFILLED_FREE_SPACE_THRESHOLD_PT
                    or (
                        estimated_fill_ratio is not None
                        and estimated_fill_ratio < _UNDERFILLED_FILL_RATIO_THRESHOLD
                    )
                )
            )
            if underfilled:
                warnings.append("Main content appears underfilled against the available first-page area.")

        return TypstPdfLayoutMetrics(
            page_count=page_count,
            is_single_page=page_count == 1,
            page_width_pt=round(page_width_pt, 2),
            page_height_pt=round(page_height_pt, 2),
            main_content_bottom_y=_round_optional_float(main_content_bottom_y),
            footer_top_y=_round_optional_float(footer_top_y),
            free_space_before_footer_pt=_round_optional_float(free_space_before_footer_pt),
            estimated_fill_ratio=_round_optional_float(estimated_fill_ratio, digits=3),
            underfilled=underfilled,
            overfilled=overfilled,
            footer_overlap_risk=footer_overlap_risk,
            footer_detected=footer_detected,
            analysis_warnings=warnings,
        )
    finally:
        document.close()


def _extract_text_blocks(text_dict: dict[str, Any]) -> list[_TextBlock]:
    """Return normalized text blocks with bounding boxes and span font sizes."""

    normalized_blocks: list[_TextBlock] = []
    for raw_block in text_dict.get("blocks", []):
        if raw_block.get("type") != 0:
            continue
        bbox = raw_block.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue

        block_text_parts: list[str] = []
        font_sizes: list[float] = []
        for raw_line in raw_block.get("lines", []):
            for raw_span in raw_line.get("spans", []):
                span_text = str(raw_span.get("text") or "").strip()
                if span_text:
                    block_text_parts.append(span_text)
                span_size = raw_span.get("size")
                if isinstance(span_size, (int, float)):
                    font_sizes.append(float(span_size))

        block_text = " ".join(block_text_parts).strip()
        if not block_text:
            continue

        normalized_blocks.append(
            _TextBlock(
                text=block_text,
                x0=float(bbox[0]),
                y0=float(bbox[1]),
                x1=float(bbox[2]),
                y1=float(bbox[3]),
                max_font_size=max(font_sizes) if font_sizes else None,
            )
        )

    return normalized_blocks


def _looks_like_footer(block: _TextBlock, page_height_pt: float) -> bool:
    """Return whether a text block is likely the consent footer."""

    normalized_text = block.text.lower()
    if any(phrase in normalized_text for phrase in _FOOTER_PHRASES):
        return True

    is_near_bottom = block.y0 >= page_height_pt * _BOTTOM_FOOTER_ZONE_RATIO
    is_small_text = block.max_font_size is not None and block.max_font_size <= _MAX_FOOTER_FONT_SIZE_PT
    return is_near_bottom and is_small_text and len(block.text) >= 20


def _round_optional_float(value: float | None, *, digits: int = 2) -> float | None:
    """Round a float when present."""

    if value is None:
        return None
    return round(float(value), digits)
