"""Helpers for building cleaner user-facing keyword lists without changing raw stored data."""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

_SHORT_DISPLAY_KEYWORD_CANONICAL_MAP = {
    "ai": "AI",
    "api": "API",
    "aws": "AWS",
    "bi": "BI",
    "cad": "CAD",
    "erp": "ERP",
    "gcp": "GCP",
    "hmi": "HMI",
    "mes": "MES",
    "ml": "ML",
    "plc": "PLC",
    "qa": "QA",
    "sap": "SAP",
    "sql": "SQL",
    "ui": "UI",
    "ux": "UX",
}
_GENERIC_DISPLAY_KEYWORD_STOPWORDS = {
    "design",
    "dev",
    "developer",
    "engineer",
    "engineering",
    "intern",
    "internship",
    "program",
    "programs",
    "project",
    "projects",
    "support",
    "system",
    "systems",
}


def normalize_display_keyword(value: str | None) -> str:
    """Normalize spacing and trim obvious edge punctuation for keyword display."""
    if not value:
        return ""
    collapsed = re.sub(r"\s+", " ", value).strip()
    return collapsed.strip(" ,;:")


def _normalized_display_key(value: str | None) -> str:
    """Build a case-insensitive key used for filtering and deduplication."""
    normalized = unicodedata.normalize("NFKD", normalize_display_keyword(value))
    return "".join(character for character in normalized if not unicodedata.combining(character)).lower()


def _canonicalize_display_keyword(value: str | None) -> str:
    """Return the preferred display form for one keyword candidate."""
    normalized_key = _normalized_display_key(value)
    if not normalized_key:
        return ""
    if normalized_key in _SHORT_DISPLAY_KEYWORD_CANONICAL_MAP:
        return _SHORT_DISPLAY_KEYWORD_CANONICAL_MAP[normalized_key]
    return normalize_display_keyword(value)


def should_keep_display_keyword(value: str | None) -> bool:
    """Decide whether a keyword is useful enough to show directly in the UI."""
    normalized_key = _normalized_display_key(value)
    if not normalized_key:
        return False
    if normalized_key in _GENERIC_DISPLAY_KEYWORD_STOPWORDS:
        return False

    is_single_alpha_token = normalized_key.isalpha() and " " not in normalized_key
    if is_single_alpha_token and len(normalized_key) < 4:
        return normalized_key in _SHORT_DISPLAY_KEYWORD_CANONICAL_MAP

    return True


def dedupe_display_keywords(values: Iterable[str | None]) -> list[str]:
    """Deduplicate display keywords while preserving the first useful surface form."""
    deduped: list[str] = []
    seen_keys: set[str] = set()

    for value in values:
        canonical_value = _canonicalize_display_keyword(value)
        normalized_key = _normalized_display_key(canonical_value)
        if not normalized_key or normalized_key in seen_keys:
            continue
        seen_keys.add(normalized_key)
        deduped.append(canonical_value)

    return deduped


def limit_display_keywords(values: Iterable[str | None], *, max_items: int | None) -> list[str]:
    """Optionally cap a cleaned keyword list while preserving order."""
    cleaned_values = [value for value in values if value]
    if max_items is None or max_items <= 0:
        return cleaned_values
    return cleaned_values[:max_items]


def build_display_keywords(
    values: Iterable[str | None],
    *,
    max_items: int | None = None,
) -> list[str]:
    """Build a cleaned user-facing keyword list from raw keyword candidates."""
    filtered_values = [value for value in values if should_keep_display_keyword(value)]
    deduped_values = dedupe_display_keywords(filtered_values)
    return limit_display_keywords(deduped_values, max_items=max_items)
