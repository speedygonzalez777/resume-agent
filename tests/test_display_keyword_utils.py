from app.services.display_keyword_utils import (
    build_display_keywords,
    dedupe_display_keywords,
    limit_display_keywords,
    normalize_display_keyword,
    should_keep_display_keyword,
)


def test_normalize_display_keyword_collapses_spacing_and_trims_punctuation() -> None:
    assert normalize_display_keyword("  technical   documentation, ") == "technical documentation"


def test_should_keep_display_keyword_filters_short_noise_and_generic_terms_but_keeps_short_exceptions() -> None:
    assert not should_keep_display_keyword("sta")
    assert not should_keep_display_keyword("program")
    assert not should_keep_display_keyword("support")
    assert not should_keep_display_keyword("projects")
    assert not should_keep_display_keyword("engineering")
    assert should_keep_display_keyword("AI")
    assert should_keep_display_keyword("PLC")
    assert should_keep_display_keyword("SQL")


def test_build_display_keywords_filters_canonicalizes_and_deduplicates() -> None:
    assert build_display_keywords([
        "sta",
        "program",
        "support",
        "projects",
        "engineering",
        "ai",
        "PLC",
        "sql",
        "technical documentation",
        "PLC",
    ]) == ["AI", "PLC", "SQL", "technical documentation"]


def test_dedupe_display_keywords_is_case_insensitive() -> None:
    assert dedupe_display_keywords(["PLC", "plc", "SQL", "sql"]) == ["PLC", "SQL"]


def test_limit_display_keywords_preserves_order() -> None:
    assert limit_display_keywords(["PLC", "SQL", "AI"], max_items=2) == ["PLC", "SQL"]


def test_build_display_keywords_can_cap_cleaned_user_facing_list() -> None:
    assert build_display_keywords(
        ["PLC", "SQL", "AI", "commissioning", "technical documentation"],
        max_items=3,
    ) == ["PLC", "SQL", "AI"]
