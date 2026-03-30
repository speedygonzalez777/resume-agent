from app.models.job import JobPosting, Requirement
from app.services.reportable_term_utils import (
    build_reportable_offer_terms,
    build_requirement_reportable_terms_lookup,
    parse_offer_term_candidate,
)
from app.services.openai_requirement_priority_service import OpenAIRequirementPriorityItem


def _build_job_posting() -> JobPosting:
    return JobPosting(
        source="manual",
        title="Generative AI Engineer",
        company_name="Acme",
        location="Warszawa",
        work_mode="hybrid",
        employment_type="B2B",
        seniority_level="mid",
        role_summary="Build agent systems with modern AI tooling.",
        responsibilities=[],
        requirements=[],
        keywords=[],
        language_of_offer="pl",
    )


def _build_requirement(
    requirement_id: str,
    text: str,
    extracted_keywords: list[str],
    *,
    category: str = "technology",
    requirement_type: str = "nice_to_have",
    importance: str = "medium",
) -> Requirement:
    return Requirement(
        id=requirement_id,
        text=text,
        category=category,
        requirement_type=requirement_type,
        importance=importance,
        extracted_keywords=extracted_keywords,
    )


def _build_priority_item(requirement_id: str, priority_tier: str) -> OpenAIRequirementPriorityItem:
    return OpenAIRequirementPriorityItem(
        requirement_id=requirement_id,
        priority_tier=priority_tier,
        confidence="high",
        reasoning_note=f"{requirement_id} is {priority_tier}.",
    )


def test_parse_offer_term_candidate_salvages_real_term_from_threshold_but_marks_primary_role() -> None:
    job_posting = _build_job_posting()
    requirement = _build_requirement(
        "req_python",
        "Co najmniej 1 rok doświadczenia z Pythonem",
        ["min. 1 rok", "Python"],
    )

    candidate = parse_offer_term_candidate(
        "min. 1 rok Python",
        source_kind="requirement",
        requirement=requirement,
        job_posting=job_posting,
    )

    assert candidate.primary_role == "matching_constraint"
    assert candidate.reportable_term == "Python"


def test_parse_offer_term_candidate_drops_generic_wrapper_phrase() -> None:
    job_posting = _build_job_posting()
    requirement = _build_requirement(
        "req_dev",
        "Doświadczenie jako deweloper",
        ["doświadczenie jako deweloper"],
    )

    candidate = parse_offer_term_candidate(
        "doświadczenie jako deweloper",
        source_kind="requirement",
        requirement=requirement,
        job_posting=job_posting,
    )

    assert candidate.primary_role == "generic_wrapper"
    assert candidate.reportable_term is None


def test_build_reportable_offer_terms_separates_terms_from_modifiers_thresholds_and_metadata() -> None:
    job_posting = _build_job_posting()
    job_posting.requirements = [
        _build_requirement(
            "req_langgraph",
            "Mile widziany LangGraph",
            ["mile widziany", "LangGraph"],
        ),
        _build_requirement(
            "req_python",
            "Co najmniej 1 rok doświadczenia z Pythonem",
            ["min. 1 rok", "Python"],
        ),
        _build_requirement(
            "req_frameworks",
            "Znajomość frameworków PyTorch i TensorFlow",
            ["znajomość", "frameworki", "PyTorch", "TensorFlow"],
        ),
        _build_requirement(
            "req_schedule",
            "Availability Monday-Friday, 32 hours weekly",
            ["availability", "Monday-Friday", "32 hours"],
            category="other",
        ),
        _build_requirement(
            "req_fast_paced",
            "Experience in a fast-paced environment",
            ["fast-paced"],
            category="soft_skill",
            importance="low",
        ),
    ]
    job_posting.keywords = [
        "LangGraph",
        "min. 1 rok",
        "Python",
        "frameworki",
        "PyTorch",
        "TensorFlow",
        "Warszawa",
        "hybrid",
        "B2B",
        "availability",
        "fast-paced",
    ]
    priority_lookup = {
        "req_fast_paced": _build_priority_item("req_fast_paced", "low_signal"),
    }

    requirement_terms = build_requirement_reportable_terms_lookup(
        job_posting,
        requirement_priority_lookup=priority_lookup,
    )
    reportable_terms = build_reportable_offer_terms(
        job_posting,
        requirement_priority_lookup=priority_lookup,
    )

    assert requirement_terms["req_langgraph"] == ["LangGraph"]
    assert requirement_terms["req_python"] == ["Python"]
    assert requirement_terms["req_frameworks"] == ["PyTorch", "TensorFlow"]
    assert requirement_terms["req_schedule"] == []
    assert requirement_terms["req_fast_paced"] == []
    assert reportable_terms == ["LangGraph", "Python", "PyTorch", "TensorFlow"]


def test_build_reportable_offer_terms_treats_top_level_keywords_as_primary_truth() -> None:
    job_posting = _build_job_posting()
    job_posting.requirements = [
        _build_requirement(
            "req_model_serving",
            "Integracja oraz serwowanie modeli w srodowisku produkcyjnym",
            ["integracja", "serwowanie modeli", "LangGraph"],
        ),
    ]
    job_posting.keywords = ["LangGraph", "Python"]

    reportable_terms = build_reportable_offer_terms(job_posting)

    assert reportable_terms == ["LangGraph", "Python"]


def test_build_reportable_offer_terms_allows_requirement_only_concrete_single_term_when_missing_upstream() -> None:
    job_posting = _build_job_posting()
    job_posting.requirements = [
        _build_requirement(
            "req_english",
            "English at communicative level",
            ["English", "communication"],
            category="language",
            requirement_type="must_have",
            importance="high",
        ),
    ]
    job_posting.keywords = ["PLC"]

    requirement_terms = build_requirement_reportable_terms_lookup(job_posting)
    reportable_terms = build_reportable_offer_terms(job_posting)

    assert requirement_terms["req_english"] == ["English", "communication"]
    assert reportable_terms == ["English", "communication", "PLC"]
