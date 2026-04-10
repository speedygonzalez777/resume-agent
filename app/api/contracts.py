"""Shared API-side contracts used by multiple backend routes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.match import MatchResult
from app.services.openai_candidate_profile_understanding_service import (
    CandidateProfileUnderstanding,
)
from app.services.openai_requirement_priority_service import OpenAIRequirementPriorityItem


class MatchingHandoffPayload(BaseModel):
    """Minimal semantic sidecars that generation can reuse after matching."""

    requirement_priority_lookup: dict[str, OpenAIRequirementPriorityItem] | None = None
    candidate_profile_understanding: CandidateProfileUnderstanding | None = None


class MatchAnalyzeDebugResponse(BaseModel):
    """Debug-oriented match-analysis response used for developer observability."""

    match_result: MatchResult
    matching_debug: dict[str, Any] = Field(default_factory=dict)
    matching_handoff: MatchingHandoffPayload
