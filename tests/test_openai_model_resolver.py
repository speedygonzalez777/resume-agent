from __future__ import annotations

from app.services.openai_model_resolver import (
    resolve_job_parsing_model,
    resolve_matching_model,
    resolve_resume_generation_model,
    resolve_resume_refinement_model,
)


def test_resolve_job_parsing_model_defaults_to_mini(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_JOB_PARSER_MODEL", raising=False)

    assert resolve_job_parsing_model() == "gpt-5-mini"


def test_resolve_matching_model_prefers_workflow_env_over_legacy_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MATCHING_MODEL", "gpt-5.4")
    monkeypatch.setenv("OPENAI_REQUIREMENT_TYPE_MODEL", "gpt-5-mini")

    assert (
        resolve_matching_model(legacy_env_name="OPENAI_REQUIREMENT_TYPE_MODEL")
        == "gpt-5.4"
    )


def test_resolve_matching_model_falls_back_to_legacy_env(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_MATCHING_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_REQUIREMENT_PRIORITY_MODEL", "gpt-5-mini")

    assert (
        resolve_matching_model(legacy_env_name="OPENAI_REQUIREMENT_PRIORITY_MODEL")
        == "gpt-5-mini"
    )


def test_resolve_resume_generation_model_prefers_workflow_env_over_legacy_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_RESUME_GENERATION_MODEL", "gpt-5.4")
    monkeypatch.setenv("OPENAI_RESUME_TAILORING_MODEL", "gpt-5-mini")

    assert (
        resolve_resume_generation_model(
            legacy_env_name="OPENAI_RESUME_TAILORING_MODEL",
        )
        == "gpt-5.4"
    )


def test_resolve_resume_refinement_model_defaults_to_mini(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_RESUME_DRAFT_REFINEMENT_MODEL", raising=False)

    assert resolve_resume_refinement_model() == "gpt-5-mini"
