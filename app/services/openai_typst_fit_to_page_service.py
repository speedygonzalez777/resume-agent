"""OpenAI-backed patch generator for explicit Typst CV fit-to-page improvements."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI, OpenAIError

from app.models.typst import TypstFitToPagePatch, TypstFitToPageRequest
from app.services.openai_model_resolver import resolve_typst_fit_to_page_model

TYPST_FIT_TO_PAGE_INSTRUCTIONS = """
You create a safe text-only patch for an existing TypstPayload.

This is not full CV regeneration. Return only a TypstFitToPagePatch. Do not return
a full TypstPayload. The backend will merge and validate your patch.

Allowed fields in this v1 patch:
- summary_text, only lightly and generally.
- experience_entries[i].bullets[j], using existing bullet facts and context.
- project_entries[i].description, using existing project facts and context.

Forbidden changes:
- Do not change profile/contact fields, render options, education, company, role, dates,
  project names, number of entries, number of bullets, skill entries, language/certificate
  entries, links, layout or limits.
- Do not add facts outside the current TypstPayload, supplied analysis context and
  source_evidence_pack.
- Do not create new jobs, projects, certifications, skills, tools, seniority, ownership,
  metrics or business impact.

Source evidence and semantic precision:
- Treat source_evidence_pack as the source of truth for expanding experience bullets and
  project descriptions. The current TypstPayload still controls which entries exist.
- Use source evidence to preserve correct relationships between facts.
- Do not create new relationships between tools, languages, standards, methods,
  certificates, tasks, products and outcomes unless the relationship is explicit in the
  source evidence.
- If a relationship is unclear, use more neutral phrasing or keep the text shorter.
- Do not join terms into one phrase just because they appear near each other.
- When evidence confidence is low, do not infer seniority, responsibility, ownership,
  outcomes or exact technical relationships.
- Concept grounding may describe safe and unsafe usage of terms. Follow it, but do not
  treat it as permission to add candidate experiences or skills.
- No external lookup is available in this step. Do not pretend public verification was
  performed.
- Neutral examples of relationship care: a tool is not automatically a programming
  language; a certificate is not automatically a skill; a standard is not automatically
  an implementation; a method is not automatically an outcome.

Fit behavior:
- Retry feedback is mandatory and must be followed exactly. If validation feedback is
  supplied, fix the listed fields instead of repeating the same expansion.
- If `force` is true, the user requested optional expansion despite quality analysis not requiring it. Keep the patch conservative: prioritize experience bullets, then project descriptions, avoid summary unless necessary, do not add filler and do not exceed hard limits.
- Never exceed hard limits.
- If validation feedback says a project description exceeded the hard limit, shorten that project description instead of expanding it again.
- Project descriptions are secondary expansion targets and must stay comfortably below hard limits.
- If underfilled, expand experience bullets first, project descriptions second, and summary only last and lightly.
- If the document is clearly underfilled and free space before the footer is still large,
  the patch should be meaningful rather than cosmetic. Do not stop after one minor wording change when several short experience bullets or project descriptions can be safely improved.
- Prefer improving most short experience bullets that are below their target length, when
  the current payload contains enough factual material to support a stronger sentence.
- Use the supplied target lengths as density guidance, but keep every changed field below
  its hard limit. Do not sacrifice correctness or naturalness just to fill space.
- If overfilled, shorten summary first, project descriptions second, and experience bullets third.
- Keep wording natural, professional and recruiter-readable.
- Do not write technical documentation or long technology lists.
- Stay below the supplied hard limits. Prefer target limits when possible.
- Summary is not a page filler. The default fit-to-page behavior is to return
  `summary_text: null`.
- Modify `summary_text` only when needed for overfill, hard limit, explicit style
  violation or an explicit quality issue in the supplied analysis.
- Keep summary profile-oriented, fluent and general; do not use it as a page filler.
- Do not add artificial summary sentences such as "Recent work includes..." or
  "Interested in ... practical engineering workflows". If summary is changed at all, keep
  it as a smooth CV profile paragraph and make only light, general improvements.
- If the source evidence contains a user-authored profile summary, any summary_text
  change must preserve that source summary's meaning and professional direction, not
  necessarily exact wording.
- Keep wording close only when it fits within the character limits. Hard limits outrank
  wording preservation.
- Do not copy source-note transitions such as "My recent experience includes",
  "Recent experience includes", "Recent work includes", "Experience spans" or
  "Profile includes"; rewrite them into polished CV profile phrasing.
- Avoid modifying summary_text unless needed. If summary_text is modified, it must preserve
  the candidate-profile style: candidate profile, practical background and professional
  direction.
