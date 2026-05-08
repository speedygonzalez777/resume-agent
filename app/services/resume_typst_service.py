"""Typst prepare/render services with source resolution, fitter orchestration and validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
from typing import Any, Literal

from app.models.candidate import CandidateProfile, EducationEntry, ExperienceEntry, ProjectEntry
from app.models.resume import ResumeDraft, ResumeExperienceEntry, ResumeProjectEntry
from app.models.typst import (
    TYPST_LIMIT_CONFIG,
    TypstArtifactRef,
    TypstConceptGrounding,
    TypstDraftVariant,
    TypstEducationEntry,
    TypstExperienceEntry,
    TypstFitToPageDebug,
    TypstFitToPagePatch,
    TypstFitToPageRequest,
    TypstFitToPageResponse,
    TypstPayload,
    TypstPrepareDebug,
    TypstPrepareRequest,
    TypstPrepareResponse,
    TypstPhotoUploadResponse,
    TypstProfilePayload,
    TypstProjectEntry,
    TypstRenderOptions,
    TypstRenderResponse,
    TypstSourceEvidenceItem,
    TypstSourceEvidencePack,
)
from app.services.openai_typst_fit_to_page_service import (
    TypstFitToPageOpenAIError,
    generate_typst_fit_to_page_patch_with_openai,
)
from app.services.openai_resume_typst_fitter_service import (
    ResumeTypstFitterOpenAIError,
    generate_typst_payload_with_openai,
)
from app.services.persistence_service import get_candidate_profile, get_resume_draft
from app.services.typst_pdf_layout_analysis_service import (
    TypstPdfLayoutAnalysisError,
    analyze_typst_pdf_layout,
)


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ARTIFACTS_DIR = _PROJECT_ROOT / "artifacts"
_SNAP_TYPST_BINARY = Path("/snap/bin/typst")
_TYPST_RENDER_TIMEOUT_SECONDS = 30
_MAX_PHOTO_UPLOAD_BYTES = 5 * 1024 * 1024
_ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
_ALLOWED_PHOTO_CONTENT_TYPES = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
}
_PHOTO_ASSET_ID_PATTERN = re.compile(r"^photo_[0-9]{8}_[0-9]{6}_[a-f0-9]{8}\.(jpg|jpeg|png)$")
_RENDER_ID_PATTERN = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-f0-9]{4}$")
_SOURCE_EVIDENCE_MAX_EXPERIENCE = 2
_SOURCE_EVIDENCE_MAX_PROJECTS = 2
_SOURCE_EVIDENCE_MAX_RESPONSIBILITIES = 3
_SOURCE_EVIDENCE_MAX_ACHIEVEMENTS = 3
_SOURCE_EVIDENCE_MAX_TECH_TERMS = 8
_SOURCE_EVIDENCE_MAX_HIGHLIGHTS = 3
_SOURCE_EVIDENCE_MAX_GROUNDING_TERMS = 20
_SOURCE_EVIDENCE_TEXT_LIMIT = 180

_PLACEHOLDER_VALUES = {"n/a", "na", "none", "unknown", "tbd", "todo", "-"}
_SUMMARY_RECENT_TASK_STYLE_PHRASES = (
    "recent work includes",
    "recent experience includes",
    "current work includes",
    "experience spans",
    "background spans",
    "profile includes",
    "candidate has",
)
_SUMMARY_THIRD_PERSON_STYLE_PHRASES = (
    "the candidate has",
    "the candidate is",
    "this candidate",
    "his experience",
    "her experience",
    "candidate has",
    "he has",
    "she has",
    "he is",
    "she is",
)
_LANGUAGE_LEVEL_ONLY_VALUES = {
    "a1",
    "a2",
    "b1",
    "b2",
    "c1",
    "c2",
    "advanced",
    "basic",
    "beginner",
    "bilingual",
    "business working",
    "conversational",
    "elementary",
    "fluent",
    "full professional proficiency",
    "intermediate",
    "limited working proficiency",
    "native",
    "native speaker",
    "professional",
    "professional working",
    "working proficiency",
}
_MONTH_ABBREVIATIONS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_SOFTWARE_SKILL_HINTS = (
    "ai",
    "api",
    "backend",
    "data",
    "fastapi",
    "frontend",
    "javascript",
    "llm",
    "machine learning",
    "openai",
    "python",
    "react",
    "software",
    "sqlite",
    "web",
)
_AUTOMATION_SKILL_HINTS = (
    "automation",
    "cia 402",
    "codesys",
    "control",
    "electrical",
    "engineering",
    "iot",
    "plc",
    "robot",
    "structured text",
    "tia",
    "tia portal",
)
_SECTION_LABELS = {
    "en": {
        "summary": "SUMMARY",
        "education": "EDUCATION",
        "experience": "EXPERIENCE",
        "projects": "PROJECTS",
        "skills": "SKILLS",
        "languages": "LANGUAGES & CERTIFICATES",
        "email": "Email:",
        "phone": "Phone:",
        "linkedin": "LinkedIn:",
        "github": "GitHub:",
        "thesis": "Thesis:",
    },
    "pl": {
        "summary": "PODSUMOWANIE",
        "education": "WYKSZTAŁCENIE",
        "experience": "DOŚWIADCZENIE",
        "projects": "PROJEKTY",
        "skills": "UMIEJĘTNOŚCI",
        "languages": "JĘZYKI I CERTYFIKATY",
        "email": "Email:",
        "phone": "Telefon:",
        "linkedin": "LinkedIn:",
        "github": "GitHub:",
        "thesis": "Praca dyplomowa:",
    },
}
_DEFAULT_CONSENT_TEXT = {
    "en": (
        "I consent to the processing of my personal data for the purposes necessary to conduct "
        "the recruitment process for the position I am applying for, in accordance with Regulation "
        "(EU) 2016/679 of the European Parliament and of the Council of 27 April 2016 (GDPR)."
    ),
    "pl": (
        "Wyrażam zgodę na przetwarzanie moich danych osobowych w celu prowadzenia rekrutacji "
        "na stanowisko, na które aplikuję, zgodnie z Rozporządzeniem Parlamentu Europejskiego "
        "i Rady (UE) 2016/679 z dnia 27 kwietnia 2016 r. (RODO)."
    ),
}


class TypstPrepareError(ValueError):
    """Base error returned by the Typst prepare flow."""

    error_code = "typst_prepare_failed"

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_error_detail(self, *, stage: str = "prepare") -> dict[str, Any]:
        """Return a structured FastAPI error detail for UI/debug display."""

        return {
            "error_code": self.error_code,
            "message": self.message,
            "stage": stage,
            **self.details,
        }


class TypstPrepareSourceError(TypstPrepareError):
    """Raised when the prepare endpoint cannot resolve a valid Typst source."""

    error_code = "typst_prepare_source_error"


class TypstPayloadValidationError(TypstPrepareError):
    """Raised when the fitter output violates deterministic Typst constraints."""

    error_code = "typst_payload_validation_failed"

    def __init__(
        self,
        message: str,
        *,
        violations: list[str],
        section_counts: dict[str, int],
        char_metrics: dict[str, Any],
        retry_attempted: bool = False,
        fitter_model: str | None = None,
        warnings: list[str] | None = None,
        status_code: int = 422,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.violations = violations
        self.section_counts = section_counts
        self.char_metrics = char_metrics
        self.retry_attempted = retry_attempted
        self.fitter_model = fitter_model
        self.warnings = warnings or []

    def to_retry_feedback(self) -> str:
        """Return concrete validation feedback suitable for one corrective retry."""

        return _build_typst_retry_feedback(self.violations, self.char_metrics)

    def to_error_detail(self, *, stage: str = "prepare") -> dict[str, Any]:
        """Return structured validation diagnostics for the frontend debug panel."""

        return {
            "error_code": self.error_code,
            "message": self.message,
            "stage": stage,
            "validation_errors": self.violations,
            "retry_attempted": self.retry_attempted,
            "fitter_model": self.fitter_model,
            "char_metrics": self.char_metrics,
            "section_counts": self.section_counts,
            "warnings": self.warnings,
        }


def _build_typst_retry_feedback(
    violations: list[str],
    char_metrics: dict[str, Any],
) -> str:
    """Build specific validation feedback for the single corrective fitter retry."""

    feedback_lines = [
        "The previous TypstPayload failed backend validation.",
        "Regenerate the TypstPayload and fix exactly the fields listed below while preserving truthful content.",
        "Hard character limits are absolute. Target character limits are preferred. Any field above a hard limit will be rejected again.",
    ]

    if violations:
        feedback_lines.append("Validation errors:")
        feedback_lines.extend(f"- {violation}" for violation in violations)

    length_feedback = _collect_hard_limit_retry_feedback(char_metrics)
    if length_feedback:
        feedback_lines.append("Length fixes:")
        feedback_lines.extend(f"- {item}" for item in length_feedback)

    return "\n".join(feedback_lines)


def _collect_hard_limit_retry_feedback(
    metrics: Any,
    *,
    path: str = "",
) -> list[str]:
    """Collect readable retry instructions for fields that exceeded hard char limits."""

    if _is_length_metric(metrics):
        if not metrics.get("exceeds_hard"):
            return []

        field_path = path or "value"
        char_count = metrics["char_count"]
        target_chars = metrics["target_chars"]
        hard_chars = metrics["hard_chars"]
        return [
            (
                f"{field_path} has {char_count} characters. Target is {target_chars} characters. "
                f"Hard limit is {hard_chars} characters. Rewrite {field_path} to be at or below "
                f"{target_chars} characters if possible and never above {hard_chars} characters."
            )
        ]

    if isinstance(metrics, dict):
        feedback: list[str] = []
        for key, value in metrics.items():
            child_path = f"{path}.{key}" if path else str(key)
            feedback.extend(_collect_hard_limit_retry_feedback(value, path=child_path))
        return feedback

    if isinstance(metrics, list):
        feedback = []
        for index, value in enumerate(metrics):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            feedback.extend(_collect_hard_limit_retry_feedback(value, path=child_path))
        return feedback

    return []


def _is_length_metric(value: Any) -> bool:
    """Return whether one char_metrics node is a single length metric."""

    if not isinstance(value, dict):
        return False
    return {"char_count", "target_chars", "hard_chars", "exceeds_hard"}.issubset(value)


class TypstRenderError(ValueError):
    """Base controlled error returned by the Typst render flow."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        error_code: str = "typst_render_failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}

    def to_error_detail(self, *, stage: str = "render") -> dict[str, Any]:
        """Return a structured FastAPI error detail for UI/debug display."""

        return {
            "error_code": self.error_code,
            "message": self.message,
            "stage": stage,
            **self.details,
        }


class TypstFitToPageError(ValueError):
    """Base controlled error returned by the Typst fit-to-page flow."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        error_code: str = "typst_fit_to_page_failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}

    def to_error_detail(self, *, stage: str = "fit-to-page") -> dict[str, Any]:
        """Return a structured FastAPI error detail for UI/debug display."""

        return {
            "error_code": self.error_code,
            "message": self.message,
            "stage": stage,
            **self.details,
        }


class TypstArtifactError(ValueError):
    """Base controlled error returned by local Typst artifact endpoints."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(slots=True)
class ResolvedTypstPrepareSource:
    """Resolved source inputs reused by the prepare flow."""

    resume_draft: ResumeDraft
    candidate_profile: CandidateProfile | None
    source_mode: str
    draft_variant: TypstDraftVariant | None
    stored_resume_draft_id: int | None
    candidate_profile_id: int | None
    warnings: list[str]


@dataclass(slots=True)
class TypstFitterInputBundle:
    """Compact evidence pack sent to the Typst fitter together with debug metadata."""

    payload: dict[str, Any]
    profile_assisted_sections: list[str]


def prepare_typst_payload(request: TypstPrepareRequest) -> TypstPrepareResponse:
    """Resolve the Typst source, call the AI fitter and validate the resulting payload."""

    resolved_source = resolve_typst_prepare_source(request)
    fitter_input_bundle = _build_typst_fitter_input_bundle(
        resolved_source,
        request.options,
    )

    retry_feedback: str | None = None
    retry_count = 0
    last_validation_error: TypstPayloadValidationError | None = None

    for attempt in range(2):
        try:
            fitter_result = generate_typst_payload_with_openai(
                fitter_input_bundle.payload,
                retry_feedback=retry_feedback,
            )
        except ResumeTypstFitterOpenAIError as exc:
            raise TypstPrepareError(
                exc.message,
                status_code=exc.status_code,
                details={
                    "error_code": "typst_fitter_failed",
                    "fitter_model": exc.details.get("model"),
                    "details": exc.details,
                    "retry_attempted": retry_count > 0,
                    "warnings": list(resolved_source.warnings),
                },
            ) from exc

        normalized_payload = _normalize_typst_payload(
            fitter_result.typst_payload,
            request.options,
        )

        try:
            section_counts, char_metrics = _validate_typst_payload(normalized_payload)
        except TypstPayloadValidationError as exc:
            last_validation_error = exc
            exc.fitter_model = fitter_result.model_name
            exc.retry_attempted = retry_count > 0 or attempt > 0
            exc.warnings = list(resolved_source.warnings)
            if attempt == 0:
                retry_count = 1
                retry_feedback = exc.to_retry_feedback()
                summary_retry_feedback = _build_user_authored_summary_retry_feedback(
                    resolved_source,
                    exc.violations,
                    exc.char_metrics,
                )
                if summary_retry_feedback:
                    retry_feedback = f"{retry_feedback}\n\n{summary_retry_feedback}"
                continue
            raise

        warnings = list(resolved_source.warnings)
        if retry_count:
            warnings.append("One corrective Typst fitter retry was needed after validation.")

        return TypstPrepareResponse(
            typst_payload=normalized_payload,
            prepare_debug=TypstPrepareDebug(
                source_mode=resolved_source.source_mode,
                draft_variant=resolved_source.draft_variant,
                stored_resume_draft_id=resolved_source.stored_resume_draft_id,
                resolved_candidate_profile_id=resolved_source.candidate_profile_id,
                candidate_profile_available=resolved_source.candidate_profile is not None,
                stub_mode=False,
                fitter_model=fitter_result.model_name,
                translation_applied=request.options.language.value == "pl",
                profile_assisted_sections=fitter_input_bundle.profile_assisted_sections,
                warnings=warnings,
                section_counts=section_counts,
                char_metrics=char_metrics,
            ),
        )

    if last_validation_error is not None:  # pragma: no cover - defensive, loop always returns or raises
        raise last_validation_error

    raise TypstPrepareError("Typst prepare failed unexpectedly.", status_code=500)


