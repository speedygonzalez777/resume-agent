"""OpenAI-backed quality analysis for rendered Typst CV documents."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI, OpenAIError

from app.models.typst import (
    TypstQualityAnalysis,
    TypstQualityAnalysisRequest,
    TypstQualityAnalysisResponse,
)
from app.services.openai_model_resolver import resolve_typst_quality_model

TYPST_QUALITY_ANALYSIS_INSTRUCTIONS = """
You analyze a rendered one-page CV document after Typst rendering.

You receive the final TypstPayload, backend char metrics, hard/target limits,
local PDF layout metrics from PyMuPDF, and render warnings.

Your task is diagnostic only:
- Do not return a changed TypstPayload.
- Do not rewrite the CV.
- Do not suggest changing layout, fonts, template, or hard limits.
- Do not add facts outside the payload and supplied metrics.
- Treat underfilled layout as a quality warning, not an automatic failure.
- Treat page_count > 1 / overfilled as a serious issue.
- If underfilled, recommend expanding in this order when factual room exists:
  1. experience bullets,
  2. project descriptions,
  3. summary only lightly and generally.
- Do not treat the summary as the main page-filling mechanism.
- Recommend expanding experience bullets and project descriptions before summary.
- When evaluating underfilled documents, do not recommend filling the page by adding task
  lists to the summary.
- Summary may mention career direction or ambition, but it should not become a list of
  recent work.
- If summary contains phrases such as `Recent work includes`, `Recent experience includes`,
  `Current work includes`, `Experience spans`, `Background spans`, `Profile includes` or
  `Candidate has`, mark it as a style issue and recommend rewriting summary as a candidate profile.
- Do not recommend adding detailed technical systems, project names, product names or standards to the summary when those details fit better in Experience, Projects or Skills.
- If overfilled, recommend shortening in this order:
  1. summary,
  2. project descriptions,
  3. experience bullets.
- Be concrete about which sections should be expanded, shortened, avoided, or reviewed.
- The fit_to_page_plan is only a plan for a future explicit user-clicked step.
""".strip()


class TypstQualityAnalysisOpenAIError(Exception):
    """Raised when OpenAI cannot return structured Typst quality analysis."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def analyze_typst_render_quality_with_openai(
    request: TypstQualityAnalysisRequest,
) -> TypstQualityAnalysisResponse:
    """Return a structured AI diagnosis for one rendered Typst CV."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "tu_wkleisz_swoj_klucz":
        raise TypstQualityAnalysisOpenAIError(
            "OpenAI API key is missing. Typst render quality analysis is unavailable.",
            status_code=503,
        )

    model_name = resolve_typst_quality_model()
    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.parse(
            model=model_name,
            instructions=TYPST_QUALITY_ANALYSIS_INSTRUCTIONS,
            input=_build_quality_analysis_input_payload(request),
            text_format=TypstQualityAnalysis,
        )
    except OpenAIError as exc:
        raise TypstQualityAnalysisOpenAIError(
            "OpenAI Typst quality analysis request failed.",
            status_code=502,
            details={"model": model_name, "reason": str(exc)},
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive unexpected wrapper
        raise TypstQualityAnalysisOpenAIError(
            "Unexpected Typst quality analysis failure.",
            status_code=502,
            details={"model": model_name, "reason": str(exc)},
        ) from exc

    structured_output = response.output_parsed
    if structured_output is None:
        raise TypstQualityAnalysisOpenAIError(
            "OpenAI returned no structured Typst quality analysis.",
            status_code=502,
            details={"model": model_name},
        )

    return TypstQualityAnalysisResponse(
        analysis=TypstQualityAnalysis.model_validate(structured_output),
        model=model_name,
        warnings=[],
    )


def _build_quality_analysis_input_payload(request: TypstQualityAnalysisRequest) -> str:
    """Serialize one quality-analysis evidence pack for the model."""

    evidence_pack = {
        "task": "Analyze the already-rendered Typst CV quality. Do not modify the payload.",
        "typst_quality_analysis_input": request.model_dump(mode="json"),
    }
    return (
        "Return a structured TypstQualityAnalysis for this rendered CV evidence pack.\n\n"
        f"{json.dumps(evidence_pack, ensure_ascii=False, indent=2)}"
    )
