from app.services.term_relation_utils import find_offer_term_relation_hits


def test_find_offer_term_relation_hits_treats_sqlite_as_supporting_sql_evidence() -> None:
    hits = find_offer_term_relation_hits(
        offer_terms=["SQL", "Python"],
        evidence_terms=["SQLite", "FastAPI"],
    )

    assert [hit.offer_term for hit in hits] == ["SQL"]
    assert hits[0].evidence_term == "SQLite"
    assert hits[0].relation_type == "supporting"
