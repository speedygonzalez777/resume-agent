"""Small centralized term-relation helpers used for supporting alignment, not exact overclaims."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable, Literal

RelationType = Literal["exact", "supporting"]

_SUPPORTING_RELATIONS: dict[str, set[str]] = {
    "sql": {
        "mariadb",
        "mysql",
        "postgresql",
        "sqlite",
        "t-sql",
        "tsql",
    },
}
_DISPLAY_CANONICAL_MAP = {
    "sql": "SQL",
}


@dataclass(frozen=True)
class TermRelationHit:
    """One normalized relation between an offer-side term and grounded candidate evidence."""

    offer_term: str
    evidence_term: str
    relation_type: RelationType
    weight: float


def normalize_term_relation_key(value: str | None) -> str:
    """Normalize one term key for exact/supporting concept matching."""

    if not value:
        return ""

    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(character for character in normalized if not unicodedata.combining(character))
    return " ".join(without_accents.strip().lower().split())


def canonicalize_relation_display(value: str | None) -> str:
    """Return the preferred display label for one normalized relation term."""

    normalized_key = normalize_term_relation_key(value)
    if not normalized_key:
        return ""
    return _DISPLAY_CANONICAL_MAP.get(normalized_key, value.strip() if value else "")


def find_offer_term_relation_hits(
    *,
    offer_terms: Iterable[str],
    evidence_terms: Iterable[str],
) -> list[TermRelationHit]:
    """Find exact or supporting relations between offer terms and grounded candidate evidence."""

    hits: list[TermRelationHit] = []
    seen_keys: set[tuple[str, str, str]] = set()

    cleaned_evidence_terms = [term for term in evidence_terms if term and term.strip()]

    for offer_term in offer_terms:
        normalized_offer_term = normalize_term_relation_key(offer_term)
        if not normalized_offer_term:
            continue

        supporting_terms = _SUPPORTING_RELATIONS.get(normalized_offer_term, set())
        canonical_offer_term = canonicalize_relation_display(offer_term)

        for evidence_term in cleaned_evidence_terms:
            normalized_evidence_term = normalize_term_relation_key(evidence_term)
            if not normalized_evidence_term:
                continue

            relation_type: RelationType | None = None
            weight = 0.0

            if normalized_offer_term == normalized_evidence_term:
                relation_type = "exact"
                weight = 1.0
            elif normalized_evidence_term in supporting_terms:
                relation_type = "supporting"
                weight = 0.45

            if relation_type is None:
                continue

            hit_key = (normalized_offer_term, normalized_evidence_term, relation_type)
            if hit_key in seen_keys:
                continue
            seen_keys.add(hit_key)
            hits.append(
                TermRelationHit(
                    offer_term=canonical_offer_term,
                    evidence_term=evidence_term.strip(),
                    relation_type=relation_type,
                    weight=weight,
                )
            )

    return hits