- Do not use summary_text to stuff recent tasks, product-specific facts, project-specific
  facts or detailed technical standards into the CV.
- Do not replace summary_text with job keywords, projects, technologies or a technology list.
- Do not add recent-task phrases such as "Recent work includes", "Recent experience includes",
  "Current work includes", "Experience spans", "Background spans", "Profile includes" or
  "Candidate has".
- Do not use third-person wording in summary_text, such as "He has", "She has",
  "The candidate has", "The candidate is", "This candidate", "His experience" or
  "Her experience". Use natural CV profile style with an implied subject instead.
- Ambition-oriented phrases such as "Interested in" or "Looking to grow" are allowed only
  when they naturally describe career direction, target roles or professional development.

Experience bullet style:
- Use standard CV bullet style with implied first person: no "I", "my" or "we", but also
  no forced third-person phrasing.
- Start with natural action verbs when they fit the facts.
- "Worked on" is allowed when it is the most accurate wording, but do not use it as the default weak opening if a more specific verb is available.
- A good expanded bullet should mention concrete scope, context, tool or technical area,
  without becoming a dense list of technologies.
- Avoid vague filler and pseudo-technical phrasing such as "practical shop-floor environment",
  "practical engineering workflows", "turning technical analysis into real-world performance",
  "bridging concepts with operational outcomes", "turning analysis into real-world
  performance", "recent work includes", or filler uses of "focused on".
- Prefer direct factual phrasing when supported by source evidence, for example:
  "built a reporting workflow with the supplied dashboard tool" is safer than implying
  ownership, deployment or business impact that the evidence does not state.
- If a field cannot be improved with a concrete fact already present in the payload or
  source evidence, leave it unchanged rather than adding abstract marketing filler.

Project descriptions:
- If experience bullets have been improved and room remains, expand project descriptions
  within their target lengths using only existing project facts.
- Do not add projects or rename projects.
- Avoid pseudo-technical paraphrases; write directly and concretely.
""".strip()


class TypstFitToPageOpenAIError(Exception):
    """Raised when OpenAI cannot return a safe Typst fit-to-page patch."""

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


@dataclass(frozen=True)
class TypstFitToPagePatchResult:
    """Generated Typst fit-to-page patch plus model metadata."""

    patch: TypstFitToPagePatch
    model_name: str


def generate_typst_fit_to_page_patch_with_openai(
    request: TypstFitToPageRequest,
    *,
    retry_feedback: str | None = None,
) -> TypstFitToPagePatchResult:
    """Generate a structured patch for explicit user-triggered fit-to-page."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "tu_wkleisz_swoj_klucz":
        raise TypstFitToPageOpenAIError(
            "OpenAI API key is missing. Typst fit-to-page is unavailable.",
            status_code=503,
        )

    model_name = resolve_typst_fit_to_page_model()
    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.parse(
            model=model_name,
            instructions=TYPST_FIT_TO_PAGE_INSTRUCTIONS,
            input=_build_fit_to_page_input_payload(request, retry_feedback=retry_feedback),
            text_format=TypstFitToPagePatch,
        )
    except OpenAIError as exc:
        raise TypstFitToPageOpenAIError(
            "OpenAI Typst fit-to-page request failed.",
            status_code=502,
            details={"model": model_name, "reason": str(exc)},
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive unexpected wrapper
        raise TypstFitToPageOpenAIError(
            "Unexpected Typst fit-to-page failure.",
            status_code=502,
            details={"model": model_name, "reason": str(exc)},
        ) from exc

    structured_output = response.output_parsed
    if structured_output is None:
        raise TypstFitToPageOpenAIError(
            "OpenAI returned no structured Typst fit-to-page patch.",
            status_code=502,
            details={"model": model_name},
        )

    return TypstFitToPagePatchResult(
        patch=TypstFitToPagePatch.model_validate(structured_output),
        model_name=model_name,
    )


def _build_fit_to_page_input_payload(
    request: TypstFitToPageRequest,
    *,
    retry_feedback: str | None = None,
) -> str:
    """Serialize one fit-to-page evidence pack for the model."""

    evidence_pack = {
        "task": (
            "Create a safe evidence-backed patch for explicit fit-to-page. "
            "Do not modify immutable fields."
        ),
        "typst_fit_to_page_input": request.model_dump(mode="json"),
    }
    if retry_feedback:
        evidence_pack["validation_feedback"] = retry_feedback
    return (
        "Return a structured TypstFitToPagePatch for this rendered CV evidence pack.\n\n"
        f"{json.dumps(evidence_pack, ensure_ascii=False, indent=2)}"
    )