def render_typst_payload(typst_payload: TypstPayload) -> TypstRenderResponse:
    """Generate a Typst source artifact and compile it into a PDF artifact."""

    try:
        _validate_typst_payload(typst_payload)
    except TypstPayloadValidationError as exc:
        raise TypstRenderError(
            exc.message,
            status_code=exc.status_code,
            error_code=exc.error_code,
            details={
                "validation_errors": exc.violations,
                "retry_attempted": False,
                "fitter_model": None,
                "char_metrics": exc.char_metrics,
                "section_counts": exc.section_counts,
                "warnings": [],
            },
        ) from exc

    render_id = _build_typst_render_id()
    typ_path = _ARTIFACTS_DIR / f"render_{render_id}.typ"
    pdf_path = _ARTIFACTS_DIR / f"render_{render_id}.pdf"

    try:
        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        typ_source, warnings = _build_typst_source(typst_payload, typ_path=typ_path)
        typ_path.write_text(typ_source, encoding="utf-8")
    except TypstRenderError:
        raise
    except OSError as exc:
        raise TypstRenderError("Typst artifact write failed.", status_code=500) from exc

    typst_binary = _resolve_typst_binary()
    if typst_binary is None:
        raise TypstRenderError(
            "Typst binary was not found. Set TYPST_BINARY_PATH or install typst in PATH.",
            status_code=503,
        )

    command = [typst_binary, "compile", str(typ_path), str(pdf_path)]
    try:
        completed_process = subprocess.run(
            command,
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=_TYPST_RENDER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise TypstRenderError("Typst PDF compilation timed out.", status_code=504) from exc
    except OSError as exc:
        raise TypstRenderError("Typst PDF compilation could not be started.", status_code=502) from exc

    if completed_process.returncode != 0:
        compile_detail = _trim_compile_output(completed_process.stderr or completed_process.stdout)
        message = "Typst PDF compilation failed."
        if compile_detail:
            message = f"{message} {compile_detail}"
        raise TypstRenderError(message, status_code=502)

    if not pdf_path.exists():
        raise TypstRenderError("Typst PDF artifact was not generated.", status_code=502)

    layout_metrics = None
    render_warnings = list(warnings)
    try:
        layout_metrics = analyze_typst_pdf_layout(pdf_path)
    except TypstPdfLayoutAnalysisError as exc:
        render_warnings.append(f"PDF layout analysis failed: {exc}")

    return TypstRenderResponse(
        status="completed",
        message="Typst render completed.",
        render_id=render_id,
        template_name=typst_payload.template_name,
        typ_source_artifact=_build_typst_artifact_ref(
            typ_path,
            artifact_type="typst_source",
            media_type="text/x-typst",
        ),
        pdf_artifact=_build_typst_artifact_ref(
            pdf_path,
            artifact_type="pdf",
            media_type="application/pdf",
        ),
        layout_metrics=layout_metrics,
        warnings=render_warnings,
    )


def fit_typst_payload_to_page(request: TypstFitToPageRequest) -> TypstFitToPageResponse:
    """Generate, merge and validate an explicit fit-to-page patch for a TypstPayload."""

    request = _attach_typst_fit_to_page_source_evidence(request)
    source_evidence_debug = _build_typst_source_evidence_debug(request.source_evidence_pack)

    try:
        fit_result = generate_typst_fit_to_page_patch_with_openai(request)
    except TypstFitToPageOpenAIError as exc:
        raise TypstFitToPageError(
            exc.message,
            status_code=exc.status_code,
            details={
                "validation_errors": [],
                "changed_fields": [],
                "char_metrics": {},
                "warnings": [],
                **source_evidence_debug,
                **exc.details,
            },
        ) from exc

    patch = fit_result.patch
    retry_attempted = False
    retry_feedback: str | None = None
    initial_validation_errors: list[str] = []
    changed_fields: list[str] = []
    try:
        merged_payload, changed_fields = _merge_typst_fit_to_page_patch(request.typst_payload, patch)
        _validate_fit_to_page_immutable_fields(request.typst_payload, merged_payload)
        section_counts, char_metrics = _validate_typst_payload(merged_payload)
    except TypstPayloadValidationError as exc:
        retry_attempted = True
        initial_validation_errors = list(exc.violations)
        retry_feedback = _build_fit_to_page_retry_feedback(exc)
        try:
            fit_result = generate_typst_fit_to_page_patch_with_openai(
                request,
                retry_feedback=retry_feedback,
            )
        except TypstFitToPageOpenAIError as retry_exc:
            raise TypstFitToPageError(
                retry_exc.message,
                status_code=retry_exc.status_code,
                details={
                    "validation_errors": exc.violations,
                    "changed_fields": [],
                    "char_metrics": exc.char_metrics,
                    "section_counts": exc.section_counts,
                    "retry_attempted": True,
                    "retry_feedback": retry_feedback,
                    "initial_validation_errors": initial_validation_errors,
                    "warnings": patch.warnings,
                    **source_evidence_debug,
                    **retry_exc.details,
                },
            ) from retry_exc

        patch = fit_result.patch
        changed_fields = []
        try:
            merged_payload, changed_fields = _merge_typst_fit_to_page_patch(request.typst_payload, patch)
            _validate_fit_to_page_immutable_fields(request.typst_payload, merged_payload)
            section_counts, char_metrics = _validate_typst_payload(merged_payload)
        except TypstPayloadValidationError as retry_validation_exc:
            raise TypstFitToPageError(
                "Typst fit-to-page failed after corrective retry.",
                status_code=retry_validation_exc.status_code,
                details={
                    "validation_errors": retry_validation_exc.violations,
                    "changed_fields": changed_fields,
                    "char_metrics": retry_validation_exc.char_metrics,
                    "section_counts": retry_validation_exc.section_counts,
                    "retry_attempted": True,
                    "retry_feedback": retry_feedback,
                    "initial_validation_errors": initial_validation_errors,
                    "warnings": patch.warnings,
                    **source_evidence_debug,
                },
            ) from retry_validation_exc
        except TypstFitToPageError as retry_patch_exc:
            retry_patch_exc.details = {
                **retry_patch_exc.details,
                "retry_attempted": True,
                "retry_feedback": retry_feedback,
                "initial_validation_errors": initial_validation_errors,
            }
            raise
    except TypstFitToPageError:
        raise

    warnings = list(patch.warnings)
    if retry_attempted:
        warnings.append("Corrective fit-to-page retry was attempted after initial validation failed.")
    if not changed_fields:
        warnings.append("Fit-to-page patch did not change any allowed payload fields.")

    return TypstFitToPageResponse(
        patch=patch,
        typst_payload=merged_payload,
        fit_debug=TypstFitToPageDebug(
            model=fit_result.model_name,
            changed_sections=_collect_changed_sections(changed_fields),
            changed_fields=changed_fields,
            rationale=patch.rationale,
            retry_attempted=retry_attempted,
            retry_feedback=retry_feedback,
            initial_validation_errors=initial_validation_errors,
            warnings=warnings,
            char_metrics=char_metrics,
            section_counts=section_counts,
            source_evidence_pack_built=source_evidence_debug["source_evidence_pack_built"],
            source_evidence_pack_used=source_evidence_debug["source_evidence_pack_used"],
            source_evidence_entry_counts=source_evidence_debug["source_evidence_entry_counts"],
            source_evidence_low_confidence_entries=source_evidence_debug[
                "source_evidence_low_confidence_entries"
            ],
            source_evidence_mapping_warnings=source_evidence_debug["source_evidence_mapping_warnings"],
        ),
    )


def save_typst_photo_asset(
    *,
    original_filename: str,
    content_type: str | None,
    content: bytes,
) -> TypstPhotoUploadResponse:
    """Validate and store one uploaded photo asset for later Typst rendering."""

    suffix = Path(original_filename or "").suffix.lower()
    if suffix not in _ALLOWED_PHOTO_EXTENSIONS:
        raise TypstArtifactError("Unsupported photo file extension. Use .jpg, .jpeg or .png.")

    normalized_content_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_content_type:
        allowed_suffixes = _ALLOWED_PHOTO_CONTENT_TYPES.get(normalized_content_type)
        if allowed_suffixes is None or suffix not in allowed_suffixes:
            raise TypstArtifactError("Unsupported photo content type. Use JPEG or PNG.")

    if not content:
        raise TypstArtifactError("Uploaded photo is empty.")
    if len(content) > _MAX_PHOTO_UPLOAD_BYTES:
        raise TypstArtifactError("Uploaded photo is too large. Maximum size is 5 MB.", status_code=413)

    photo_asset_id = f"photo_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}{suffix}"
    uploads_dir = _get_photo_uploads_dir()
    photo_path = uploads_dir / photo_asset_id

    try:
        uploads_dir.mkdir(parents=True, exist_ok=True)
        photo_path.write_bytes(content)
    except OSError as exc:
        raise TypstArtifactError("Photo upload could not be saved.", status_code=500) from exc

    return TypstPhotoUploadResponse(
        photo_asset_id=photo_asset_id,
        photo_artifact=_build_typst_artifact_ref(
            photo_path,
            artifact_type="photo_asset",
            media_type=normalized_content_type or _guess_photo_media_type(suffix),
        ),
    )


def resolve_typst_render_artifact(
    *,
    render_id: str,
    artifact_type: str,
) -> tuple[Path, str]:
    """Resolve a generated .typ or .pdf artifact from safe route parameters."""

    cleaned_render_id = (render_id or "").strip()
    cleaned_artifact_type = (artifact_type or "").strip().lower()

    if not _RENDER_ID_PATTERN.fullmatch(cleaned_render_id):
        raise TypstArtifactError("Invalid render_id.")

    artifact_extension_by_type = {
        "typ": (".typ", "text/plain"),
        "pdf": (".pdf", "application/pdf"),
    }
    if cleaned_artifact_type not in artifact_extension_by_type:
        raise TypstArtifactError("Invalid artifact type. Use 'typ' or 'pdf'.")

    extension, media_type = artifact_extension_by_type[cleaned_artifact_type]
    artifact_path = _safe_child_path(
        _ARTIFACTS_DIR,
        f"render_{cleaned_render_id}{extension}",
    )
    if not artifact_path.exists() or not artifact_path.is_file():
        raise TypstArtifactError("Requested Typst artifact was not found.", status_code=404)

    return artifact_path, media_type


def _build_typst_render_id() -> str:
    """Build a stable, sortable render identifier with a short collision guard."""

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{secrets.token_hex(2)}"


def _build_typst_source(
    typst_payload: TypstPayload,
    *,
    typ_path: Path,
) -> tuple[str, list[str]]:
    """Build a complete Typst document from an already prepared TypstPayload."""

    language_key = typst_payload.language.value
    labels = _SECTION_LABELS[language_key]
    consent_text = _resolve_consent_text(typst_payload)
    photo_path, warnings = _resolve_photo_asset_for_render(typst_payload, typ_path=typ_path)

    source_parts = [
        _build_typst_preamble(labels, consent_text),
        _build_typst_header_source(typst_payload, labels, photo_path),
        _wrap_typst_section(
            labels["summary"],
            f"#render-text({_typst_string(typst_payload.summary_text)})",
        ),
    ]

    education_source = _build_education_section_source(typst_payload.education_entries, labels)
    if education_source:
        source_parts.append(_wrap_typst_section(labels["education"], education_source))

    experience_source = _build_experience_section_source(typst_payload.experience_entries)
    if experience_source:
        source_parts.append(_wrap_typst_section(labels["experience"], experience_source))

    project_source = _build_project_section_source(typst_payload.project_entries)
    if project_source:
        source_parts.append(_wrap_typst_section(labels["projects"], project_source))

    skill_source = _build_text_list_source(typst_payload.skill_entries)
    if skill_source:
        source_parts.append(_wrap_typst_section(labels["skills"], skill_source))

    language_certificate_source = _build_text_list_source(typst_payload.language_certificate_entries)
    if language_certificate_source:
        source_parts.append(_wrap_typst_section(labels["languages"], language_certificate_source))

    source_parts.append(_build_consent_source())

    return "\n\n".join(part for part in source_parts if part.strip()) + "\n", warnings


def _build_typst_preamble(labels: dict[str, str], consent_text: str | None) -> str:
    """Return static Typst layout helpers plus dynamic labels that are safe to compile."""

    return "\n".join(
        [
            "// Generated Typst source from resume-agent. You may copy or edit this artifact manually if needed.",
            '#set page(paper: "a4", margin: (top: 0.68cm, bottom: 0.72cm, left: 1.05cm, right: 1.05cm))',
            "#set text(",
            '  font: ("Calibri", "Carlito", "Arial", "Liberation Sans", "DejaVu Sans"),',
            "  size: 10.6pt,",
            ")",
            "#set par(justify: false, leading: 0.68em)",
            "#set list(tight: true)",
            "",
            "#let header_height = 3.45cm",
            "#let no_photo_header_top_offset = 0.82cm",
            f"#let thesis_label = {_typst_string(labels['thesis'])}",
            f"#let consent_text = {_typst_optional_string(consent_text)}",
            "",
            "#let render-text(value) = [#value]",
            "",
            "#let section(title) = [",
            "  #v(0.03cm)",
            "  #grid(",
            "    columns: (1fr,),",
            "    row-gutter: 0.05cm,",
            "    [#text(size: 13.2pt, weight: \"bold\", bottom-edge: \"bounds\")[#title]],",
            "    [#line(length: 100%, stroke: 0.6pt)],",
            "  )",
            "  #v(0.012cm)",
            "]",
            "",
            "#let dated-line(lhs, rhs) = [",
            "  #block[",
            "    #grid(",
            "      columns: (1fr, auto),",
            "      column-gutter: 0.4cm,",
            "      align: (left, right),",
            "      lhs,",
            "      rhs,",
            "    )",
            "  ]",
            "]",
        ]
    )


def _build_typst_header_source(
    typst_payload: TypstPayload,
    labels: dict[str, str],
    photo_path: str | None,
) -> str:
    """Build the Typst header, omitting LinkedIn/GitHub lines when values are empty."""

    profile = typst_payload.profile
    display_full_name = (profile.full_name or "").strip().upper()
    linkedin_source = _build_optional_header_link_source(
        labels["linkedin"],
        profile.linkedin,
        indent="          ",
    )
    github_source = _build_optional_header_link_source(
        labels["github"],
        profile.github,
        indent="          ",
    )
    header_text = "\n".join(
        [
            f"          #text(size: 21pt, weight: \"bold\")[#render-text({_typst_string(display_full_name)})]",
            "          #v(0.07cm)",
            "          #text(size: 9.9pt)[",
            f"            #strong[{labels['email']}] #render-text({_typst_string(profile.email)})   |   #strong[{labels['phone']}] #render-text({_typst_string(profile.phone)})",
            "          ]",
            linkedin_source,
            github_source,
        ]
    ).rstrip()

    if photo_path is not None:
        return "\n".join(
            [
                "#block(height: header_height)[",
                "  #grid(",
                "    columns: (1fr, 3.1cm),",
                "    column-gutter: 0.28cm,",
                "    align: (left, top),",
                "    [",
                "      #v(0.02cm)",
                header_text,
                "    ],",
                "    [",
                "      #align(right)[",
                f"        #image({_typst_string(photo_path)}, width: 2.75cm, height: 3.45cm, fit: \"cover\")",
                "      ]",
                "    ],",
                "  )",
                "]",
            ]
        )

    return "\n".join(
        [
            "#block(height: header_height)[",
            "  #pad(top: no_photo_header_top_offset)[",
            "    #align(center)[",
            header_text,
            "    ]",
            "  ]",
            "]",
        ]
    )


def _build_optional_header_link_source(label: str, value: str | None, *, indent: str) -> str:
    """Return one optional contact line, or an empty string when the value is absent."""

    cleaned_value = (value or "").strip()
    if not cleaned_value:
        return ""

    return "\n".join(
        [
            f"{indent}#v(0.015cm)",
            f"{indent}#text(size: 9.9pt)[",
            f"{indent}  #strong[{label}] #render-text({_typst_string(cleaned_value)})",
            f"{indent}]",
        ]
    )


def _wrap_typst_section(title: str, body: str) -> str:
    """Wrap an already generated Typst body with a section heading."""

    return "\n".join(
        [
            f"#section({_typst_string(title)})",
            body.strip(),
        ]
    )


def _build_education_section_source(
    entries: list[TypstEducationEntry],
    labels: dict[str, str],
) -> str:
    """Render education entries including an optional thesis line."""

    entry_sources: list[str] = []
    for entry in entries:
        entry_lines = [
            "#dated-line(",
            f"  [#text(weight: \"bold\")[#render-text({_typst_string(entry.institution)})]],",
            f"  [#render-text({_typst_string(entry.date)})],",
            ")",
        ]
        if (entry.degree or "").strip():
            entry_lines.append(f"#render-text({_typst_string(entry.degree)})")
        if (entry.thesis or "").strip():
            entry_lines.extend(
                [
                    "#v(0.01cm)",
                    (
                        f"#emph[#render-text({_typst_string(labels['thesis'])}) "
                        f"#render-text({_typst_string(entry.thesis)})]"
                    ),
                ]
            )
        entry_sources.append("\n".join(entry_lines))

    return "\n#v(0.03cm)\n".join(entry_sources)


def _build_experience_section_source(entries: list[TypstExperienceEntry]) -> str:
    """Render experience entries with compact bullet lists."""

    entry_sources: list[str] = []
    for entry in entries:
        role_source = ""
        if (entry.role or "").strip():
            role_source = f" — #emph[#render-text({_typst_string(entry.role)})]"

        entry_lines = [
            "#dated-line(",
            f"  [#text(weight: \"bold\")[#render-text({_typst_string(entry.company)})]{role_source}],",
            f"  [#render-text({_typst_string(entry.date)})],",
            ")",
        ]
        bullet_source = _build_text_list_source(entry.bullets)
        if bullet_source:
            entry_lines.append(bullet_source)
        entry_sources.append("\n".join(entry_lines))

    return "\n#v(0.035cm)\n".join(entry_sources)


def _build_project_section_source(entries: list[TypstProjectEntry]) -> str:
    """Render project entries as a compact list."""

    item_sources: list[str] = []
    for entry in entries:
        source = f"#text(weight: \"bold\")[#render-text({_typst_string(entry.name)})]"
        if (entry.description or "").strip():
            source = f"{source} — #render-text({_typst_string(entry.description)})"
        item_sources.append(source)
    return _build_list_source(item_sources)


def _build_text_list_source(values: list[str]) -> str:
    """Render simple text values as a Typst list."""

    return _build_list_source(
        [f"#render-text({_typst_string(value)})" for value in values if (value or "").strip()]
    )


def _build_list_source(item_sources: list[str]) -> str:
    """Build a Typst list call from item snippets."""

    if not item_sources:
        return ""

    item_blocks = []
    for item_source in item_sources:
        indented_source = "    " + item_source.replace("\n", "\n    ")
        item_blocks.append(f"  [\n{indented_source}\n  ],")

    return "\n".join(["#list(", *item_blocks, ")"])


def _build_consent_source() -> str:
    """Render consent text only when a consent string is available."""

    return "\n".join(
        [
            "#if consent_text != none [",
            "  #place(bottom + center, dy: -0.12cm)[",
            "    #text(size: 8pt)[",
            "      #render-text(consent_text)",
            "    ]",
            "  ]",
            "]",
        ]
    )


def _resolve_consent_text(typst_payload: TypstPayload) -> str | None:
    """Resolve the consent clause from TypstPayload options."""

    consent_mode = typst_payload.consent_mode.value
    if consent_mode == "none":
        return None
    if consent_mode == "custom":
        custom_consent_text = (typst_payload.custom_consent_text or "").strip()
        if not custom_consent_text:
            raise TypstRenderError("custom_consent_text is required when consent_mode='custom'.")
        return custom_consent_text
    return _DEFAULT_CONSENT_TEXT[typst_payload.language.value]


def _resolve_photo_asset_for_render(
    typst_payload: TypstPayload,
    *,
    typ_path: Path,
) -> tuple[str | None, list[str]]:
    """Resolve an uploaded photo asset for Typst rendering."""

    if not typst_payload.include_photo:
        return None, []

    photo_asset_id = (typst_payload.photo_asset_id or "").strip()
    if not photo_asset_id:
        raise TypstRenderError(
            "Photo rendering was requested, but photo_asset_id is missing.",
            status_code=400,
        )

    try:
        photo_path = _resolve_photo_asset_path(photo_asset_id)
    except TypstArtifactError as exc:
        raise TypstRenderError(exc.message, status_code=exc.status_code) from exc

    if not photo_path.exists() or not photo_path.is_file():
        raise TypstRenderError(
            "Photo rendering was requested, but the uploaded photo asset was not found.",
            status_code=404,
        )

    relative_photo_path = os.path.relpath(photo_path, start=typ_path.parent)
    return relative_photo_path.replace(os.sep, "/"), []


def _resolve_typst_binary() -> str | None:
    """Resolve the Typst executable from env, PATH, then the common snap path."""

    env_path = (os.environ.get("TYPST_BINARY_PATH") or "").strip()
    if env_path:
        expanded_path = Path(env_path).expanduser()
        if expanded_path.is_file() and os.access(expanded_path, os.X_OK):
            return str(expanded_path)
        resolved_command = shutil.which(env_path)
        if resolved_command:
            return resolved_command

    path_binary = shutil.which("typst")
    if path_binary:
        return path_binary

    if _SNAP_TYPST_BINARY.is_file() and os.access(_SNAP_TYPST_BINARY, os.X_OK):
        return str(_SNAP_TYPST_BINARY)

    return None


def _build_typst_artifact_ref(
    artifact_path: Path,
    *,
    artifact_type: str,
    media_type: str,
) -> TypstArtifactRef:
    """Build public artifact metadata without requiring absolute paths in the API contract."""

    return TypstArtifactRef(
        artifact_type=artifact_type,
        filename=artifact_path.name,
        relative_path=_relative_artifact_path(artifact_path),
        absolute_path=None,
        media_type=media_type,
        size_bytes=artifact_path.stat().st_size if artifact_path.exists() else None,
    )


def _resolve_photo_asset_path(photo_asset_id: str) -> Path:
    """Resolve one uploaded photo asset ID to a safe local path."""

    cleaned_photo_asset_id = (photo_asset_id or "").strip()
    if not _PHOTO_ASSET_ID_PATTERN.fullmatch(cleaned_photo_asset_id):
        raise TypstArtifactError("Invalid photo_asset_id.")
    return _safe_child_path(_get_photo_uploads_dir(), cleaned_photo_asset_id)


def _get_photo_uploads_dir() -> Path:
    """Return the local controlled upload directory tied to the active artifacts root."""

    return _ARTIFACTS_DIR / "uploads"


def _safe_child_path(parent_dir: Path, child_name: str) -> Path:
    """Build a child path and verify that it stays inside the controlled parent directory."""

    candidate_path = (parent_dir / child_name).resolve()
    parent_path = parent_dir.resolve()
    try:
        candidate_path.relative_to(parent_path)
    except ValueError as exc:
        raise TypstArtifactError("Invalid artifact path.") from exc
    return candidate_path


def _guess_photo_media_type(suffix: str) -> str:
    """Return a basic media type for a validated photo suffix."""

    if suffix == ".png":
        return "image/png"
    return "image/jpeg"


def _relative_artifact_path(artifact_path: Path) -> str:
    """Return a project-relative artifact path when possible."""

    try:
        return artifact_path.resolve().relative_to(_PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return artifact_path.name


def _typst_string(value: str | None) -> str:
    """Serialize one Python string as a Typst string literal."""

    normalized_value = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return json.dumps(normalized_value, ensure_ascii=False)


def _typst_optional_string(value: str | None) -> str:
    """Serialize an optional string as a Typst string literal or none."""

    if value is None:
        return "none"
    return _typst_string(value)


def _trim_compile_output(value: str | None) -> str:
    """Return a bounded single-line compile error summary."""

    cleaned_value = " ".join((value or "").split())
    return cleaned_value[:500]


def resolve_typst_prepare_source(request: TypstPrepareRequest) -> ResolvedTypstPrepareSource:
    """Resolve a stored or inline final resume draft into one normalized Typst source."""

    if request.draft_id is not None:
        return _resolve_stored_resume_draft_source(
            request.draft_id,
            request.draft_variant,
        )

    return _resolve_inline_resume_draft_source(
        request.final_resume_draft,
        request.candidate_profile_id,
    )


def _resolve_stored_resume_draft_source(
    draft_id: int,
    draft_variant: TypstDraftVariant | None,
) -> ResolvedTypstPrepareSource:
    """Resolve one stored base/refined resume draft from SQLite."""

    stored_record = get_resume_draft(draft_id)
    if stored_record is None:
        raise TypstPrepareSourceError("Stored resume draft not found.", status_code=404)
    if draft_variant is None:
        raise TypstPrepareSourceError("draft_variant is required when draft_id is provided.")

    warnings: list[str] = []

    if draft_variant is TypstDraftVariant.BASE:
        base_artifacts = stored_record.get("base_resume_artifacts")
        if not isinstance(base_artifacts, dict) or "resume_draft" not in base_artifacts:
            raise TypstPrepareSourceError(
                "Stored base resume draft is unavailable or malformed.",
                status_code=500,
            )
        resume_draft = ResumeDraft.model_validate(base_artifacts["resume_draft"])
    else:
        refined_artifacts = stored_record.get("refined_resume_artifacts")
        if not isinstance(refined_artifacts, dict) or "refined_resume_draft" not in refined_artifacts:
            raise TypstPrepareSourceError(
                "Requested refined draft variant is not available for this stored draft."
            )
        resume_draft = ResumeDraft.model_validate(refined_artifacts["refined_resume_draft"])

    candidate_profile = None
    candidate_profile_id = stored_record.get("candidate_profile_id")
    if candidate_profile_id is None:
        warnings.append(
            "Stored draft does not reference a candidate profile ID, so prepare used draft-only fallback data where needed.",
        )
    else:
        stored_profile = get_candidate_profile(candidate_profile_id)
        if stored_profile is None:
            warnings.append(
                "Stored candidate profile linked to this draft was not found, so prepare used draft-only fallback data where needed.",
            )
        else:
            candidate_profile = stored_profile["payload"]

    return ResolvedTypstPrepareSource(
        resume_draft=resume_draft,
        candidate_profile=candidate_profile,
        source_mode="draft_id",
        draft_variant=draft_variant,
        stored_resume_draft_id=draft_id,
        candidate_profile_id=candidate_profile_id,
        warnings=warnings,
    )


def _resolve_inline_resume_draft_source(
    final_resume_draft: ResumeDraft | None,
    candidate_profile_id: int | None,
) -> ResolvedTypstPrepareSource:
    """Resolve one inline final draft together with its candidate profile reference."""

    if final_resume_draft is None:
        raise TypstPrepareSourceError("final_resume_draft is required for inline Typst prepare.")
    if candidate_profile_id is None:
        raise TypstPrepareSourceError(
            "candidate_profile_id is required when final_resume_draft is provided."
        )

    stored_profile = get_candidate_profile(candidate_profile_id)
    if stored_profile is None:
        raise TypstPrepareSourceError(
            "Candidate profile not found for the provided inline Typst source.",
            status_code=404,
        )

    return ResolvedTypstPrepareSource(
        resume_draft=final_resume_draft,
        candidate_profile=stored_profile["payload"],
        source_mode="inline_draft",
        draft_variant=None,
        stored_resume_draft_id=None,
        candidate_profile_id=candidate_profile_id,
        warnings=[],
    )


def _attach_typst_fit_to_page_source_evidence(
    request: TypstFitToPageRequest,
) -> TypstFitToPageRequest:
    """Attach deterministic stored-draft evidence when the request carries source context."""

    if request.source_evidence_pack is not None:
        return request

    source_draft_id = request.stored_resume_draft_id or request.draft_id
    if source_draft_id is None:
        return request

    try:
        resolved_source = _resolve_stored_resume_draft_source(
            source_draft_id,
            request.draft_variant,
        )
    except TypstPrepareSourceError as exc:
        raise TypstFitToPageError(
            exc.message,
            status_code=exc.status_code,
            details={
                "validation_errors": [],
                "changed_fields": [],
                "char_metrics": {},
                "warnings": [],
                "source_evidence_pack_built": False,
                "source_evidence_pack_used": False,
                "source_evidence_entry_counts": {},
                "source_evidence_low_confidence_entries": [],
                "source_evidence_mapping_warnings": [exc.message],
            },
        ) from exc

    source_evidence_pack = build_typst_source_evidence_pack(
        request.typst_payload,
        resolved_source,
    )
    return request.model_copy(
        update={"source_evidence_pack": source_evidence_pack},
        deep=True,
    )


def build_typst_source_evidence_pack(
    typst_payload: TypstPayload,
    resolved_source: ResolvedTypstPrepareSource,
) -> TypstSourceEvidencePack:
    """Build a bounded runtime evidence pack for entries already present in TypstPayload."""

    resume_draft = resolved_source.resume_draft
    candidate_profile = resolved_source.candidate_profile
    mapping_warnings = list(resolved_source.warnings)

    experience_items = _build_typst_experience_evidence_items(
        typst_payload,
        resume_draft,
        candidate_profile,
        mapping_warnings,
    )
    project_items = _build_typst_project_evidence_items(
        typst_payload,
        resume_draft,
        candidate_profile,
        mapping_warnings,
    )
    summary_context = _build_typst_summary_evidence_item(resume_draft, candidate_profile)
    concept_grounding = _build_typst_concept_grounding(
        experience_items,
        project_items,
        candidate_profile,
    )

    return TypstSourceEvidencePack(
        experience_items=experience_items,
        project_items=project_items,
        summary_context=summary_context,
        concept_grounding=concept_grounding,
        mapping_warnings=mapping_warnings,
        token_budget_notes=[
            f"Experience evidence limited to {_SOURCE_EVIDENCE_MAX_EXPERIENCE} payload entries.",
            f"Project evidence limited to {_SOURCE_EVIDENCE_MAX_PROJECTS} payload entries.",
            (
                "Per-entry evidence is capped at 3 responsibilities, 3 achievements/outcomes, "
                "8 technologies/keywords and short source highlights."
            ),
        ],
    )


def _build_typst_experience_evidence_items(
    typst_payload: TypstPayload,
    resume_draft: ResumeDraft,
    candidate_profile: CandidateProfile | None,
    mapping_warnings: list[str],
) -> list[TypstSourceEvidenceItem]:
    """Map Typst experience entries back to draft/profile source evidence."""

    source_lookup = _build_profile_experience_lookup(candidate_profile)
    source_key_lookup = _build_profile_experience_key_lookup(candidate_profile)
    source_skill_terms = _build_skill_term_category_lookup(candidate_profile)
    draft_entries = resume_draft.selected_experience_entries
    draft_lookup = _build_resume_experience_evidence_lookup(draft_entries)
    evidence_items: list[TypstSourceEvidenceItem] = []

    for payload_index, payload_entry in enumerate(
        typst_payload.experience_entries[:_SOURCE_EVIDENCE_MAX_EXPERIENCE]
    ):
        draft_entry, match_note = _match_typst_experience_entry(payload_entry, draft_entries, draft_lookup)
        source_entry = None
        source_id = None
        match_confidence: Literal["high", "medium", "low"] = "low"
        warnings: list[str] = []

        if draft_entry is not None:
            source_id = (draft_entry.source_experience_id or "").strip() or None
            if source_id:
                source_entry = source_lookup.get(source_id)
            if source_entry is None:
                fallback_key = _normalize_experience_key(draft_entry.company_name, draft_entry.position_title)
                source_entry = source_key_lookup.get(fallback_key)
                if source_entry is not None:
                    source_id = source_entry.id
                    warnings.append("Profile source entry matched by normalized company and role fallback.")
            match_confidence = "high" if source_entry is not None else "medium"
            if source_id and source_entry is None:
                warnings.append("Draft source_experience_id was present but the profile source entry was not found.")
        else:
            warning = (
                f"Low-confidence experience evidence mapping for payload index {payload_index}: "
                f"{payload_entry.company} / {payload_entry.role}."
            )
            warnings.append(warning)
            mapping_warnings.append(warning)

        responsibilities = _trim_evidence_list(
            source_entry.responsibilities if source_entry is not None else [],
            _SOURCE_EVIDENCE_MAX_RESPONSIBILITIES,
        )
        achievements = _trim_evidence_list(
            source_entry.achievements if source_entry is not None else [],
            _SOURCE_EVIDENCE_MAX_ACHIEVEMENTS,
        )
        technologies = _trim_evidence_list(
            source_entry.technologies_used if source_entry is not None else [],
            _SOURCE_EVIDENCE_MAX_TECH_TERMS,
        )
        keywords = _trim_evidence_list(
            [
                *(source_entry.keywords if source_entry is not None else []),
                *(draft_entry.highlighted_keywords if draft_entry is not None else []),
            ],
            _SOURCE_EVIDENCE_MAX_TECH_TERMS,
        )
        source_highlights = _trim_evidence_list(
            [
                *(draft_entry.source_highlights if draft_entry is not None else []),
                *(draft_entry.relevance_note.splitlines() if draft_entry and draft_entry.relevance_note else []),
            ],
            _SOURCE_EVIDENCE_MAX_HIGHLIGHTS,
        )
        constraints = [
            "Do not overstate seniority, ownership, scope, metrics or business impact.",
            "Do not create new tool-language-standard-task-outcome relationships beyond this evidence.",
        ]
        if match_confidence == "low":
            constraints.append("Low-confidence mapping: prefer current payload wording or leave unchanged.")

        evidence_items.append(
            TypstSourceEvidenceItem(
                entry_type="experience",
                payload_index=payload_index,
                source_id=source_id,
                match_confidence=match_confidence,
                title=_truncate_evidence_text(payload_entry.role or (draft_entry.position_title if draft_entry else "")),
                organization=_truncate_evidence_text(
                    payload_entry.company or (draft_entry.company_name if draft_entry else "")
                ),
                role=_truncate_evidence_text(payload_entry.role or (draft_entry.position_title if draft_entry else "")),
                date=_truncate_evidence_text(payload_entry.date or (draft_entry.date_range if draft_entry else "")),
                responsibilities=responsibilities,
                achievements=achievements,
                technologies=technologies,
                keywords=_annotate_skill_terms(keywords, source_skill_terms),
                source_highlights=source_highlights,
                outcomes=achievements,
                constraints=constraints,
                warnings=[*warnings, *([match_note] if match_note else [])],
            )
        )

    return evidence_items


def _build_typst_project_evidence_items(
    typst_payload: TypstPayload,
    resume_draft: ResumeDraft,
    candidate_profile: CandidateProfile | None,
    mapping_warnings: list[str],
) -> list[TypstSourceEvidenceItem]:
    """Map Typst project entries back to draft/profile source evidence."""

    source_lookup = _build_profile_project_lookup(candidate_profile)
    source_name_lookup = _build_profile_project_name_lookup(candidate_profile)
    source_skill_terms = _build_skill_term_category_lookup(candidate_profile)
    draft_lookup = _build_resume_project_evidence_lookup(resume_draft.selected_project_entries)
    evidence_items: list[TypstSourceEvidenceItem] = []

    for payload_index, payload_entry in enumerate(typst_payload.project_entries[:_SOURCE_EVIDENCE_MAX_PROJECTS]):
        project_key = _normalize_project_name_key(payload_entry.name)
        draft_entry = draft_lookup.get(project_key)
        source_entry = None
        source_id = None
        match_confidence: Literal["high", "medium", "low"] = "low"
        warnings: list[str] = []

        if draft_entry is not None:
            source_id = (draft_entry.source_project_id or "").strip() or None
            if source_id:
                source_entry = source_lookup.get(source_id)
            if source_entry is None:
                source_entry = source_name_lookup.get(project_key)
                if source_entry is not None:
                    source_id = source_entry.id
                    warnings.append("Profile source entry matched by normalized project-name fallback.")
            match_confidence = "high" if source_entry is not None else "medium"
            if source_id and source_entry is None:
                warnings.append("Draft source_project_id was present but the profile source entry was not found.")
        else:
            warning = f"Low-confidence project evidence mapping for payload index {payload_index}: {payload_entry.name}."
            warnings.append(warning)
            mapping_warnings.append(warning)

        source_description = []
        if source_entry is not None:
            source_description.append(source_entry.description)

        source_highlights = _trim_evidence_list(
            [
                *source_description,
                *(draft_entry.source_highlights if draft_entry is not None else []),
                *(draft_entry.relevance_note.splitlines() if draft_entry and draft_entry.relevance_note else []),
            ],
            _SOURCE_EVIDENCE_MAX_HIGHLIGHTS,
        )
        outcomes = _trim_evidence_list(
            source_entry.outcomes if source_entry is not None else [],
            _SOURCE_EVIDENCE_MAX_ACHIEVEMENTS,
        )
        technologies = _trim_evidence_list(
            source_entry.technologies_used if source_entry is not None else [],
            _SOURCE_EVIDENCE_MAX_TECH_TERMS,
        )
        keywords = _trim_evidence_list(
            [
                *(source_entry.keywords if source_entry is not None else []),
                *(draft_entry.highlighted_keywords if draft_entry is not None else []),
            ],
            _SOURCE_EVIDENCE_MAX_TECH_TERMS,
        )
        constraints = [
            "Do not invent production deployment, users, metrics, ownership or business impact.",
            "Do not create new relationships between technologies, methods, tasks and outcomes.",
        ]
        if match_confidence == "low":
            constraints.append("Low-confidence mapping: prefer current payload wording or leave unchanged.")

        evidence_items.append(
            TypstSourceEvidenceItem(
                entry_type="project",
                payload_index=payload_index,
                source_id=source_id,
                match_confidence=match_confidence,
                title=_truncate_evidence_text(payload_entry.name),
                organization=None,
                role=_truncate_evidence_text(draft_entry.role if draft_entry is not None else ""),
                date=None,
                responsibilities=[],
                achievements=[],
                technologies=technologies,
                keywords=_annotate_skill_terms(keywords, source_skill_terms),
                source_highlights=source_highlights,
                outcomes=outcomes,
                constraints=constraints,
                warnings=warnings,
            )
        )

    return evidence_items


def _build_typst_summary_evidence_item(
    resume_draft: ResumeDraft,
    candidate_profile: CandidateProfile | None,
) -> TypstSourceEvidenceItem | None:
    """Return only broad summary context, not a full source dump."""

    user_authored_summary = _normalize_visible_whitespace(
        candidate_profile.professional_summary_base if candidate_profile is not None else None
    )
    source_highlights = _trim_evidence_list(
        [
            f"User-authored profile summary: {user_authored_summary}" if user_authored_summary else "",
            resume_draft.professional_summary or "",
            resume_draft.fit_summary or "",
        ],
        3,
        max_chars=220,
    )
    keywords = _trim_evidence_list(
        [
            *(candidate_profile.target_roles if candidate_profile is not None else []),
            resume_draft.target_job_title or "",
        ],
        6,
        max_chars=80,
    )
    if not source_highlights and not keywords:
        return None

    return TypstSourceEvidenceItem(
        entry_type="summary",
        payload_index=None,
        source_id=None,
        match_confidence="high" if user_authored_summary else "medium",
        title=(
            "Summary source context; user-authored profile summary is the semantic source of truth"
            if user_authored_summary
            else "Summary source context"
        ),
        source_highlights=source_highlights,
        keywords=keywords,
        constraints=[
            (
                "If a user-authored profile summary is present, use it as the semantic source of truth for summary_text, not text to copy word for word."
                if user_authored_summary
                else "Use summary context only for broad profile direction."
            ),
            "Existing draft summary, fit summary and target role are secondary context only.",
            "Do not build summary_text from job keywords, projects, technologies or detailed source facts.",
            "Do not stuff detailed project, task, product or standard facts into summary_text.",
        ],
    )


def _build_resume_experience_evidence_lookup(
    draft_entries: list[ResumeExperienceEntry],
) -> dict[str, ResumeExperienceEntry]:
    """Build conservative draft-entry lookup keys used by the source evidence mapper."""

    lookup: dict[str, ResumeExperienceEntry] = {}
    for entry in draft_entries:
        keys = [
            _normalize_experience_evidence_key(entry.company_name, entry.position_title, entry.date_range),
            _normalize_experience_key(entry.company_name, entry.position_title),
        ]
        for key in keys:
            if key and key not in lookup:
                lookup[key] = entry
    return lookup


def _build_resume_project_evidence_lookup(
    draft_entries: list[ResumeProjectEntry],
) -> dict[str, ResumeProjectEntry]:
    """Build a draft project lookup by normalized project name."""

    lookup: dict[str, ResumeProjectEntry] = {}
    for entry in draft_entries:
        key = _normalize_project_name_key(entry.project_name)
        if key and key not in lookup:
            lookup[key] = entry
    return lookup


def _match_typst_experience_entry(
    payload_entry: TypstExperienceEntry,
    draft_entries: list[ResumeExperienceEntry],
    draft_lookup: dict[str, ResumeExperienceEntry],
) -> tuple[ResumeExperienceEntry | None, str | None]:
    """Find the best draft entry behind one rendered Typst experience entry."""

    full_key = _normalize_experience_evidence_key(
        payload_entry.company,
        payload_entry.role,
        payload_entry.date,
    )
    if full_key in draft_lookup:
        return draft_lookup[full_key], None

    short_key = _normalize_experience_key(payload_entry.company, payload_entry.role)
    if short_key in draft_lookup:
        return draft_lookup[short_key], "Mapped by company and role because the date range differed or was absent."

    for entry in draft_entries:
        if _normalize_experience_key(entry.company_name, entry.position_title) == short_key:
            return entry, "Mapped by fallback company and role scan."

    return None, None


def _normalize_experience_evidence_key(company: str | None, role: str | None, date_range: str | None) -> str:
    """Normalize company, role and date for payload-to-draft evidence matching."""

    return _normalize_fallback_dedupe_key(f"{company or ''} {role or ''} {date_range or ''}")


def _build_typst_concept_grounding(
    experience_items: list[TypstSourceEvidenceItem],
    project_items: list[TypstSourceEvidenceItem],
    candidate_profile: CandidateProfile | None,
) -> list[TypstConceptGrounding]:
    """Create generic, source-derived term guidance without external lookup."""

    skill_term_categories = _build_skill_term_category_lookup(candidate_profile)
    grounding: list[TypstConceptGrounding] = []
    seen_terms: set[str] = set()

    for item in [*experience_items, *project_items]:
        source_context = _format_evidence_item_context(item)
        for term in [*item.technologies, *item.keywords]:
            clean_term = _strip_evidence_annotation(term)
            normalized_term = _normalize_fallback_dedupe_key(clean_term)
            if not normalized_term or normalized_term in seen_terms:
                continue
            seen_terms.add(normalized_term)
            term_type = skill_term_categories.get(normalized_term)
            if term_type is None:
                term_type = "technology_or_tool" if term in item.technologies else "keyword_or_domain_term"
            confidence = item.match_confidence if item.match_confidence in {"high", "medium"} else "low"
            grounding.append(
                TypstConceptGrounding(
                    term=_truncate_evidence_text(clean_term, max_chars=80),
                    source_context=source_context,
                    term_type=_truncate_evidence_text(term_type, max_chars=80),
                    safe_usage="Use this term only in the source context where it appears.",
                    unsafe_usage=(
                        "Do not merge it with neighboring terms or claim a tool-language-standard-task-outcome "
                        "relationship unless the evidence states that relationship."
                    ),
                    relationship_notes="No external lookup was performed; preserve only relationships visible in evidence.",
                    confidence=confidence,
                    needs_external_verification=confidence == "low",
                    manual_review_reason=(
                        "Low-confidence source mapping; keep phrasing neutral or unchanged."
                        if confidence == "low"
                        else None
                    ),
                )
            )
            if len(grounding) >= _SOURCE_EVIDENCE_MAX_GROUNDING_TERMS:
                return grounding

    return grounding


def _build_skill_term_category_lookup(candidate_profile: CandidateProfile | None) -> dict[str, str]:
    """Return source skill categories for terms already present in the candidate profile."""

    if candidate_profile is None:
        return {}

    lookup: dict[str, str] = {}
    for skill in candidate_profile.skill_entries:
        category = _normalize_visible_whitespace(skill.category)
        for term in [skill.name, *skill.aliases]:
            normalized_term = _normalize_fallback_dedupe_key(term)
            if normalized_term and category and normalized_term not in lookup:
                lookup[normalized_term] = category
    return lookup


def _annotate_skill_terms(values: list[str], skill_term_categories: dict[str, str]) -> list[str]:
    """Add lightweight source category hints without changing the original term."""

    annotated_values: list[str] = []
    for value in values:
        normalized_value = _normalize_fallback_dedupe_key(value)
        category = skill_term_categories.get(normalized_value)
        if category:
            annotated_values.append(f"{value} (source category: {category})")
        else:
            annotated_values.append(value)
    return annotated_values


def _strip_evidence_annotation(value: str) -> str:
    """Remove local evidence annotations before producing concept grounding terms."""

    return re.sub(r"\s+\(source category: [^)]+\)$", "", value).strip()


def _format_evidence_item_context(item: TypstSourceEvidenceItem) -> str:
    """Format a compact source context label for concept grounding."""

    if item.entry_type == "experience":
        return " / ".join(
            value
            for value in [item.organization, item.role, item.date]
            if value
        )
    return item.title or item.entry_type


def _trim_evidence_list(
    values: list[str],
    limit: int,
    *,
    max_chars: int = _SOURCE_EVIDENCE_TEXT_LIMIT,
) -> list[str]:
    """Clean, dedupe and truncate evidence strings for token discipline."""

    cleaned_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        cleaned_value = _truncate_evidence_text(value, max_chars=max_chars)
        if not cleaned_value:
            continue
        normalized_value = _normalize_fallback_dedupe_key(cleaned_value)
        if normalized_value in seen_values:
            continue
        seen_values.add(normalized_value)
        cleaned_values.append(cleaned_value)
        if len(cleaned_values) >= limit:
            break
    return cleaned_values


def _truncate_evidence_text(value: str | None, *, max_chars: int = _SOURCE_EVIDENCE_TEXT_LIMIT) -> str | None:
    """Return one short evidence string suitable for a runtime prompt."""

    cleaned_value = _normalize_visible_whitespace(value)
    if not cleaned_value:
        return None
    if len(cleaned_value) <= max_chars:
        return cleaned_value
    return f"{cleaned_value[: max_chars - 1].rstrip()}…"


def _build_typst_source_evidence_debug(
    source_evidence_pack: TypstSourceEvidencePack | None,
) -> dict[str, Any]:
    """Build response-safe debug metadata for source evidence usage."""

    if source_evidence_pack is None:
        return {
            "source_evidence_pack_built": False,
            "source_evidence_pack_used": False,
            "source_evidence_entry_counts": {},
            "source_evidence_low_confidence_entries": [],
            "source_evidence_mapping_warnings": [],
        }

    evidence_items = [
        *source_evidence_pack.experience_items,
        *source_evidence_pack.project_items,
    ]
    low_confidence_entries = [
        _format_evidence_item_context(item)
        for item in evidence_items
        if item.match_confidence == "low"
    ]
    return {
        "source_evidence_pack_built": True,
        "source_evidence_pack_used": True,
        "source_evidence_entry_counts": {
            "experience": len(source_evidence_pack.experience_items),
            "projects": len(source_evidence_pack.project_items),
            "concept_grounding": len(source_evidence_pack.concept_grounding),
            "summary_context": 1 if source_evidence_pack.summary_context is not None else 0,
        },
        "source_evidence_low_confidence_entries": low_confidence_entries,
        "source_evidence_mapping_warnings": source_evidence_pack.mapping_warnings,
    }


def _build_typst_fitter_input_bundle(
    resolved_source: ResolvedTypstPrepareSource,
    options: TypstRenderOptions,
) -> TypstFitterInputBundle:
    """Build a compact draft-first evidence pack for the Typst fitter."""

    resume_draft = resolved_source.resume_draft
    candidate_profile = resolved_source.candidate_profile

    profile_assisted_sections: list[str] = []
    profile_fallback_source: dict[str, Any] = {}

    header_fallback = _build_profile_header_fallback(candidate_profile, resume_draft)
    if header_fallback:
        profile_fallback_source["header"] = header_fallback
        profile_assisted_sections.append("header")

    education_fallback = _build_profile_backed_education_entries_for_fitter(
        candidate_profile,
        language=options.language.value,
    )
    if education_fallback:
        profile_fallback_source["education_entries"] = [
            entry.model_dump(mode="json") for entry in education_fallback
        ]
        profile_assisted_sections.append("education")

    experience_fallback = _build_profile_fallback_experience_entries(
        resume_draft,
        candidate_profile,
    )
    if experience_fallback:
        profile_fallback_source["experience_entries"] = experience_fallback
        profile_assisted_sections.append("experience")

    project_fallback = _build_profile_fallback_project_entries(
        resume_draft,
        candidate_profile,
    )
    if project_fallback:
        profile_fallback_source["project_entries"] = [
            entry.model_dump(mode="json") for entry in project_fallback
        ]
        profile_assisted_sections.append("projects")

    skill_fallback = _build_profile_fallback_skill_entries(
        resume_draft,
        candidate_profile,
    )
    if skill_fallback:
        profile_fallback_source["skill_entries"] = skill_fallback
        profile_assisted_sections.append("skills")

    skill_source_material = _build_profile_skill_source_material(candidate_profile, resume_draft)
    if skill_source_material:
        profile_fallback_source["skill_source_material"] = skill_source_material
        if "skills" not in profile_assisted_sections:
            profile_assisted_sections.append("skills")

    language_certificate_fallback = _build_profile_fallback_language_certificate_entries(
        resume_draft,
        candidate_profile,
    )
    if language_certificate_fallback:
        profile_fallback_source["language_certificate_entries"] = language_certificate_fallback
        profile_assisted_sections.append("languages_certificates")

    payload = {
        "render_options": options.model_dump(mode="json"),
        "limit_config": TYPST_LIMIT_CONFIG,
        "source_priority_rules": [
            "ResumeDraft is the primary source for most CV sections.",
            "summary_text has its own source hierarchy: if primary_summary_source.user_authored_profile_summary_available is true, TypstPayload.summary_text must use primary_summary_source.user_authored_profile_summary as the semantic source of truth.",
            "For summary_text, user_authored_profile_summary outranks ResumeDraft.professional_summary, fit_summary, target role direction, projects, technologies, job keywords and job posting content.",
            "user_authored_profile_summary is the semantic source of truth for summary meaning, professional direction and key facts, not text to copy word for word.",
            "If user_authored_profile_summary exceeds the CV summary character budget, compress it; do not copy it verbatim if it would exceed limit_config.summary.hard_chars.",
            "Aim summary_text around limit_config.summary.target_chars (currently 370) and always within limit_config.summary.hard_chars (currently 390).",
            "Hard limit compliance has priority over exact wording.",
            "Projects, technologies, job keywords and job posting content are not primary sources for summary_text.",
            "Profile fallback data may be used when the corresponding draft field or section is missing, too sparse, underfilled or clearly lower quality, and only when it can be inserted naturally without inventing content.",
            "Use high-quality profile fallback as top-up candidates when the one-page CV has room and the profile data is specific, truthful and non-duplicative.",
            "Do not create a second CV-generation pass from the profile.",
            "Do not synthesize a new summary from job keywords, projects, technologies or job posting content.",
            "Use CV-friendly date ranges, not raw ISO dates.",
        ],
        "primary_summary_source": _build_typst_primary_summary_source(resume_draft, candidate_profile),
        "draft_primary_source": _build_typst_draft_primary_source(resume_draft, candidate_profile),
        "profile_fallback_source": profile_fallback_source,
    }

    return TypstFitterInputBundle(
        payload=payload,
        profile_assisted_sections=profile_assisted_sections,
    )


def _build_typst_primary_summary_source(
    resume_draft: ResumeDraft,
    candidate_profile: CandidateProfile | None,
) -> dict[str, Any]:
    """Return the explicit source hierarchy for Typst summary generation."""

    user_authored_summary = _normalize_visible_whitespace(
        candidate_profile.professional_summary_base if candidate_profile is not None else None
    )
    existing_draft_summary = _normalize_visible_whitespace(resume_draft.professional_summary)
    fit_summary = _normalize_visible_whitespace(resume_draft.fit_summary)
    target_role = _normalize_visible_whitespace(resume_draft.target_job_title)

    return {
        "user_authored_profile_summary": user_authored_summary,
        "user_authored_profile_summary_available": bool(user_authored_summary),
        "existing_resume_draft_summary": existing_draft_summary,
        "fit_summary": fit_summary,
        "target_role": target_role,
        "source_priority": [
            "user_authored_profile_summary",
            "existing_resume_draft_summary",
            "target_role_direction",
            "supported_high_level_profile_facts",
        ],
        "allowed_summary_operations": [
            "shorten_to_limit",
            "smooth_language",
            "normalize_cv_style",
            "remove_first_person_if_needed",
            "lightly_align_direction",
        ],
        "forbidden_summary_operations": [
            "rewrite_from_keywords",
            "rewrite_from_projects",
            "rewrite_from_technologies",
            "rewrite_from_job_posting",
            "replace_with_project_summary",
            "replace_with_technology_list",
        ],
        "notes": [
            "When user_authored_profile_summary_available is true, summary_text must be a conservative adaptation of user_authored_profile_summary.",
            "Existing draft summary, fit summary and target role are secondary context only.",
            "Projects, technologies and job keywords are never primary sources for summary_text.",
        ],
    }


def _build_user_authored_summary_retry_feedback(
    resolved_source: ResolvedTypstPrepareSource,
    violations: list[str],
    char_metrics: dict[str, Any] | None = None,
) -> str | None:
    """Return targeted retry guidance when summary validation fails with a profile summary available."""

    user_authored_summary = _normalize_visible_whitespace(
        resolved_source.candidate_profile.professional_summary_base
        if resolved_source.candidate_profile is not None
        else None
    )
    if not user_authored_summary:
        return None
    if not any("summary_text" in violation for violation in violations):
        return None

    failed_phrase = _extract_summary_failed_phrase_from_violations(violations)
    summary_length_metric = _extract_summary_length_overflow_metric(char_metrics)
    feedback_lines = ["User-authored profile summary preservation:"]
    if failed_phrase:
        feedback_lines.append(
            "The previous summary_text failed validation because it used the "
            f'forbidden/system-like phrase: "{failed_phrase}".'
        )
        feedback_lines.append(
            "Do not use this phrase or similar system-like/recent-task phrasing."
        )
    if summary_length_metric:
        char_count = summary_length_metric["char_count"]
        target_chars = summary_length_metric["target_chars"]
        hard_chars = summary_length_metric["hard_chars"]
        feedback_lines.append(
            "The previous summary_text failed validation because it exceeded the hard "
            f"character limit: {char_count} chars > hard limit {hard_chars} chars."
        )
        feedback_lines.append(
            f"Rewrite summary_text to about {target_chars} chars if possible; "
            f"it must be <= {hard_chars} chars."
        )
        feedback_lines.append(
            "Hard character limits outrank wording preservation. Preserve meaning and "
            "professional direction, but do not preserve exact wording if that prevents "
            "meeting the limit."
        )
    if not failed_phrase and not summary_length_metric:
        feedback_lines.append("The previous summary_text failed backend validation.")
    feedback_lines.extend(
        [
            "CandidateProfile.professional_summary_base is the semantic source of truth for summary_text.",
            "Rewrite summary_text as a conservative adaptation of the user-authored profile summary below.",
            "Preserve its meaning and professional direction. Keep wording close only when it fits within the target and hard character limits.",
            "Do not copy source transitions like My recent experience includes, Recent experience includes, Recent work includes, Experience spans or Profile includes.",
            "Do not replace it with a project, keyword, technology or job-posting summary.",
            f"User-authored profile summary: {json.dumps(user_authored_summary, ensure_ascii=False)}",
        ]
    )
    return "\n".join(feedback_lines)


def _extract_summary_length_overflow_metric(
    char_metrics: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return summary_text length metrics when it exceeded the hard limit."""

    if not isinstance(char_metrics, dict):
        return None
    summary_metric = char_metrics.get("summary_text")
    if not _is_length_metric(summary_metric):
        return None
    if not summary_metric.get("exceeds_hard"):
        return None
    return summary_metric


def _extract_summary_failed_phrase_from_violations(violations: list[str]) -> str | None:
    """Return the concrete failed summary phrase when validation reported one."""

    for violation in violations:
        if "summary_text" not in violation:
            continue
        phrase_match = re.search(r'phrase:\s*"([^"]+)"', violation)
        if phrase_match:
            return phrase_match.group(1)
    return None


def _build_profile_header_fallback(
    candidate_profile: CandidateProfile | None,
    resume_draft: ResumeDraft,
) -> dict[str, str | None]:
    """Return small typed header fallback data when it adds useful structure."""

    if candidate_profile is None:
        return {}

    personal_info = candidate_profile.personal_info
    draft_header = resume_draft.header

    linkedin, github = _resolve_supported_links(resume_draft, candidate_profile)

    should_include = any(
        [
            not (draft_header.full_name or "").strip(),
            not (draft_header.email or "").strip(),
            not (draft_header.phone or "").strip(),
            linkedin is not None,
            github is not None,
        ]
    )
    if not should_include:
        return {}

    return {
        "full_name": (personal_info.full_name or "").strip() or None,
        "email": (str(personal_info.email) or "").strip() or None,
        "phone": (personal_info.phone or "").strip() or None,
        "linkedin": linkedin,
        "github": github,
    }


def _build_profile_backed_education_entries_for_fitter(
    candidate_profile: CandidateProfile | None,
    *,
    language: str,
) -> list[TypstEducationEntry]:
    """Build structured education fallback entries, attaching thesis only to completed studies."""

    if candidate_profile is None or not candidate_profile.education_entries:
        return []

    selected_entries = _sort_education_entries_for_typst(candidate_profile.education_entries)[:2]
    thesis_title = (candidate_profile.thesis_title or "").strip() or None
    thesis_target_index = None
    if thesis_title:
        for index, entry in enumerate(selected_entries):
            if not entry.is_current:
                thesis_target_index = index
                break

    typst_entries: list[TypstEducationEntry] = []
    for index, entry in enumerate(selected_entries):
        typst_entries.append(
            TypstEducationEntry(
                institution=_resolve_education_institution_name(entry, language=language),
                degree=_format_education_degree(entry, language=language),
                date=_format_education_date(entry),
                thesis=thesis_title if thesis_target_index == index else None,
            )
        )

    return typst_entries


def _build_typst_draft_primary_source(
    resume_draft: ResumeDraft,
    candidate_profile: CandidateProfile | None = None,
) -> dict[str, Any]:
    """Return the draft source with display-safe date ranges for the Typst fitter."""

    draft_source = resume_draft.model_dump(mode="json")
    experience_source_lookup = _build_profile_experience_lookup(candidate_profile)
    project_source_lookup = _build_profile_project_lookup(candidate_profile)

    for entry in draft_source.get("selected_experience_entries") or []:
        if isinstance(entry, dict):
            entry["date_range"] = _format_cv_friendly_experience_date_value(entry.get("date_range"))
            source_entry = experience_source_lookup.get((entry.get("source_experience_id") or "").strip())
            if source_entry is not None:
                _enrich_selected_experience_source(entry, source_entry)

    for entry in draft_source.get("selected_project_entries") or []:
        if isinstance(entry, dict):
            source_entry = project_source_lookup.get((entry.get("source_project_id") or "").strip())
            if source_entry is not None:
                _enrich_selected_project_source(entry, source_entry)

    education_entries = draft_source.get("selected_education_entries")
    if isinstance(education_entries, list):
        draft_source["selected_education_entries"] = [
            _format_cv_friendly_date_ranges_in_text(value, education=True)
            if isinstance(value, str)
            else value
            for value in education_entries
        ]

    certificate_entries = draft_source.get("selected_certificate_entries")
    if isinstance(certificate_entries, list):
        draft_source["selected_certificate_entries"] = [
            _strip_certificate_issue_date_from_display(value)
            if isinstance(value, str)
            else value
            for value in certificate_entries
        ]

    return draft_source


def _build_profile_experience_lookup(
    candidate_profile: CandidateProfile | None,
) -> dict[str, ExperienceEntry]:
    """Return profile experience entries keyed by stable source id."""

    if candidate_profile is None:
        return {}

    return {
        entry.id.strip(): entry
        for entry in candidate_profile.experience_entries
        if (entry.id or "").strip()
    }


def _build_profile_project_lookup(
    candidate_profile: CandidateProfile | None,
) -> dict[str, ProjectEntry]:
    """Return profile project entries keyed by stable source id."""

    if candidate_profile is None:
        return {}

    return {
        entry.id.strip(): entry
        for entry in candidate_profile.project_entries
        if (entry.id or "").strip()
    }


def _build_profile_experience_key_lookup(
    candidate_profile: CandidateProfile | None,
) -> dict[str, ExperienceEntry]:
    """Return profile experience entries keyed by normalized company and role."""

    if candidate_profile is None:
        return {}

    lookup: dict[str, ExperienceEntry] = {}
    for entry in candidate_profile.experience_entries:
        key = _normalize_experience_key(entry.company_name, entry.position_title)
        if key and key not in lookup:
            lookup[key] = entry
    return lookup


def _build_profile_project_name_lookup(
    candidate_profile: CandidateProfile | None,
) -> dict[str, ProjectEntry]:
    """Return profile project entries keyed by normalized project name."""

    if candidate_profile is None:
        return {}

    lookup: dict[str, ProjectEntry] = {}
    for entry in candidate_profile.project_entries:
        key = _normalize_project_name_key(entry.project_name)
        if key and key not in lookup:
            lookup[key] = entry
    return lookup


def _enrich_selected_experience_source(
    selected_entry: dict[str, Any],
    source_entry: ExperienceEntry,
) -> None:
    """Attach source evidence for the fitter without generating final bullets."""

    technologies = _clean_string_list(source_entry.technologies_used)
    keywords = _clean_string_list(source_entry.keywords)
    responsibilities = _clean_string_list(source_entry.responsibilities)
    achievements = _clean_string_list(source_entry.achievements)

    if technologies:
        selected_entry["source_technologies"] = technologies
    if keywords:
        selected_entry["source_keywords"] = keywords
    if responsibilities:
        selected_entry["source_responsibilities"] = responsibilities
    if achievements:
        selected_entry["source_achievements"] = achievements


def _enrich_selected_project_source(
    selected_entry: dict[str, Any],
    source_entry: ProjectEntry,
) -> None:
    """Attach source project evidence so fitter skill/bullet choices stay factual."""

    technologies = _clean_string_list(source_entry.technologies_used)
    keywords = _clean_string_list(source_entry.keywords)
    outcomes = _clean_string_list(source_entry.outcomes)
    description = _normalize_visible_whitespace(source_entry.description)

    if technologies:
        selected_entry["source_technologies"] = technologies
    if keywords:
        selected_entry["source_keywords"] = keywords
    if outcomes:
        selected_entry["source_outcomes"] = outcomes
    if _is_substantive_text(description, min_chars=10, min_words=2):
        selected_entry["source_description"] = description


def _build_profile_fallback_experience_entries(
    resume_draft: ResumeDraft,
    candidate_profile: CandidateProfile | None,
) -> list[dict[str, Any]]:
    """Provide profile-backed experience top-up candidates when the draft is underfilled."""

    if candidate_profile is None:
        return []

    meaningful_draft_count = _count_meaningful_draft_experience_entries(resume_draft)
    available_slots = TYPST_LIMIT_CONFIG["experience"]["exact_items"] - meaningful_draft_count
    if available_slots <= 0:
        return []

    selected_ids = {
        (entry.source_experience_id or "").strip()
        for entry in resume_draft.selected_experience_entries
        if (entry.source_experience_id or "").strip()
    }
    selected_keys = {
        _normalize_experience_key(entry.company_name, entry.position_title)
        for entry in resume_draft.selected_experience_entries
        if _looks_meaningful_label(entry.company_name) and _looks_meaningful_label(entry.position_title)
    }
    fallback_entries: list[dict[str, Any]] = []

    for entry in candidate_profile.experience_entries:
        if entry.id in selected_ids:
            continue
        if _normalize_experience_key(entry.company_name, entry.position_title) in selected_keys:
            continue

        bullets = _clean_string_list(
            [*entry.achievements, *entry.responsibilities],
            limit=TYPST_LIMIT_CONFIG["experience"]["bullets_per_entry"],
        )
        if not _looks_meaningful_label(entry.company_name):
            continue
        if not _looks_meaningful_label(entry.position_title):
            continue
        if not (entry.start_date or "").strip():
            continue
        if not any(_is_substantive_text(bullet) for bullet in bullets):
            continue

        fallback_entry: dict[str, Any] = TypstExperienceEntry(
            company=(entry.company_name or "").strip(),
            role=(entry.position_title or "").strip(),
            date=_format_experience_date(entry),
            bullets=bullets,
        ).model_dump(mode="json")

        technologies_used = _clean_string_list(entry.technologies_used)
        keywords = _clean_string_list(entry.keywords)
        responsibilities = _clean_string_list(entry.responsibilities)
        achievements = _clean_string_list(entry.achievements)
        if technologies_used:
            fallback_entry["source_technologies"] = technologies_used
        if keywords:
            fallback_entry["source_keywords"] = keywords
        if responsibilities:
            fallback_entry["source_responsibilities"] = responsibilities
        if achievements:
            fallback_entry["source_achievements"] = achievements

        fallback_entries.append(fallback_entry)
        if len(fallback_entries) >= available_slots:
            break

    return fallback_entries


def _build_profile_fallback_project_entries(
    resume_draft: ResumeDraft,
    candidate_profile: CandidateProfile | None,
) -> list[TypstProjectEntry]:
    """Provide profile-backed project top-up candidates when the draft is underfilled."""

    if candidate_profile is None:
        return []

    meaningful_draft_project_keys = _collect_meaningful_draft_project_keys(resume_draft)
    available_slots = TYPST_LIMIT_CONFIG["projects"]["exact_items"] - len(meaningful_draft_project_keys)
    if available_slots <= 0:
        return []

    selected_ids = {
        (entry.source_project_id or "").strip()
        for entry in resume_draft.selected_project_entries
        if (entry.source_project_id or "").strip()
    }
    fallback_entries: list[TypstProjectEntry] = []

    for entry in candidate_profile.project_entries:
        if entry.id in selected_ids:
            continue
        project_key = _normalize_project_name_key(entry.project_name)
        if project_key in meaningful_draft_project_keys:
            continue

        description_parts = _clean_string_list(
            [entry.description, *entry.outcomes],
            limit=2,
        )
        description = " ".join(description_parts).strip()
        if not _looks_meaningful_label(entry.project_name):
            continue
        if not _is_substantive_text(description):
            continue

        fallback_entries.append(
            TypstProjectEntry(
                name=(entry.project_name or "").strip(),
                description=description,
            )
        )
        meaningful_draft_project_keys.add(project_key)
        if len(fallback_entries) >= available_slots:
            break

    return fallback_entries


def _build_profile_fallback_skill_entries(
    resume_draft: ResumeDraft,
    candidate_profile: CandidateProfile | None,
) -> list[str]:
    """Provide profile-backed skill category rows when the draft is sparse or too granular."""

    if candidate_profile is None:
        return []

    existing_values = _clean_string_list(
        [*resume_draft.selected_skills, *resume_draft.selected_soft_skill_entries]
    )
    if (
        len(existing_values) >= TYPST_LIMIT_CONFIG["skills"]["exact_items"]
        and not any(_is_weak_skill_line(value) for value in existing_values)
    ):
        return []

    fallback_values: list[str] = []
    seen_keys = {_normalize_fallback_dedupe_key(value) for value in existing_values}
    for value in _build_profile_skill_category_lines(candidate_profile):
        _append_unique_normalized_fallback(fallback_values, seen_keys, value)
        if len(fallback_values) >= TYPST_LIMIT_CONFIG["skills"]["exact_items"]:
            break

    return fallback_values


def _build_profile_fallback_language_certificate_entries(
    resume_draft: ResumeDraft,
    candidate_profile: CandidateProfile | None,
) -> list[str]:
    """Provide profile-backed language/certificate top-up candidates."""

    if candidate_profile is None:
        return []

    existing_values = _clean_string_list(
        [
            *resume_draft.selected_language_entries,
            *resume_draft.selected_certificate_entries,
        ]
    )
    available_slots = TYPST_LIMIT_CONFIG["languages_certificates"]["max_items"] - len(existing_values)
    if available_slots <= 0:
        return []

    fallback_values: list[str] = []
    seen_keys = {_normalize_fallback_dedupe_key(value) for value in existing_values}
    for entry in candidate_profile.language_entries:
        formatted_entry = _format_language_entry(entry.language_name, entry.proficiency_level)
        if formatted_entry is not None:
            _append_unique_normalized_fallback(fallback_values, seen_keys, formatted_entry)
        if len(fallback_values) >= available_slots:
            return fallback_values

    forbidden_certificate_keys = {
        _normalize_fallback_dedupe_key(value)
        for value in candidate_profile.immutable_rules.forbidden_certificates
        if _looks_meaningful_label(value, min_chars=2)
    }
    for entry in candidate_profile.certificate_entries:
        formatted_entry = _format_certificate_entry(
            entry.certificate_name,
            entry.issuer,
            entry.issue_date,
            entry.notes,
        )
        if formatted_entry is None:
            continue
        if _is_forbidden_certificate_fallback(
            formatted_entry,
            entry.certificate_name,
            forbidden_certificate_keys,
        ):
            continue
        _append_unique_normalized_fallback(fallback_values, seen_keys, formatted_entry)
        if len(fallback_values) >= available_slots:
            break

    return fallback_values


def _resolve_supported_links(
    resume_draft: ResumeDraft,
    candidate_profile: CandidateProfile | None,
) -> tuple[str | None, str | None]:
    """Resolve typed LinkedIn/GitHub links with profile-first, draft-second priority."""

    linkedin = (
        str(candidate_profile.personal_info.linkedin_url)
        if candidate_profile is not None and candidate_profile.personal_info.linkedin_url
        else None
    )
    github = (
        str(candidate_profile.personal_info.github_url)
        if candidate_profile is not None and candidate_profile.personal_info.github_url
        else None
    )

    for link in resume_draft.header.links:
        normalized_link = (link or "").strip()
        if not normalized_link:
            continue
        lowered_link = normalized_link.lower()
        if linkedin is None and "linkedin.com" in lowered_link:
            linkedin = normalized_link
        if github is None and "github.com" in lowered_link:
            github = normalized_link
    return linkedin, github


def _count_meaningful_draft_experience_entries(resume_draft: ResumeDraft) -> int:
    """Return how many draft experience entries are complete enough for Typst output."""

    count = 0
    for entry in resume_draft.selected_experience_entries:
        if not _looks_meaningful_label(entry.company_name):
            continue
        if not _looks_meaningful_label(entry.position_title):
            continue
        if not (entry.date_range or "").strip():
            continue
        if any(_is_substantive_text(bullet) for bullet in entry.bullet_points):
            count += 1
    return count


def _collect_meaningful_draft_project_keys(resume_draft: ResumeDraft) -> set[str]:
    """Return normalized project names for draft entries that are usable."""

    project_keys: set[str] = set()
    for entry in resume_draft.selected_project_entries:
        if not _looks_meaningful_label(entry.project_name):
            continue
        project_text = " ".join(_clean_string_list([*entry.bullet_points, entry.relevance_note or ""], limit=2))
        if _is_substantive_text(project_text):
            project_key = _normalize_project_name_key(entry.project_name)
            if project_key:
                project_keys.add(project_key)
    return project_keys


def _normalize_experience_key(company: str | None, role: str | None) -> str:
    """Normalize an experience header for conservative top-up duplicate checks."""

    return _normalize_fallback_dedupe_key(f"{company or ''} {role or ''}")


def _normalize_project_name_key(value: str | None) -> str:
    """Normalize a project name so small separator differences do not create duplicates."""

    normalized_value = _normalize_fallback_dedupe_key(value)
    normalized_value = re.sub(r"\s*[:|/]+\s*", " ", normalized_value)
    normalized_value = re.sub(r"\s+", " ", normalized_value)
    return normalized_value.strip(" -")


def _build_profile_skill_category_lines(candidate_profile: CandidateProfile) -> list[str]:
    """Build richer skill fallback rows from structured profile skills and soft skills."""

    software_values: list[str] = []
    automation_values: list[str] = []
    other_values: list[str] = []

    for skill_entry in candidate_profile.skill_entries:
        cleaned_name = _normalize_visible_whitespace(skill_entry.name)
        if not _looks_meaningful_label(cleaned_name, min_chars=2):
            continue

        category = _normalize_visible_whitespace(skill_entry.category)
        aliases = _clean_string_list(skill_entry.aliases)
        bucket_text = " ".join([cleaned_name, category, *aliases]).lower()
        if _contains_any_hint(bucket_text, _AUTOMATION_SKILL_HINTS):
            _append_unique_skill_value(automation_values, cleaned_name)
        elif _contains_any_hint(bucket_text, _SOFTWARE_SKILL_HINTS):
            _append_unique_skill_value(software_values, cleaned_name)
        else:
            _append_unique_skill_value(other_values, cleaned_name)

    soft_skill_values: list[str] = []
    for soft_skill in candidate_profile.soft_skill_entries:
        cleaned_soft_skill = _normalize_visible_whitespace(soft_skill)
        if _looks_meaningful_label(cleaned_soft_skill, min_chars=3):
            _append_unique_skill_value(soft_skill_values, cleaned_soft_skill)

    technical_lines: list[str] = []
    _append_skill_category_line(technical_lines, "Software & AI", software_values)
    _append_skill_category_line(technical_lines, "Automation & Control", automation_values)
    _append_skill_category_line(technical_lines, "Technical skills", other_values)

    fallback_lines = technical_lines[:2]
    soft_line = _build_skill_category_line("Soft skills", soft_skill_values)
    if soft_line:
        fallback_lines.append(soft_line)

    if len(fallback_lines) < TYPST_LIMIT_CONFIG["skills"]["exact_items"]:
        seen_line_keys = {_normalize_fallback_dedupe_key(line) for line in fallback_lines}
        for line in technical_lines[2:]:
            _append_unique_normalized_fallback(fallback_lines, seen_line_keys, line)
            if len(fallback_lines) >= TYPST_LIMIT_CONFIG["skills"]["exact_items"]:
                break

    return fallback_lines[: TYPST_LIMIT_CONFIG["skills"]["exact_items"]]


def _build_profile_skill_source_material(
    candidate_profile: CandidateProfile | None,
    resume_draft: ResumeDraft | None = None,
) -> dict[str, Any]:
    """Return raw profile skill evidence so the fitter can choose natural categories."""

    if candidate_profile is None:
        return {}

    structured_skills: list[dict[str, Any]] = []
    for skill_entry in candidate_profile.skill_entries:
        cleaned_name = _normalize_visible_whitespace(skill_entry.name)
        if not _looks_meaningful_label(cleaned_name, min_chars=2):
            continue

        skill_record: dict[str, Any] = {"name": cleaned_name}
        category = _normalize_visible_whitespace(skill_entry.category)
        level = _normalize_visible_whitespace(skill_entry.level)
        aliases = _clean_string_list(skill_entry.aliases)
        evidence_sources = _clean_string_list(skill_entry.evidence_sources)
        if category:
            skill_record["category"] = category
        if level:
            skill_record["level"] = level
        if skill_entry.years_of_experience is not None:
            skill_record["years_of_experience"] = skill_entry.years_of_experience
        if aliases:
            skill_record["aliases"] = aliases
        if evidence_sources:
            skill_record["evidence_sources"] = evidence_sources
        structured_skills.append(skill_record)

    experience_technologies: list[str] = []
    experience_keywords: list[str] = []
    for entry in candidate_profile.experience_entries:
        _append_unique_visible_values(experience_technologies, entry.technologies_used)
        _append_unique_visible_values(experience_keywords, entry.keywords)

    project_technologies: list[str] = []
    project_keywords: list[str] = []
    for entry in candidate_profile.project_entries:
        _append_unique_visible_values(project_technologies, entry.technologies_used)
        _append_unique_visible_values(project_keywords, entry.keywords)

    selected_experience_technologies: list[str] = []
    selected_experience_keywords: list[str] = []
    selected_project_technologies: list[str] = []
    selected_project_keywords: list[str] = []
    if resume_draft is not None:
        experience_lookup = _build_profile_experience_lookup(candidate_profile)
        for selected_entry in resume_draft.selected_experience_entries:
            source_id = (selected_entry.source_experience_id or "").strip()
            source_entry = experience_lookup.get(source_id)
            if source_entry is None:
                continue
            _append_unique_visible_values(
                selected_experience_technologies,
                source_entry.technologies_used,
            )
            _append_unique_visible_values(
                selected_experience_keywords,
                [*source_entry.keywords, *selected_entry.highlighted_keywords],
            )

        project_lookup = _build_profile_project_lookup(candidate_profile)
        for selected_entry in resume_draft.selected_project_entries:
            source_id = (selected_entry.source_project_id or "").strip()
            source_entry = project_lookup.get(source_id)
            if source_entry is None:
                continue
            _append_unique_visible_values(
                selected_project_technologies,
                source_entry.technologies_used,
            )
            _append_unique_visible_values(
                selected_project_keywords,
                [*source_entry.keywords, *selected_entry.highlighted_keywords],
            )

    soft_skills: list[str] = []
    _append_unique_visible_values(soft_skills, candidate_profile.soft_skill_entries, min_chars=3)

    material: dict[str, Any] = {}
    if structured_skills:
        material["technical_skills"] = structured_skills
    if selected_experience_technologies:
        material["selected_experience_technologies"] = selected_experience_technologies
    if selected_experience_keywords:
        material["selected_experience_keywords"] = selected_experience_keywords
    if selected_project_technologies:
        material["selected_project_technologies"] = selected_project_technologies
    if selected_project_keywords:
        material["selected_project_keywords"] = selected_project_keywords
    if experience_technologies:
        material["experience_technologies"] = experience_technologies
    if experience_keywords:
        material["experience_keywords"] = experience_keywords
    if project_technologies:
        material["project_technologies"] = project_technologies
    if project_keywords:
        material["project_keywords"] = project_keywords
    if soft_skills:
        material["soft_skills"] = soft_skills
    return material


def _append_skill_category_line(lines: list[str], label: str, values: list[str]) -> None:
    """Append one nonempty skill category line if it fits the Typst hard limit."""

    line = _build_skill_category_line(label, values)
    if line:
        lines.append(line)


def _build_skill_category_line(label: str, values: list[str]) -> str | None:
    """Build one bounded skill line from ordered unique values."""

    selected_values: list[str] = []
    for value in values:
        candidate_values = [*selected_values, value]
        candidate_line = f"{label}: {', '.join(candidate_values)}"
        if len(candidate_line) <= TYPST_LIMIT_CONFIG["skills"]["entry_hard_chars"]:
            selected_values.append(value)

    if not selected_values:
        return None
    return f"{label}: {', '.join(selected_values)}"


def _append_unique_skill_value(values: list[str], value: str) -> None:
    """Append one skill value once after fallback-style normalization."""

    normalized_value = _normalize_fallback_dedupe_key(value)
    if not normalized_value:
        return
    if any(_normalize_fallback_dedupe_key(existing) == normalized_value for existing in values):
        return
    values.append(value)


def _append_unique_visible_values(
    values: list[str],
    candidates: list[str],
    *,
    min_chars: int = 2,
) -> None:
    """Append meaningful visible strings once after fallback-style normalization."""

    for candidate in candidates:
        cleaned_candidate = _normalize_visible_whitespace(candidate)
        if not _looks_meaningful_label(cleaned_candidate, min_chars=min_chars):
            continue
        _append_unique_skill_value(values, cleaned_candidate)


def _contains_any_hint(value: str, hints: tuple[str, ...]) -> bool:
    """Return whether a lowercased text contains one of the category hints."""

    return any(hint in value for hint in hints)


def _is_weak_skill_line(value: str) -> bool:
    """Return whether a skill row is too granular to be a good Typst skill entry."""

    cleaned_value = _normalize_visible_whitespace(value)
    if not cleaned_value:
        return True
    if ":" in cleaned_value or "," in cleaned_value:
        return False
    return len(cleaned_value.split()) <= 2 and len(cleaned_value) <= 30


def _dedupe_typst_project_entries(entries: list[TypstProjectEntry]) -> list[TypstProjectEntry]:
    """Keep the first project for each normalized name so the final payload has no duplicate titles."""

    deduped_entries: list[TypstProjectEntry] = []
    seen_names: set[str] = set()
    for entry in entries:
        project_key = _normalize_project_name_key(entry.name)
        if project_key:
            if project_key in seen_names:
                continue
            seen_names.add(project_key)
        deduped_entries.append(entry)
    return deduped_entries


def _looks_meaningful_label(value: str, *, min_chars: int = 2) -> bool:
    """Return whether a short single-line field looks usable in a CV section."""

    cleaned_value = (value or "").strip()
    if len(cleaned_value) < min_chars:
        return False
    if _is_placeholder_value(cleaned_value):
        return False
    return any(character.isalnum() for character in cleaned_value)


def _is_substantive_text(value: str, *, min_chars: int = 20, min_words: int = 3) -> bool:
    """Return whether a longer text fragment is detailed enough for a natural fallback."""

    cleaned_value = (value or "").strip()
    if not cleaned_value:
        return False
    if len(cleaned_value) >= min_chars:
        return True
    return len([word for word in cleaned_value.split() if word.strip()]) >= min_words


def _merge_typst_fit_to_page_patch(
    typst_payload: TypstPayload,
    patch: TypstFitToPagePatch,
) -> tuple[TypstPayload, list[str]]:
    """Apply only v1 allowed fit-to-page patch fields to a copied TypstPayload."""

    changed_fields: list[str] = []
    summary_text = typst_payload.summary_text
    if patch.summary_text is not None:
        cleaned_summary = _clean_fit_to_page_patch_text(patch.summary_text, field_path="summary_text")
        if cleaned_summary != typst_payload.summary_text:
            summary_text = cleaned_summary
            changed_fields.append("summary_text")

    experience_entries = [
        entry.model_copy(update={"bullets": list(entry.bullets)})
        for entry in typst_payload.experience_entries
    ]
    seen_bullet_updates: set[tuple[int, int]] = set()
    for update in patch.experience_bullet_updates:
        update_key = (update.entry_index, update.bullet_index)
        if update_key in seen_bullet_updates:
            raise _build_fit_to_page_validation_error(
                f"Duplicate patch for experience_entries[{update.entry_index}].bullets[{update.bullet_index}]."
            )
        seen_bullet_updates.add(update_key)
        if update.entry_index >= len(experience_entries):
            raise _build_fit_to_page_validation_error(
                f"experience_entries[{update.entry_index}] does not exist."
            )
        bullets = list(experience_entries[update.entry_index].bullets)
        if update.bullet_index >= len(bullets):
            raise _build_fit_to_page_validation_error(
                f"experience_entries[{update.entry_index}].bullets[{update.bullet_index}] does not exist."
            )
        cleaned_text = _clean_fit_to_page_patch_text(
            update.text,
            field_path=f"experience_entries[{update.entry_index}].bullets[{update.bullet_index}]",
        )
        if cleaned_text != bullets[update.bullet_index]:
            bullets[update.bullet_index] = cleaned_text
            experience_entries[update.entry_index] = experience_entries[update.entry_index].model_copy(
                update={"bullets": bullets}
            )
            changed_fields.append(
                f"experience_entries[{update.entry_index}].bullets[{update.bullet_index}]"
            )

    project_entries = [entry.model_copy() for entry in typst_payload.project_entries]
    seen_project_updates: set[int] = set()
    for update in patch.project_description_updates:
        if update.entry_index in seen_project_updates:
            raise _build_fit_to_page_validation_error(
                f"Duplicate patch for project_entries[{update.entry_index}].description."
            )
        seen_project_updates.add(update.entry_index)
        if update.entry_index >= len(project_entries):
            raise _build_fit_to_page_validation_error(
                f"project_entries[{update.entry_index}] does not exist."
            )
        cleaned_description = _clean_fit_to_page_patch_text(
            update.description,
            field_path=f"project_entries[{update.entry_index}].description",
        )
        if cleaned_description != project_entries[update.entry_index].description:
            project_entries[update.entry_index] = project_entries[update.entry_index].model_copy(
                update={"description": cleaned_description}
            )
            changed_fields.append(f"project_entries[{update.entry_index}].description")

    merged_payload = typst_payload.model_copy(
        update={
            "summary_text": summary_text,
            "experience_entries": experience_entries,
            "project_entries": project_entries,
        },
        deep=True,
    )
    return merged_payload, changed_fields


def _clean_fit_to_page_patch_text(value: str, *, field_path: str) -> str:
    """Clean and validate one patch text field without semantic rewriting."""

    cleaned_value = " ".join((value or "").replace("\r\n", "\n").replace("\r", "\n").split())
    if not cleaned_value:
        raise _build_fit_to_page_validation_error(f"{field_path} cannot be empty.")
    if _is_placeholder_value(cleaned_value):
        raise _build_fit_to_page_validation_error(f"{field_path} cannot be a placeholder value.")
    if not any(character.isalnum() for character in cleaned_value):
        raise _build_fit_to_page_validation_error(f"{field_path} must contain meaningful text.")
    return cleaned_value


def _validate_fit_to_page_immutable_fields(original: TypstPayload, merged: TypstPayload) -> None:
    """Verify that a merged patch changed only the explicit v1 allowed text fields."""

    violations: list[str] = []
    scalar_fields = [
        "template_name",
        "language",
        "include_photo",
        "photo_asset_id",
        "consent_mode",
        "custom_consent_text",
    ]
    original_dump = original.model_dump(mode="json")
    merged_dump = merged.model_dump(mode="json")
    for field_name in scalar_fields:
        if original_dump.get(field_name) != merged_dump.get(field_name):
            violations.append(f"{field_name} must not change.")

    if original_dump.get("profile") != merged_dump.get("profile"):
        violations.append("profile must not change.")
    if original_dump.get("education_entries") != merged_dump.get("education_entries"):
        violations.append("education_entries must not change.")
    if original_dump.get("skill_entries") != merged_dump.get("skill_entries"):
        violations.append("skill_entries must not change.")
    if original_dump.get("language_certificate_entries") != merged_dump.get("language_certificate_entries"):
        violations.append("language_certificate_entries must not change.")

    if len(original.experience_entries) != len(merged.experience_entries):
        violations.append("experience_entries count must not change.")
    else:
        for index, (original_entry, merged_entry) in enumerate(
            zip(original.experience_entries, merged.experience_entries, strict=True)
        ):
            if original_entry.company != merged_entry.company:
                violations.append(f"experience_entries[{index}].company must not change.")
            if original_entry.role != merged_entry.role:
                violations.append(f"experience_entries[{index}].role must not change.")
            if original_entry.date != merged_entry.date:
                violations.append(f"experience_entries[{index}].date must not change.")
            if len(original_entry.bullets) != len(merged_entry.bullets):
                violations.append(f"experience_entries[{index}].bullets count must not change.")

    if len(original.project_entries) != len(merged.project_entries):
        violations.append("project_entries count must not change.")
    else:
        for index, (original_entry, merged_entry) in enumerate(
            zip(original.project_entries, merged.project_entries, strict=True)
        ):
            if original_entry.name != merged_entry.name:
                violations.append(f"project_entries[{index}].name must not change.")

    if violations:
        raise _build_fit_to_page_validation_error(*violations)


def _collect_changed_sections(changed_fields: list[str]) -> list[str]:
    """Return stable section names from changed field paths."""

    sections: list[str] = []
    for field_path in changed_fields:
        if field_path == "summary_text":
            section_name = "summary"
        elif field_path.startswith("experience_entries"):
            section_name = "experience"
        elif field_path.startswith("project_entries"):
            section_name = "projects"
        else:
            section_name = "unknown"
        if section_name not in sections:
            sections.append(section_name)
    return sections


def _build_fit_to_page_retry_feedback(validation_error: TypstPayloadValidationError) -> str:
    """Build specific validation feedback for the single fit-to-page corrective retry."""

    feedback_lines = [
        "The previous Typst fit-to-page patch produced a merged TypstPayload that failed backend validation.",
        "Return a corrected TypstFitToPagePatch. Do not repeat the invalid expansion.",
        "Retry feedback is mandatory and must be followed exactly.",
        "Hard character limits are absolute. Target character limits are preferred.",
    ]

    if validation_error.violations:
        feedback_lines.append("Validation errors:")
        feedback_lines.extend(f"- {violation}" for violation in validation_error.violations)

    length_feedback = _collect_fit_to_page_hard_limit_retry_feedback(validation_error.char_metrics)
    if length_feedback:
        feedback_lines.append("Length fixes:")
        feedback_lines.extend(f"- {item}" for item in length_feedback)

    return "\n".join(feedback_lines)


def _collect_fit_to_page_hard_limit_retry_feedback(
    metrics: Any,
    *,
    path: str = "",
) -> list[str]:
    """Collect fit-to-page retry instructions for fields exceeding hard char limits."""

    if _is_length_metric(metrics):
        if not metrics.get("exceeds_hard"):
            return []

        field_path = path or "value"
        display_path = field_path
        extra_guidance = ""
        project_match = re.fullmatch(r"project_entries\[(\d+)\]\.entry_total", field_path)
        if project_match:
            display_path = f"project_entries[{project_match.group(1)}].description"
            extra_guidance = (
                f" Do not expand project_entries[{project_match.group(1)}] again. "
                "Prefer using available space in experience bullets before expanding project descriptions."
            )

        char_count = metrics["char_count"]
        target_chars = metrics["target_chars"]
        hard_chars = metrics["hard_chars"]
        return [
            (
                f"{display_path} exceeds the hard character limit. Current length: {char_count} characters. "
                f"Target: {target_chars} characters. Hard limit: {hard_chars} characters. "
                f"Shorten {display_path} to be at or below {target_chars} characters if possible and never above "
                f"{hard_chars} characters.{extra_guidance}"
            )
        ]

    if isinstance(metrics, dict):
        feedback: list[str] = []
        for key, value in metrics.items():
            child_path = f"{path}.{key}" if path else str(key)
            feedback.extend(_collect_fit_to_page_hard_limit_retry_feedback(value, path=child_path))
        return feedback

    if isinstance(metrics, list):
        feedback = []
        for index, value in enumerate(metrics):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            feedback.extend(_collect_fit_to_page_hard_limit_retry_feedback(value, path=child_path))
        return feedback

    return []


def _build_fit_to_page_validation_error(*violations: str) -> TypstFitToPageError:
    """Build a structured fit-to-page validation error."""

    return TypstFitToPageError(
        "Typst fit-to-page patch validation failed.",
        status_code=422,
        details={
            "validation_errors": [violation for violation in violations if violation],
            "changed_fields": [],
            "char_metrics": {},
            "warnings": [],
        },
    )


def _normalize_typst_payload(
    typst_payload: TypstPayload,
    options: TypstRenderOptions,
) -> TypstPayload:
    """Trim user-facing strings and reapply deterministic render options."""

    return TypstPayload(
        template_name="cv_one_page",
        language=options.language,
        include_photo=options.include_photo,
        consent_mode=options.consent_mode,
        custom_consent_text=(options.custom_consent_text or "").strip() or None,
        photo_asset_id=(options.photo_asset_id or "").strip() or None,
        profile=TypstProfilePayload(
            full_name=(typst_payload.profile.full_name or "").strip(),
            email=(typst_payload.profile.email or "").strip(),
            phone=(typst_payload.profile.phone or "").strip(),
            linkedin=(typst_payload.profile.linkedin or "").strip() or None,
            github=(typst_payload.profile.github or "").strip() or None,
        ),
        summary_text=(typst_payload.summary_text or "").strip(),
        education_entries=[
            TypstEducationEntry(
                institution=(entry.institution or "").strip(),
                degree=(entry.degree or "").strip(),
                date=_format_cv_friendly_education_date_value(entry.date),
                thesis=(entry.thesis or "").strip() or None,
            )
            for entry in typst_payload.education_entries
            if any(
                [
                    (entry.institution or "").strip(),
                    (entry.degree or "").strip(),
                    (entry.date or "").strip(),
                    (entry.thesis or "").strip(),
                ]
            )
        ],
        experience_entries=[
            TypstExperienceEntry(
                company=(entry.company or "").strip(),
                role=(entry.role or "").strip(),
                date=_format_cv_friendly_experience_date_value(entry.date),
                bullets=_clean_string_list(entry.bullets),
            )
            for entry in typst_payload.experience_entries
            if any(
                [
                    (entry.company or "").strip(),
                    (entry.role or "").strip(),
                    (entry.date or "").strip(),
                    _clean_string_list(entry.bullets),
                ]
            )
        ],
        project_entries=_dedupe_typst_project_entries(
            [
                TypstProjectEntry(
                    name=(entry.name or "").strip(),
                    description=(entry.description or "").strip(),
                )
                for entry in typst_payload.project_entries
                if any(
                    [
                        (entry.name or "").strip(),
                        (entry.description or "").strip(),
                    ]
                )
            ]
        ),
        skill_entries=_clean_string_list(typst_payload.skill_entries),
        language_certificate_entries=_clean_string_list(typst_payload.language_certificate_entries),
    )


def _validate_typst_payload(
    typst_payload: TypstPayload,
) -> tuple[dict[str, int], dict[str, Any]]:
    """Validate deterministic template limits after the structured AI output."""

    violations: list[str] = []
    char_metrics: dict[str, Any] = {}
    section_counts = {
        "education_entries": len(typst_payload.education_entries),
        "experience_entries": len(typst_payload.experience_entries),
        "project_entries": len(typst_payload.project_entries),
        "skill_entries": len(typst_payload.skill_entries),
        "language_certificate_entries": len(typst_payload.language_certificate_entries),
        "nonempty_thesis_entries": sum(
            1 for entry in typst_payload.education_entries if (entry.thesis or "").strip()
        ),
    }

    if typst_payload.template_name != "cv_one_page":
        violations.append("template_name must stay 'cv_one_page'.")

    if len(typst_payload.education_entries) > TYPST_LIMIT_CONFIG["education"]["exact_items"]:
        violations.append("education_entries exceed the allowed maximum of 2.")
    if len(typst_payload.experience_entries) > TYPST_LIMIT_CONFIG["experience"]["exact_items"]:
        violations.append("experience_entries exceed the allowed maximum of 2.")
    if len(typst_payload.project_entries) > TYPST_LIMIT_CONFIG["projects"]["exact_items"]:
        violations.append("project_entries exceed the allowed maximum of 2.")
    if len(typst_payload.skill_entries) > TYPST_LIMIT_CONFIG["skills"]["exact_items"]:
        violations.append("skill_entries exceed the allowed maximum of 3.")
    if (
        len(typst_payload.language_certificate_entries)
        > TYPST_LIMIT_CONFIG["languages_certificates"]["max_items"]
    ):
        violations.append("language_certificate_entries exceed the allowed maximum of 6.")
    if section_counts["nonempty_thesis_entries"] > TYPST_LIMIT_CONFIG["education"]["thesis_max_items"]:
        violations.append("At most one education entry may contain thesis text.")

    char_metrics["summary_text"] = _build_length_metric(
        typst_payload.summary_text,
        target_chars=TYPST_LIMIT_CONFIG["summary"]["target_chars"],
        hard_chars=TYPST_LIMIT_CONFIG["summary"]["hard_chars"],
    )
    if char_metrics["summary_text"]["exceeds_hard"]:
        violations.append("summary_text exceeds the hard character limit.")
    forbidden_summary_phrase = _find_summary_forbidden_style_phrase(
        typst_payload.summary_text,
        _SUMMARY_RECENT_TASK_STYLE_PHRASES,
    )
    forbidden_third_person_phrase = _find_summary_forbidden_style_phrase(
        typst_payload.summary_text,
        _SUMMARY_THIRD_PERSON_STYLE_PHRASES,
    )
    if forbidden_summary_phrase:
        violations.append(
            f'summary_text uses a system-like or recent-task phrase: "{forbidden_summary_phrase}". '
            "Rewrite summary_text as a fluent candidate profile paragraph. It should describe the "
            "candidate profile, practical background and professional direction. Do not list recent "
            "tasks in summary; keep project-specific and technical details in Experience, Projects or Skills."
        )
    if forbidden_third_person_phrase:
        violations.append(
            f'summary_text is written in third person ("{forbidden_third_person_phrase}"). '
            "Rewrite it as a natural CV profile paragraph without first-person pronouns and without "
            'third-person wording. Use profile-style phrasing such as "Automation and Robotics engineer..." '
            'and "Combines practical experience...".'
        )

    profile_metrics = {
        "full_name": _build_length_metric(
            typst_payload.profile.full_name,
            target_chars=TYPST_LIMIT_CONFIG["header"]["full_name_hard_chars"],
            hard_chars=TYPST_LIMIT_CONFIG["header"]["full_name_hard_chars"],
        ),
        "email": _build_length_metric(
            typst_payload.profile.email,
            target_chars=TYPST_LIMIT_CONFIG["header"]["email_hard_chars"],
            hard_chars=TYPST_LIMIT_CONFIG["header"]["email_hard_chars"],
        ),
        "phone": _build_length_metric(
            typst_payload.profile.phone,
            target_chars=TYPST_LIMIT_CONFIG["header"]["phone_hard_chars"],
            hard_chars=TYPST_LIMIT_CONFIG["header"]["phone_hard_chars"],
        ),
        "linkedin": _build_length_metric(
            typst_payload.profile.linkedin or "",
            target_chars=TYPST_LIMIT_CONFIG["header"]["linkedin_hard_chars"],
            hard_chars=TYPST_LIMIT_CONFIG["header"]["linkedin_hard_chars"],
        ),
        "github": _build_length_metric(
            typst_payload.profile.github or "",
            target_chars=TYPST_LIMIT_CONFIG["header"]["github_hard_chars"],
            hard_chars=TYPST_LIMIT_CONFIG["header"]["github_hard_chars"],
        ),
    }
    char_metrics["profile"] = profile_metrics
    for field_name, metric in profile_metrics.items():
        if metric["exceeds_hard"]:
            violations.append(f"profile.{field_name} exceeds the hard character limit.")

    education_metrics: list[dict[str, Any]] = []
    for index, entry in enumerate(typst_payload.education_entries):
        entry_metrics = {
            "institution": _build_length_metric(
                entry.institution,
                target_chars=TYPST_LIMIT_CONFIG["education"]["institution_target_chars"],
                hard_chars=TYPST_LIMIT_CONFIG["education"]["institution_hard_chars"],
            ),
            "degree": _build_length_metric(
                entry.degree,
                target_chars=TYPST_LIMIT_CONFIG["education"]["degree_target_chars"],
                hard_chars=TYPST_LIMIT_CONFIG["education"]["degree_hard_chars"],
            ),
            "date": _build_length_metric(
                entry.date,
                target_chars=TYPST_LIMIT_CONFIG["education"]["date_hard_chars"],
                hard_chars=TYPST_LIMIT_CONFIG["education"]["date_hard_chars"],
            ),
            "thesis": _build_length_metric(
                entry.thesis or "",
                target_chars=TYPST_LIMIT_CONFIG["education"]["thesis_target_chars"],
                hard_chars=TYPST_LIMIT_CONFIG["education"]["thesis_hard_chars"],
            ),
        }
        education_metrics.append(entry_metrics)
        for field_name, metric in entry_metrics.items():
            if metric["exceeds_hard"]:
                violations.append(
                    f"education_entries[{index}].{field_name} exceeds the hard character limit."
                )
    char_metrics["education_entries"] = education_metrics

    experience_metrics: list[dict[str, Any]] = []
    for index, entry in enumerate(typst_payload.experience_entries):
        if len(entry.bullets) > TYPST_LIMIT_CONFIG["experience"]["bullets_per_entry"]:
            violations.append(
                f"experience_entries[{index}] exceed the allowed maximum of 2 bullets."
            )
        entry_metrics = {
            "header_left": _build_length_metric(
                _join_header_left(entry.company, entry.role),
                target_chars=TYPST_LIMIT_CONFIG["experience"]["header_left_target_chars"],
                hard_chars=TYPST_LIMIT_CONFIG["experience"]["header_left_hard_chars"],
            ),
            "date": _build_length_metric(
                entry.date,
                target_chars=TYPST_LIMIT_CONFIG["experience"]["date_hard_chars"],
                hard_chars=TYPST_LIMIT_CONFIG["experience"]["date_hard_chars"],
            ),
            "bullets": [
                _build_length_metric(
                    bullet,
                    target_chars=TYPST_LIMIT_CONFIG["experience"]["bullet_target_chars"],
                    hard_chars=TYPST_LIMIT_CONFIG["experience"]["bullet_hard_chars"],
                )
                for bullet in entry.bullets
            ],
        }
        experience_metrics.append(entry_metrics)
        if entry_metrics["header_left"]["exceeds_hard"]:
            violations.append(f"experience_entries[{index}].header_left exceeds the hard character limit.")
        if entry_metrics["date"]["exceeds_hard"]:
            violations.append(f"experience_entries[{index}].date exceeds the hard character limit.")
        for bullet_index, bullet_metric in enumerate(entry_metrics["bullets"]):
            if bullet_metric["exceeds_hard"]:
                violations.append(
                    f"experience_entries[{index}].bullets[{bullet_index}] exceed the hard character limit."
                )
    char_metrics["experience_entries"] = experience_metrics

    project_metrics: list[dict[str, Any]] = []
    for index, entry in enumerate(typst_payload.project_entries):
        entry_metrics = {
            "entry_total": _build_length_metric(
                _join_header_left(entry.name, entry.description),
                target_chars=TYPST_LIMIT_CONFIG["projects"]["entry_total_target_chars"],
                hard_chars=TYPST_LIMIT_CONFIG["projects"]["entry_total_hard_chars"],
            )
        }
        project_metrics.append(entry_metrics)
        if entry_metrics["entry_total"]["exceeds_hard"]:
            violations.append(
                f"project_entries[{index}] exceed the hard character limit."
            )
    char_metrics["project_entries"] = project_metrics

    skill_metrics = [
        _build_length_metric(
            value,
            target_chars=TYPST_LIMIT_CONFIG["skills"]["entry_target_chars"],
            hard_chars=TYPST_LIMIT_CONFIG["skills"]["entry_hard_chars"],
        )
        for value in typst_payload.skill_entries
    ]
    char_metrics["skill_entries"] = skill_metrics
    for index, metric in enumerate(skill_metrics):
        if metric["exceeds_hard"]:
            violations.append(f"skill_entries[{index}] exceed the hard character limit.")

    language_certificate_metrics = [
        _build_length_metric(
            value,
            target_chars=TYPST_LIMIT_CONFIG["languages_certificates"]["entry_target_chars"],
            hard_chars=TYPST_LIMIT_CONFIG["languages_certificates"]["entry_hard_chars"],
        )
        for value in typst_payload.language_certificate_entries
    ]
    char_metrics["language_certificate_entries"] = language_certificate_metrics
    for index, metric in enumerate(language_certificate_metrics):
        if metric["exceeds_hard"]:
            violations.append(
                f"language_certificate_entries[{index}] exceed the hard character limit."
            )

    if violations:
        raise TypstPayloadValidationError(
            "Typst payload validation failed.",
            violations=violations,
            section_counts=section_counts,
            char_metrics=char_metrics,
        )

    return section_counts, char_metrics


def _build_length_metric(
    value: str,
    *,
    target_chars: int,
    hard_chars: int,
) -> dict[str, int | bool]:
    """Build one small debug record for a single string length constraint."""

    char_count = len((value or "").strip())
    return {
        "char_count": char_count,
        "target_chars": target_chars,
        "hard_chars": hard_chars,
        "exceeds_target": char_count > target_chars,
        "exceeds_hard": char_count > hard_chars,
    }


def _format_education_date(entry: EducationEntry) -> str:
    """Format one education date range for the Typst payload."""

    start_label = _format_year_label(entry.start_date) or _normalize_visible_whitespace(entry.start_date)
    end_label = "Present" if entry.is_current else _format_year_label(entry.end_date)
    if not end_label and not entry.is_current:
        end_label = _normalize_visible_whitespace(entry.end_date)
    if start_label and end_label:
        return f"{start_label} - {end_label}"
    return start_label


def _sort_education_entries_for_typst(entries: list[EducationEntry]) -> list[EducationEntry]:
    """Prefer current education first, then newer completed education."""

    indexed_entries = list(enumerate(entries))

    def sort_key(indexed_entry: tuple[int, EducationEntry]) -> tuple[int, int, int]:
        original_index, entry = indexed_entry
        current_rank = 0 if entry.is_current else 1
        sort_year = (
            _extract_year_for_sort(entry.start_date)
            or _extract_year_for_sort(entry.end_date)
            or 0
        )
        return (current_rank, -sort_year, original_index)

    return [entry for _index, entry in sorted(indexed_entries, key=sort_key)]


def _resolve_education_institution_name(entry: EducationEntry, *, language: str) -> str:
    """Use controlled English institution aliases when the profile provides them."""

    if language == "en":
        english_alias = _normalize_visible_whitespace(entry.institution_name_en)
        if english_alias:
            return english_alias
    return _normalize_visible_whitespace(entry.institution_name)


def _format_education_degree(entry: EducationEntry, *, language: str) -> str:
    """Format one education degree line for the fitter input without translating proper names."""

    degree = _normalize_visible_whitespace(entry.degree)
    field_of_study = _normalize_visible_whitespace(entry.field_of_study)
    if language == "en" and field_of_study:
        formatted_field_of_study = _format_english_field_of_study(field_of_study)
        normalized_degree = degree.lower()
        if _is_bachelor_degree(normalized_degree):
            return f"Bachelor's degree in {formatted_field_of_study}"
        if _is_master_degree(normalized_degree):
            return f"Master's degree in {formatted_field_of_study}"
        if degree:
            return f"{degree} in {formatted_field_of_study}"
        return formatted_field_of_study

    degree_parts = [degree, field_of_study]
    return " - ".join(part for part in degree_parts if part)


def _format_english_field_of_study(value: str) -> str:
    """Apply conservative title casing to English degree fields while preserving acronyms."""

    cleaned_value = _normalize_visible_whitespace(value)
    if not cleaned_value:
        return ""

    words = cleaned_value.split(" ")
    formatted_words: list[str] = []
    for index, word in enumerate(words):
        formatted_words.append(_format_english_field_word(word, is_first=index == 0))
    return " ".join(formatted_words)


def _format_english_field_word(word: str, *, is_first: bool) -> str:
    """Format one word without lowercasing acronyms or established mixed-case terms."""

    if not word:
        return word
    if any(character.isupper() for character in word[1:]) or word.isupper():
        return word

    lowered_word = word.lower()
    if not is_first and lowered_word in {"and", "or", "of", "in", "for", "with", "to"}:
        return lowered_word

    match = re.match(r"^([^A-Za-z]*)([A-Za-z][A-Za-z'-]*)([^A-Za-z]*)$", word)
    if match is None:
        return word
    prefix, core, suffix = match.groups()
    return f"{prefix}{core[:1].upper()}{core[1:].lower()}{suffix}"


def _is_bachelor_degree(normalized_degree: str) -> bool:
    """Return whether a degree label is safely recognizable as a bachelor's degree."""

    return any(
        marker in normalized_degree
        for marker in ("bachelor", "bsc", "b.s.", "licencjat")
    )


def _is_master_degree(normalized_degree: str) -> bool:
    """Return whether a degree label is safely recognizable as a master's degree."""

    return any(
        marker in normalized_degree
        for marker in ("master", "msc", "m.s.", "magister")
    )


def _extract_year_for_sort(value: str | None) -> int | None:
    """Extract the first visible year from a date-like value."""

    match = re.search(r"\d{4}", _normalize_visible_whitespace(value))
    if match is None:
        return None
    return int(match.group(0))


def _format_experience_date(entry: ExperienceEntry) -> str:
    """Format one experience date range for profile-backed Typst fallback entries."""

    start_label = _format_month_year_label(entry.start_date) or _normalize_visible_whitespace(entry.start_date)
    end_label = "Present" if entry.is_current else _format_month_year_label(entry.end_date)
    if not end_label and not entry.is_current:
        end_label = _normalize_visible_whitespace(entry.end_date)
    if start_label and end_label:
        return f"{start_label} - {end_label}"
    return start_label


def _format_cv_friendly_education_date_value(value: str | None) -> str:
    """Normalize education dates from ISO-like values to compact year ranges."""

    return _format_cv_friendly_date_value(value, education=True)


def _format_cv_friendly_experience_date_value(value: str | None) -> str:
    """Normalize experience dates from ISO-like values to month-year ranges."""

    return _format_cv_friendly_date_value(value, education=False)


def _format_cv_friendly_date_value(value: str | None, *, education: bool) -> str:
    """Convert a raw date or date range into a CV-friendly display value when possible."""

    cleaned_value = _normalize_visible_whitespace(value)
    if not cleaned_value:
        return ""

    date_range = _split_display_date_range(cleaned_value)
    if date_range is not None:
        start_value, end_value = date_range
        start_label = (
            _format_year_label(start_value)
            if education
            else _format_month_year_label(start_value)
        ) or start_value
        end_label = "Present" if _is_present_date_label(end_value) else (
            _format_year_label(end_value)
            if education
            else _format_month_year_label(end_value)
        ) or end_value
        if start_label and end_label:
            return f"{start_label} - {end_label}"

    single_label = (
        _format_year_label(cleaned_value)
        if education
        else _format_month_year_label(cleaned_value)
    )
    return single_label or cleaned_value


def _format_cv_friendly_date_ranges_in_text(value: str, *, education: bool) -> str:
    """Replace ISO date ranges embedded in a draft text line with compact display ranges."""

    def replace_match(match: re.Match[str]) -> str:
        return _format_cv_friendly_date_value(match.group(0), education=education)

    return re.sub(
        r"\d{4}(?:-\d{2}(?:-\d{2})?)?\s+-\s+(?:\d{4}(?:-\d{2}(?:-\d{2})?)?|Present)",
        replace_match,
        value,
    )


def _strip_certificate_issue_date_from_display(value: str) -> str:
    """Remove trailing ISO-like issue dates from short certificate display strings."""

    cleaned_value = _normalize_visible_whitespace(value)
    if not cleaned_value:
        return ""
    return re.sub(
        r"\s+-\s+\d{4}(?:-\d{2}(?:-\d{2})?)?$",
        "",
        cleaned_value,
    ).strip()


def _split_display_date_range(value: str) -> tuple[str, str] | None:
    """Split a visible date range while ignoring hyphens inside ISO dates."""

    parts = re.split(r"\s+(?:-|–|—)\s+", value, maxsplit=1)
    if len(parts) != 2:
        return None
    start_value, end_value = (part.strip() for part in parts)
    if not start_value or not end_value:
        return None
    return start_value, end_value


def _format_year_label(value: str | None) -> str | None:
    """Return a year-only label for ISO-like education dates."""

    cleaned_value = _normalize_visible_whitespace(value)
    if not cleaned_value:
        return None
    if re.fullmatch(r"\d{4}", cleaned_value):
        return cleaned_value
    if re.fullmatch(r"\d{4}-\d{2}", cleaned_value):
        return cleaned_value[:4]
    parsed_date = _parse_iso_date(cleaned_value)
    if parsed_date is not None:
        return str(parsed_date.year)
    return None


def _format_month_year_label(value: str | None) -> str | None:
    """Return a month-year label for ISO-like experience dates."""

    cleaned_value = _normalize_visible_whitespace(value)
    if not cleaned_value:
        return None
    if re.fullmatch(r"\d{4}", cleaned_value):
        return cleaned_value
    year_month_match = re.fullmatch(r"(\d{4})-(\d{2})", cleaned_value)
    if year_month_match is not None:
        year, month = year_month_match.groups()
        return _format_month_year_parts(year, month)
    parsed_date = _parse_iso_date(cleaned_value)
    if parsed_date is not None:
        return _format_month_year_parts(str(parsed_date.year), f"{parsed_date.month:02d}")
    return None


def _format_month_year_parts(year: str, month: str) -> str | None:
    """Format parsed year/month values as an English CV date label."""

    month_index = int(month)
    if month_index < 1 or month_index > 12:
        return None
    return f"{_MONTH_ABBREVIATIONS[month_index - 1]} {year}"


def _parse_iso_date(value: str) -> date | None:
    """Parse an ISO date if the value is a complete YYYY-MM-DD string."""

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _is_present_date_label(value: str | None) -> bool:
    """Return whether a date label means ongoing/current work."""

    return _normalize_visible_whitespace(value).lower() in {"present", "current", "now", "obecnie"}


def _format_language_entry(language_name: str, proficiency_level: str) -> str | None:
    """Format one fallback language entry in the same style as the draft flow."""

    cleaned_language_name = _normalize_visible_whitespace(language_name)
    if not _is_usable_language_name(cleaned_language_name):
        return None

    cleaned_proficiency_level = _normalize_optional_fallback_detail(proficiency_level)
    if cleaned_language_name and cleaned_proficiency_level:
        return f"{cleaned_language_name} - {cleaned_proficiency_level}"
    return cleaned_language_name


def _format_certificate_entry(
    certificate_name: str,
    issuer: str | None,
    issue_date: str | None,
    notes: str | None = None,
) -> str | None:
    """Format one fallback certificate entry in the same style as the draft flow."""

    _ = issue_date
    cleaned_certificate_name = _normalize_visible_whitespace(certificate_name)
    if not _is_usable_certificate_name(cleaned_certificate_name):
        return None

    cleaned_notes = _normalize_optional_fallback_detail(notes)
    if cleaned_notes and _normalize_fallback_dedupe_key(cleaned_notes) not in _normalize_fallback_dedupe_key(
        cleaned_certificate_name
    ):
        certificate_with_notes = f"{cleaned_certificate_name} ({cleaned_notes})"
        if len(certificate_with_notes) <= TYPST_LIMIT_CONFIG["languages_certificates"]["entry_hard_chars"]:
            return certificate_with_notes

    cleaned_issuer = _normalize_optional_fallback_detail(issuer)
    if cleaned_issuer and not _is_certificate_issuer_redundant(cleaned_certificate_name, cleaned_issuer):
        certificate_with_issuer = f"{cleaned_certificate_name} - {cleaned_issuer}"
        if len(certificate_with_issuer) <= TYPST_LIMIT_CONFIG["languages_certificates"]["entry_hard_chars"]:
            return certificate_with_issuer

    return cleaned_certificate_name


def _is_certificate_issuer_redundant(certificate_name: str, issuer: str) -> bool:
    """Return whether issuer already appears in a short certificate name."""

    certificate_key = _normalize_fallback_dedupe_key(certificate_name)
    issuer_key = _normalize_fallback_dedupe_key(issuer)
    if not issuer_key:
        return True
    if certificate_key == issuer_key:
        return True
    return issuer_key in set(certificate_key.split())


def _append_unique_normalized_fallback(
    fallback_values: list[str],
    seen_keys: set[str],
    value: str,
) -> None:
    """Append one fallback item once after display-safe normalization."""

    normalized_key = _normalize_fallback_dedupe_key(value)
    if not normalized_key or normalized_key in seen_keys:
        return

    fallback_values.append(value)
    seen_keys.add(normalized_key)


def _is_forbidden_certificate_fallback(
    formatted_entry: str,
    certificate_name: str,
    forbidden_certificate_keys: set[str],
) -> bool:
    """Return whether a certificate fallback is blocked by immutable profile rules."""

    if not forbidden_certificate_keys:
        return False

    return (
        _normalize_fallback_dedupe_key(formatted_entry) in forbidden_certificate_keys
        or _normalize_fallback_dedupe_key(certificate_name) in forbidden_certificate_keys
    )


def _is_usable_language_name(value: str) -> bool:
    """Return whether a language name can stand on its own in a CV section."""

    return (
        _looks_meaningful_label(value, min_chars=2)
        and not _is_date_only_value(value)
        and not _is_language_level_only_value(value)
    )


def _is_usable_certificate_name(value: str) -> bool:
    """Return whether a certificate name is specific enough for Typst fallback."""

    return (
        _looks_meaningful_label(value, min_chars=2)
        and not _is_date_only_value(value)
        and not _is_language_level_only_value(value)
    )


def _normalize_optional_fallback_detail(value: str | None, *, allow_date: bool = False) -> str | None:
    """Normalize optional fallback details without letting placeholders add noise."""

    cleaned_value = _normalize_visible_whitespace(value)
    if not cleaned_value or _is_placeholder_value(cleaned_value):
        return None
    if not allow_date and _is_date_only_value(cleaned_value):
        return None
    return cleaned_value


def _normalize_visible_whitespace(value: str | None) -> str:
    """Trim and collapse user-facing whitespace for compact fallback display."""

    return " ".join((value or "").strip().split())


def _normalize_fallback_dedupe_key(value: str | None) -> str:
    """Normalize one visible fallback string for conservative duplicate checks."""

    normalized_value = _normalize_visible_whitespace(value).lower()
    normalized_value = re.sub(r"\s*[—–-]\s*", " - ", normalized_value)
    normalized_value = re.sub(r"\s+", " ", normalized_value)
    return normalized_value.strip()


def _is_placeholder_value(value: str | None) -> bool:
    """Return whether a value is an explicit placeholder rather than CV content."""

    return _normalize_fallback_dedupe_key(value) in _PLACEHOLDER_VALUES


def _find_summary_forbidden_style_phrase(
    value: str | None,
    phrases: tuple[str, ...],
) -> str | None:
    """Return a forbidden summary style phrase found in a value, preserving matched casing."""

    if not (value or "").strip():
        return None
    for phrase in sorted(phrases, key=len, reverse=True):
        pattern = r"\s+".join(re.escape(part) for part in phrase.split())
        match = re.search(rf"\b{pattern}\b", value or "", flags=re.IGNORECASE)
        if match:
            return " ".join(match.group(0).split())
    return None


def _is_date_only_value(value: str | None) -> bool:
    """Return whether a value is only a date-like token."""

    cleaned_value = _normalize_visible_whitespace(value)
    digit_count = sum(character.isdigit() for character in cleaned_value)
    if digit_count < 4:
        return False
    return all(character.isdigit() or character in {" ", "-", ".", "/"} for character in cleaned_value)


def _is_language_level_only_value(value: str | None) -> bool:
    """Return whether a value looks like a language level without a language name."""

    normalized_value = _normalize_fallback_dedupe_key(value)
    compact_value = re.sub(r"[\s._-]+", "", normalized_value)
    return normalized_value in _LANGUAGE_LEVEL_ONLY_VALUES or compact_value in _LANGUAGE_LEVEL_ONLY_VALUES


def _join_header_left(left: str, right: str) -> str:
    """Join two visible header fragments using the same visual separator as the template."""

    cleaned_left = (left or "").strip()
    cleaned_right = (right or "").strip()
    if cleaned_left and cleaned_right:
        return f"{cleaned_left} — {cleaned_right}"
    return cleaned_left or cleaned_right


def _clean_string_list(values: list[str], limit: int | None = None) -> list[str]:
    """Trim empty list items while preserving order."""

    cleaned_values: list[str] = []
    for value in values:
        cleaned_value = (value or "").strip()
        if not cleaned_value:
            continue
        cleaned_values.append(cleaned_value)
        if limit is not None and len(cleaned_values) >= limit:
            break
    return cleaned_values
