/**
 * Final CV document tab for Typst prepare, render and artifact download.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import {
  analyzeTypstRender,
  fitTypstPayloadToPage,
  listResumeDrafts,
  prepareTypstResume,
  renderTypstResume,
  uploadResumePhoto,
} from "./api";
import DocumentActionPanel from "./components/document/DocumentActionPanel";
import DocumentDebugPanel from "./components/document/DocumentDebugPanel";
import DocumentManualEditorPanel from "./components/document/DocumentManualEditorPanel";
import DocumentOptionsCard from "./components/document/DocumentOptionsCard";
import DocumentQualitySummary from "./components/document/DocumentQualitySummary";
import DocumentSourceSelector from "./components/document/DocumentSourceSelector";
import DocumentWorkspace from "./components/document/DocumentWorkspace";
import PdfPreviewPanel from "./components/document/PdfPreviewPanel";
import RawJsonPanel from "./RawJsonPanel";

const MANUAL_TYPST_AUTOSAVE_VERSION = 1;
const MANUAL_TYPST_AUTOSAVE_PREFIX = "resume-agent:manual-typst-payload:v1";

function getErrorMessage(error) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Wystąpił nieoczekiwany błąd.";
}

function buildDocumentFlowError(error, stage) {
  return {
    stage,
    message: getErrorMessage(error),
    status: typeof error?.status === "number" ? error.status : null,
    responseBody: error?.responseBody ?? error?.data ?? null,
  };
}

function buildLocalDocumentFlowError(message, stage) {
  return {
    stage,
    message,
    status: null,
    responseBody: null,
  };
}

function getValidationErrors(responseBody) {
  const validationErrors = responseBody?.detail?.validation_errors;
  return Array.isArray(validationErrors) ? validationErrors : [];
}

function formatSavedAt(savedAt) {
  const parsedDate = new Date(savedAt);
  if (Number.isNaN(parsedDate.getTime())) {
    return savedAt;
  }
  return parsedDate.toLocaleString("pl-PL");
}

function createDefaultDocumentOptions() {
  return {
    language: "en",
    includePhoto: false,
    consentMode: "default",
    customConsentText: "",
  };
}

function hasOptionalFitToPageRoom(metrics) {
  if (!metrics || metrics.overfilled || metrics.footer_overlap_risk) {
    return false;
  }
  if (typeof metrics.free_space_before_footer_pt === "number" && metrics.free_space_before_footer_pt >= 80) {
    return true;
  }
  if (typeof metrics.estimated_fill_ratio === "number" && metrics.estimated_fill_ratio < 0.9) {
    return true;
  }
  return false;
}

function isDocumentTooFullForOptionalFit(metrics) {
  if (!metrics) {
    return true;
  }
  if (typeof metrics.estimated_fill_ratio === "number" && metrics.estimated_fill_ratio >= 0.92) {
    return true;
  }
  if (typeof metrics.free_space_before_footer_pt === "number" && metrics.free_space_before_footer_pt < 60) {
    return true;
  }
  return false;
}

function getWorkflowStage({
  selectedDraft,
  renderResponse,
  analysisResponse,
  fitResponse,
  improvedRenderResponse,
  manualEditorOpen,
  manualRenderResponse,
}) {
  if (!selectedDraft) {
    return "select-draft";
  }
  if (manualRenderResponse) {
    return "final-ready";
  }
  if (manualEditorOpen) {
    return "manual-editing";
  }
  if (improvedRenderResponse) {
    return "improved-ready";
  }
  if (fitResponse?.typst_payload) {
    return "fit-ready";
  }
  if (analysisResponse?.analysis) {
    return "quality-ready";
  }
  if (renderResponse) {
    return "base-ready";
  }
  return "configure";
}

function getFitCtaState({ analysisResponse, fitResponse, improvedRenderResponse, layoutMetrics }) {
  const analysis = analysisResponse?.analysis;
  if (!analysis) {
    return "unavailable";
  }
  if (improvedRenderResponse) {
    return "rendered";
  }
  if (fitResponse?.typst_payload) {
    return "ready-to-render";
  }
  if (analysis.should_offer_fit_to_page) {
    return "required";
  }
  if (hasOptionalFitToPageRoom(layoutMetrics)) {
    return "optional";
  }
  if (isDocumentTooFullForOptionalFit(layoutMetrics)) {
    return "not-needed";
  }
  return "not-recommended";
}

function getRecommendedPdfVersion({ renderResponse, improvedRenderResponse, manualRenderResponse }) {
  if (manualRenderResponse) {
    return "manual";
  }
  if (improvedRenderResponse) {
    return "improved";
  }
  if (renderResponse) {
    return "base";
  }
  return "base";
}

function buildTypstPrepareRequest(draftId, draftVariant, options, uploadedPhoto) {
  return {
    draft_id: draftId,
    draft_variant: draftVariant,
    options: {
      language: options.language,
      include_photo: options.includePhoto,
      consent_mode: options.consentMode,
      custom_consent_text:
        options.consentMode === "custom" ? options.customConsentText.trim() : null,
      photo_asset_id: options.includePhoto ? uploadedPhoto?.photo_asset_id ?? null : null,
    },
  };
}

function deepCloneJson(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

function buildStableHash(value) {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? "");
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
  }
  return hash.toString(36);
}

function sanitizeLocalStorageKeyPart(value) {
  return String(value ?? "none")
    .trim()
    .replace(/[^a-zA-Z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "none";
}

function buildManualAutosaveKey(payload, prepareResponse, selectedDraftId, draftVariant) {
  const prepareDebug = prepareResponse?.prepare_debug ?? {};
  const storedDraftId = prepareDebug.stored_resume_draft_id ?? selectedDraftId ?? null;
  const draftToken = storedDraftId
    ? `draft-${storedDraftId}`
    : `payload-${buildStableHash({
      template_name: payload?.template_name,
      profile: payload?.profile,
      summary_text: payload?.summary_text,
    })}`;
  const resolvedDraftVariant = prepareDebug.draft_variant ?? draftVariant ?? "base";
  const language = payload?.language ?? "unknown";
  const photoFlag = payload?.include_photo ? "photo" : "no-photo";
  const photoToken = payload?.photo_asset_id ? `asset-${buildStableHash(payload.photo_asset_id)}` : "no-asset";

  return [
    MANUAL_TYPST_AUTOSAVE_PREFIX,
    sanitizeLocalStorageKeyPart(draftToken),
    sanitizeLocalStorageKeyPart(resolvedDraftVariant),
    sanitizeLocalStorageKeyPart(language),
    sanitizeLocalStorageKeyPart(photoFlag),
    sanitizeLocalStorageKeyPart(photoToken),
  ].join(":");
}

function buildManualAutosaveRecord(payload, prepareResponse, selectedDraftId, draftVariant) {
  const prepareDebug = prepareResponse?.prepare_debug ?? {};
  return {
    version: MANUAL_TYPST_AUTOSAVE_VERSION,
    saved_at: new Date().toISOString(),
    metadata: {
      draft_id: selectedDraftId ? Number.parseInt(selectedDraftId, 10) : null,
      stored_resume_draft_id: prepareDebug.stored_resume_draft_id ?? null,
      draft_variant: prepareDebug.draft_variant ?? draftVariant ?? null,
      language: payload?.language ?? null,
      include_photo: payload?.include_photo ?? null,
      template_name: payload?.template_name ?? null,
    },
    payload,
  };
}

function readManualAutosaveRecord(key) {
  if (typeof window === "undefined" || !key) {
    return null;
  }
  const rawValue = window.localStorage.getItem(key);
  if (!rawValue) {
    return null;
  }
  try {
    const parsedValue = JSON.parse(rawValue);
    if (parsedValue?.version !== MANUAL_TYPST_AUTOSAVE_VERSION || !parsedValue.payload) {
      return null;
    }
    return parsedValue;
  } catch {
    return null;
  }
}

function saveManualAutosaveRecord(key, record) {
  if (typeof window === "undefined" || !key) {
    return;
  }
  window.localStorage.setItem(key, JSON.stringify(record));
}

function removeManualAutosaveRecord(key) {
  if (typeof window === "undefined" || !key) {
    return;
  }
  window.localStorage.removeItem(key);
}

function DocumentFlowErrorPanel({ error }) {
  if (!error) {
    return null;
  }

  const validationErrors = getValidationErrors(error.responseBody);

  return (
    <div className="message error document-error-panel">
      <strong>{error.message}</strong>
      <p>
        Etap: {error.stage} · Status HTTP: {error.status ?? "brak"}
      </p>
      {validationErrors.length > 0 ? (
        <ul className="detail-list">
          {validationErrors.map((item, index) => (
            <li key={`${item}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : null}
      {error.responseBody ? (
        <RawJsonPanel summary="Szczegóły błędu / Debug JSON" value={error.responseBody} />
      ) : null}
    </div>
  );
}

/**
 * Render the final Typst/PDF document flow.
 *
 * @returns {JSX.Element} Document CV tab content.
 */
export default function DocumentCvTab() {
  const [drafts, setDrafts] = useState([]);
  const [draftsLoading, setDraftsLoading] = useState(false);
  const [draftsError, setDraftsError] = useState(null);
  const [selectedDraftId, setSelectedDraftId] = useState("");
  const [draftVariant, setDraftVariant] = useState("base");
  const [documentOptions, setDocumentOptions] = useState(createDefaultDocumentOptions);
  const [uploadedPhoto, setUploadedPhoto] = useState(null);
  const [photoUploadLoading, setPhotoUploadLoading] = useState(false);
  const [photoUploadError, setPhotoUploadError] = useState(null);
  const [prepareResponse, setPrepareResponse] = useState(null);
  const [prepareLoading, setPrepareLoading] = useState(false);
  const [prepareError, setPrepareError] = useState(null);
  const [renderResponse, setRenderResponse] = useState(null);
  const [renderLoading, setRenderLoading] = useState(false);
  const [renderError, setRenderError] = useState(null);
  const [analysisResponse, setAnalysisResponse] = useState(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState(null);
  const [fitResponse, setFitResponse] = useState(null);
  const [fitLoading, setFitLoading] = useState(false);
  const [fitError, setFitError] = useState(null);
  const [improvedRenderResponse, setImprovedRenderResponse] = useState(null);
  const [improvedRenderLoading, setImprovedRenderLoading] = useState(false);
  const [improvedRenderError, setImprovedRenderError] = useState(null);
  const [manualEditorOpen, setManualEditorOpen] = useState(false);
  const [manualEditedPayload, setManualEditedPayload] = useState(null);
  const [manualRenderResponse, setManualRenderResponse] = useState(null);
  const [manualRenderLoading, setManualRenderLoading] = useState(false);
  const [manualRenderError, setManualRenderError] = useState(null);
  const [manualAutosaveStatus, setManualAutosaveStatus] = useState(null);
  const [manualAutosavePrompt, setManualAutosavePrompt] = useState(null);
  const [manualAutosaveKey, setManualAutosaveKey] = useState(null);
  const [activeDocumentVersion, setActiveDocumentVersion] = useState("base");
  const [expandedWorkflowStep, setExpandedWorkflowStep] = useState(null);
  const manualAutosaveInitialLoadRef = useRef(false);
  const [message, setMessage] = useState(null);

  const selectedDraft = useMemo(
    () => drafts.find((draft) => String(draft.id) === String(selectedDraftId)) ?? null,
    [drafts, selectedDraftId],
  );

  const manualSourcePayload = fitResponse?.typst_payload ?? prepareResponse?.typst_payload ?? null;
  const manualSourceLabel = fitResponse?.typst_payload
    ? "Aktualna wersja AI po dopasowaniu do strony"
    : prepareResponse?.typst_payload
      ? "Pierwsza wersja AI po przygotowaniu PDF"
      : "Brak przygotowanej wersji PDF";

  function resetManualDocumentState() {
    setManualEditorOpen(false);
    setManualEditedPayload(null);
    setManualRenderResponse(null);
    setManualRenderError(null);
    setManualAutosaveStatus(null);
    setManualAutosavePrompt(null);
    setManualAutosaveKey(null);
    manualAutosaveInitialLoadRef.current = false;
  }

  function clearPreparedDocumentState() {
    setPrepareResponse(null);
    setPrepareError(null);
    setRenderResponse(null);
    setRenderError(null);
    setAnalysisResponse(null);
    setAnalysisError(null);
    setFitResponse(null);
    setFitError(null);
    setImprovedRenderResponse(null);
    setImprovedRenderError(null);
    resetManualDocumentState();
    setActiveDocumentVersion("base");
  }

  async function refreshDrafts() {
    setDraftsLoading(true);
    setDraftsError(null);

    try {
      const payload = await listResumeDrafts(100);
      setDrafts(payload);
      if (selectedDraftId && !payload.some((draft) => String(draft.id) === String(selectedDraftId))) {
        setSelectedDraftId("");
        setDraftVariant("base");
        clearPreparedDocumentState();
        setExpandedWorkflowStep("source");
      }
    } catch (error) {
      setDraftsError(getErrorMessage(error));
    } finally {
      setDraftsLoading(false);
    }
  }

  useEffect(() => {
    void refreshDrafts();
  }, []);

  useEffect(() => {
    if (!manualEditorOpen || !manualEditedPayload || !manualAutosaveKey) {
      return undefined;
    }
    if (manualAutosaveInitialLoadRef.current) {
      manualAutosaveInitialLoadRef.current = false;
      return undefined;
    }

    setManualAutosaveStatus({ type: "info", text: "Zapisywanie zmian lokalnie..." });
    const timeoutId = window.setTimeout(() => {
      try {
        const record = buildManualAutosaveRecord(
          manualEditedPayload,
          prepareResponse,
          selectedDraftId,
          draftVariant,
        );
        saveManualAutosaveRecord(manualAutosaveKey, record);
        setManualAutosaveStatus({
          type: "success",
          text: `Zapis roboczy zapisany lokalnie: ${formatSavedAt(record.saved_at)}.`,
        });
      } catch (error) {
        setManualAutosaveStatus({
          type: "error",
          text: `Nie udało się zapisać zmian lokalnie: ${getErrorMessage(error)}`,
        });
      }
    }, 500);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [draftVariant, manualAutosaveKey, manualEditedPayload, manualEditorOpen, prepareResponse, selectedDraftId]);

  function handleDraftChange(nextDraftId) {
    const nextDraft = drafts.find((draft) => String(draft.id) === String(nextDraftId));
    setSelectedDraftId(nextDraftId);
    setDraftVariant(nextDraft?.has_refined_version ? draftVariant : "base");
    setMessage(null);
    clearPreparedDocumentState();
    setExpandedWorkflowStep(nextDraftId ? "options" : "source");
  }

  function handleDraftVariantChange(nextVariant) {
    setDraftVariant(nextVariant);
    setMessage(null);
    clearPreparedDocumentState();
  }

  function updateDocumentOption(fieldName, nextValue) {
    setDocumentOptions((currentOptions) => ({
      ...currentOptions,
      [fieldName]: nextValue,
    }));
    setMessage(null);
    clearPreparedDocumentState();
    setExpandedWorkflowStep("options");
  }

  async function handlePhotoUpload(file) {
    if (!file) {
      return;
    }

    setPhotoUploadLoading(true);
    setPhotoUploadError(null);
    setMessage(null);
    clearPreparedDocumentState();
    setExpandedWorkflowStep("options");

    try {
      const payload = await uploadResumePhoto(file);
      setUploadedPhoto(payload);
      setMessage({
        type: "success",
        text: "Zdjęcie zostało zapisane i będzie użyte przy generowaniu PDF.",
      });
    } catch (error) {
      setUploadedPhoto(null);
      setPhotoUploadError(getErrorMessage(error));
    } finally {
      setPhotoUploadLoading(false);
    }
  }

  function validateCanPrepare() {
    if (!selectedDraftId) {
      return "Wybierz zapisany draft CV.";
    }
    if (draftVariant === "refined" && !selectedDraft?.has_refined_version) {
      return "Ten draft nie ma wersji AI poprawionej.";
    }
    if (documentOptions.includePhoto && !uploadedPhoto?.photo_asset_id) {
      return "Wgraj zdjęcie albo wybierz wariant bez zdjęcia.";
    }
    if (documentOptions.consentMode === "custom" && !documentOptions.customConsentText.trim()) {
      return "Wpisz treść własnej klauzuli albo wybierz inny tryb klauzuli.";
    }
    return null;
  }

  async function handlePrepareClick() {
    const validationError = validateCanPrepare();
    if (validationError) {
      setPrepareError(buildLocalDocumentFlowError(validationError, "prepare"));
      return;
    }

    setPrepareLoading(true);
    setPrepareError(null);
    setRenderResponse(null);
    setRenderError(null);
    setAnalysisResponse(null);
    setAnalysisError(null);
    setFitResponse(null);
    setFitError(null);
    setImprovedRenderResponse(null);
    setImprovedRenderError(null);
    resetManualDocumentState();
    setMessage(null);

    let preparedPayload = null;
    try {
      const requestBody = buildTypstPrepareRequest(
        Number.parseInt(selectedDraftId, 10),
        draftVariant,
        documentOptions,
        uploadedPhoto,
      );
      preparedPayload = await prepareTypstResume(requestBody);
      setPrepareResponse(preparedPayload);
    } catch (error) {
      setPrepareResponse(null);
      setPrepareError(buildDocumentFlowError(error, "prepare"));
      setPrepareLoading(false);
      return;
    }
    setPrepareLoading(false);

    setRenderLoading(true);
    let renderedPayload = null;
    try {
      renderedPayload = await renderTypstResume(preparedPayload.typst_payload);
      setRenderResponse(renderedPayload);
      setActiveDocumentVersion("base");
    } catch (error) {
      setRenderResponse(null);
      setRenderError(buildDocumentFlowError(error, "render"));
      setRenderLoading(false);
      return;
    }
    setRenderLoading(false);

    setAnalysisLoading(true);
    try {
      const analysisPayload = await analyzeTypstRender({
        typst_payload: preparedPayload.typst_payload,
        layout_metrics: renderedPayload.layout_metrics ?? null,
        char_metrics: preparedPayload.prepare_debug?.char_metrics ?? {},
        limit_config: preparedPayload.prepare_debug?.limit_config ?? {},
        render_warnings: renderedPayload.warnings ?? [],
      });
      setAnalysisResponse(analysisPayload);
      setMessage({ type: "success", text: "PDF został przygotowany, wygenerowany i przeanalizowany." });
    } catch (error) {
      setAnalysisResponse(null);
      setAnalysisError(buildDocumentFlowError(error, "analyze-render"));
      setMessage({
        type: "warning",
        text: "PDF został wygenerowany, ale analiza AI nie powiodła się.",
      });
    } finally {
      setAnalysisLoading(false);
    }
  }

  async function handleFitToPageClick({ force = false } = {}) {
    if (!prepareResponse?.typst_payload || !analysisResponse?.analysis) {
      setFitError(buildLocalDocumentFlowError("Najpierw przygotuj i przeanalizuj PDF.", "fit-to-page"));
      return;
    }

    setFitLoading(true);
    setFitError(null);
    setFitResponse(null);
    setImprovedRenderResponse(null);
    setImprovedRenderError(null);
    resetManualDocumentState();
    setActiveDocumentVersion("base");
    setMessage(null);

    try {
      const storedDraftId =
        prepareResponse.prepare_debug?.stored_resume_draft_id ?? Number.parseInt(selectedDraftId, 10);
      const resolvedDraftVariant = prepareResponse.prepare_debug?.draft_variant ?? draftVariant;
      const payload = await fitTypstPayloadToPage({
        typst_payload: prepareResponse.typst_payload,
        layout_metrics: renderResponse?.layout_metrics ?? null,
        quality_analysis: analysisResponse.analysis,
        char_metrics: prepareResponse.prepare_debug?.char_metrics ?? {},
        limit_config: prepareResponse.prepare_debug?.limit_config ?? {},
        render_warnings: renderResponse?.warnings ?? [],
        force,
        draft_id: storedDraftId,
        stored_resume_draft_id: storedDraftId,
        draft_variant: resolvedDraftVariant,
      });
      setFitResponse(payload);
      setMessage({ type: "success", text: "Wersja do dopasowania strony została przygotowana do podglądu." });
    } catch (error) {
      setFitResponse(null);
      setFitError(buildDocumentFlowError(error, "fit-to-page"));
    } finally {
      setFitLoading(false);
    }
  }

  async function handleImprovedRenderClick() {
    if (!fitResponse?.typst_payload) {
      setImprovedRenderError(buildLocalDocumentFlowError("Najpierw wykonaj dopasowanie do strony.", "render"));
      return;
    }

    setImprovedRenderLoading(true);
    setImprovedRenderError(null);
    setMessage(null);

    try {
      const payload = await renderTypstResume(fitResponse.typst_payload);
      setImprovedRenderResponse(payload);
      setActiveDocumentVersion("improved");
      setMessage({ type: "success", text: "PDF po dopasowaniu został wygenerowany." });
    } catch (error) {
      setImprovedRenderResponse(null);
      setImprovedRenderError(buildDocumentFlowError(error, "render"));
    } finally {
      setImprovedRenderLoading(false);
    }
  }

  function openManualEditor() {
    if (!manualSourcePayload) {
      setManualRenderError(buildLocalDocumentFlowError("Najpierw przygotuj PDF.", "manual-edit"));
      return;
    }

    const nextAutosaveKey = buildManualAutosaveKey(
      manualSourcePayload,
      prepareResponse,
      selectedDraftId,
      draftVariant,
    );
    const savedRecord = readManualAutosaveRecord(nextAutosaveKey);
    const hasCurrentSession =
      manualAutosaveKey === nextAutosaveKey && (Boolean(manualEditedPayload) || Boolean(manualAutosavePrompt));

    setManualEditorOpen(true);
    setExpandedWorkflowStep("manual");
    setManualAutosaveKey(nextAutosaveKey);
    setManualRenderError(null);
    setMessage(null);

    if (hasCurrentSession) {
      setActiveDocumentVersion(manualRenderResponse ? "manual" : improvedRenderResponse ? "improved" : "base");
      return;
    }

    setManualRenderResponse(null);
    setActiveDocumentVersion(improvedRenderResponse ? "improved" : "base");

    if (savedRecord) {
      setManualAutosavePrompt({
        key: nextAutosaveKey,
        record: savedRecord,
      });
      setManualEditedPayload(null);
      setManualAutosaveStatus({
        type: "info",
        text: `Znaleziono lokalny zapis roboczy z ${formatSavedAt(savedRecord.saved_at)}.`,
      });
      return;
    }

    manualAutosaveInitialLoadRef.current = true;
    setManualAutosavePrompt(null);
    setManualEditedPayload(deepCloneJson(manualSourcePayload));
    setManualAutosaveStatus({
      type: "info",
      text: "Edytor startuje od aktualnej wersji AI. Zmiany zostaną zapisane lokalnie po edycji.",
    });
  }

  function closeManualEditor() {
    if (manualEditedPayload && manualAutosaveKey) {
      try {
        const record = buildManualAutosaveRecord(
          manualEditedPayload,
          prepareResponse,
          selectedDraftId,
          draftVariant,
        );
        saveManualAutosaveRecord(manualAutosaveKey, record);
        setManualAutosaveStatus({
          type: "success",
          text: `Zapis roboczy zapisany lokalnie: ${formatSavedAt(record.saved_at)}.`,
        });
      } catch (error) {
        setManualAutosaveStatus({
          type: "error",
          text: `Nie udało się zapisać zmian lokalnie: ${getErrorMessage(error)}`,
        });
      }
    }
    setManualEditorOpen(false);
    setExpandedWorkflowStep(null);
  }

  function restoreManualAutosave() {
    if (!manualAutosavePrompt?.record?.payload) {
      return;
    }
    manualAutosaveInitialLoadRef.current = true;
    setManualEditedPayload(deepCloneJson(manualAutosavePrompt.record.payload));
    setManualAutosavePrompt(null);
    setManualRenderResponse(null);
    setManualRenderError(null);
    setActiveDocumentVersion(improvedRenderResponse ? "improved" : "base");
    setManualAutosaveStatus({
      type: "success",
      text: `Przywrócono lokalny zapis roboczy z ${formatSavedAt(manualAutosavePrompt.record.saved_at)}.`,
    });
  }

  function startManualEditFromAi() {
    if (!manualSourcePayload) {
      setManualRenderError(buildLocalDocumentFlowError("Nie ma aktualnej wersji AI do przywrócenia.", "manual-edit"));
      return;
    }
    manualAutosaveInitialLoadRef.current = true;
    setManualEditedPayload(deepCloneJson(manualSourcePayload));
    setManualAutosavePrompt(null);
    setManualRenderResponse(null);
    setManualRenderError(null);
    setActiveDocumentVersion(improvedRenderResponse ? "improved" : "base");
    setManualAutosaveStatus({
      type: "info",
      text: "Edytor został ustawiony na aktualną wersję AI. Istniejący zapis roboczy nie został usunięty.",
    });
  }

  function deleteManualAutosaveAndStartFromAi() {
    const keyToDelete = manualAutosavePrompt?.key ?? manualAutosaveKey;
    try {
      removeManualAutosaveRecord(keyToDelete);
      startManualEditFromAi();
      setManualAutosaveStatus({
        type: "success",
        text: "Zapis roboczy został usunięty. Edytor startuje od aktualnej wersji AI.",
      });
    } catch (error) {
      setManualAutosaveStatus({
        type: "error",
        text: `Nie udało się usunąć zapisu roboczego: ${getErrorMessage(error)}`,
      });
    }
  }

  function clearManualAutosave() {
    try {
      removeManualAutosaveRecord(manualAutosaveKey);
      setManualAutosavePrompt(null);
      setManualAutosaveStatus({
        type: "success",
        text: "Lokalny zapis roboczy został wyczyszczony. Kolejne zmiany znowu zapiszą się automatycznie.",
      });
    } catch (error) {
      setManualAutosaveStatus({
        type: "error",
        text: `Nie udało się wyczyścić zapisu roboczego: ${getErrorMessage(error)}`,
      });
    }
  }

  function handleManualPayloadChange(nextPayload) {
    setManualEditedPayload(nextPayload);
    setManualRenderResponse(null);
    setManualRenderError(null);
    setActiveDocumentVersion(improvedRenderResponse ? "improved" : "base");
    setMessage(null);
  }

  async function handleManualRenderClick() {
    if (!manualEditedPayload) {
      setManualRenderError(buildLocalDocumentFlowError("Najpierw otwórz albo przywróć edytowaną wersję.", "render"));
      return;
    }

    setManualRenderLoading(true);
    setManualRenderError(null);
    setMessage(null);

    try {
      const payload = await renderTypstResume(manualEditedPayload);
      setManualRenderResponse(payload);
      setActiveDocumentVersion("manual");
      setMessage({ type: "success", text: "Finalny PDF z edycji został wygenerowany." });
    } catch (error) {
      setManualRenderResponse(null);
      setManualRenderError(buildDocumentFlowError(error, "render-edited"));
    } finally {
      setManualRenderLoading(false);
    }
  }

  const flowIsLoading =
    prepareLoading || renderLoading || analysisLoading || fitLoading || improvedRenderLoading || manualRenderLoading;
  const canPrepare = !flowIsLoading && !validateCanPrepare();
  const workflowStage = getWorkflowStage({
    selectedDraft,
    renderResponse,
    analysisResponse,
    fitResponse,
    improvedRenderResponse,
    manualEditorOpen,
    manualRenderResponse,
  });
  const fitCtaState = getFitCtaState({
    analysisResponse,
    fitResponse,
    improvedRenderResponse,
    layoutMetrics: renderResponse?.layout_metrics ?? null,
  });
  const recommendedPdfVersion = getRecommendedPdfVersion({
    renderResponse,
    improvedRenderResponse,
    manualRenderResponse,
  });
  const hasSavedLocalChanges = Boolean(
    manualAutosavePrompt?.record ||
      manualAutosaveStatus?.type === "success" ||
      readManualAutosaveRecord(manualAutosaveKey),
  );
  const sourceStepMode = selectedDraft ? "completed" : "active";
  const defaultExpandedStep = manualEditorOpen
    ? "manual"
    : !selectedDraft
      ? "source"
      : !renderResponse
        ? "options"
        : fitCtaState === "required" || fitCtaState === "optional" || fitCtaState === "ready-to-render"
          ? "action"
        : null;
  const canExpandOptions = Boolean(selectedDraft);
  const canExpandAction = Boolean(selectedDraft);
  const canExpandManual = Boolean(manualSourcePayload);
  const effectiveExpandedStep = manualEditorOpen
    ? "manual"
    : expandedWorkflowStep === "source"
      ? "source"
      : expandedWorkflowStep === "options" && canExpandOptions
        ? "options"
        : expandedWorkflowStep === "action" && canExpandAction
          ? "action"
          : expandedWorkflowStep === "manual" && canExpandManual
            ? "manual"
            : defaultExpandedStep;
  const sourceExpanded = effectiveExpandedStep === "source";
  const optionsExpanded = effectiveExpandedStep === "options";
  const actionExpanded = effectiveExpandedStep === "action";
  const manualExpanded = manualEditorOpen;
  const actionNeedsAttention =
    !renderResponse || fitCtaState === "required" || fitCtaState === "optional" || fitCtaState === "ready-to-render";
  const optionsStepMode = !selectedDraft
    ? "locked"
    : optionsExpanded
      ? "editing"
      : renderResponse
        ? "completed"
        : "available";
  const actionStepMode = !selectedDraft
    ? "locked"
    : actionExpanded
      ? "active"
      : actionNeedsAttention
        ? "available"
        : "completed";
  const manualStepMode = !manualSourcePayload
    ? "locked"
    : manualExpanded
      ? "editing"
      : manualRenderResponse
        ? "completed"
        : "available";
  const currentActionLabel = prepareLoading
    ? "Przygotowywanie PDF..."
    : renderLoading
      ? "Generowanie PDF..."
      : analysisLoading
        ? "Analiza jakości..."
        : fitLoading
          ? "Dopasowywanie do strony..."
          : improvedRenderLoading
            ? "Generowanie PDF po dopasowaniu..."
            : manualRenderLoading
              ? "Generowanie PDF z edycji..."
              : "Przygotuj PDF";
  const documentVersions = [
    {
      id: "base",
      label: "Bazowy",
      renderResponse,
      emptyText: "Pierwszy PDF pojawi się po kliknięciu „Przygotuj PDF”.",
    },
    {
      id: "improved",
      label: "Dopasowany",
      renderResponse: improvedRenderResponse,
      emptyText: "Ta wersja pojawi się po dopasowaniu do strony i wygenerowaniu PDF po dopasowaniu.",
    },
    {
      id: "manual",
      label: "Finalny",
      renderResponse: manualRenderResponse,
      emptyText: "Finalny PDF pojawi się po ręcznej edycji i wygenerowaniu PDF z edycji.",
    },
  ];

  return (
    <section className="tab-content document-tab-content">
      <div className="section-header tab-header">
        <div>
          <h2>PDF i edycja</h2>
          <p className="section-copy">
            Przygotuj PDF, sprawdź jakość i wykonaj finalną edycję.
          </p>
        </div>
      </div>

      {message ? <div className={`message ${message.type}`}>{message.text}</div> : null}
      {draftsError ? <div className="message error">{draftsError}</div> : null}
      {photoUploadError ? <div className="message error">{photoUploadError}</div> : null}
      <DocumentFlowErrorPanel error={prepareError} />
      <DocumentFlowErrorPanel error={renderError} />
      <DocumentFlowErrorPanel error={analysisError} />
      <DocumentFlowErrorPanel error={fitError} />
      <DocumentFlowErrorPanel error={improvedRenderError} />
      <DocumentFlowErrorPanel error={manualRenderError} />

      <DocumentWorkspace
        left={(
          <>
            <section className="document-workflow-panel">
              <div className="document-workflow-list">
                <DocumentSourceSelector
                  mode={sourceExpanded ? "active" : sourceStepMode}
                  expanded={sourceExpanded}
                  drafts={drafts}
                  draftsLoading={draftsLoading}
                  selectedDraftId={selectedDraftId}
                  selectedDraft={selectedDraft}
                  draftVariant={draftVariant}
                  flowIsLoading={flowIsLoading}
                  onDraftChange={handleDraftChange}
                  onDraftVariantChange={handleDraftVariantChange}
                  onRefreshDrafts={refreshDrafts}
                  onExpand={() => setExpandedWorkflowStep("source")}
                  onCollapse={() => setExpandedWorkflowStep(null)}
                  formatSavedAt={formatSavedAt}
                />

                <DocumentOptionsCard
                  mode={optionsStepMode}
                  expanded={optionsExpanded}
                  documentOptions={documentOptions}
                  uploadedPhoto={uploadedPhoto}
                  photoUploadLoading={photoUploadLoading}
                  flowIsLoading={flowIsLoading}
                  onOptionChange={updateDocumentOption}
                  onPhotoUpload={handlePhotoUpload}
                  onExpand={() => setExpandedWorkflowStep("options")}
                  onContinue={() => setExpandedWorkflowStep("action")}
                />

                <DocumentActionPanel
                  mode={actionStepMode}
                  expanded={actionExpanded}
                  workflowStage={workflowStage}
                  fitCtaState={fitCtaState}
                  currentActionLabel={currentActionLabel}
                  canPrepare={canPrepare}
                  hasPreparedPdf={Boolean(renderResponse)}
                  hasFitPayload={Boolean(fitResponse?.typst_payload)}
                  hasImprovedPdf={Boolean(improvedRenderResponse)}
                  renderMetrics={renderResponse?.layout_metrics ?? null}
                  renderWarnings={renderResponse?.warnings ?? []}
                  improvedRenderLoading={improvedRenderLoading}
                  flowIsLoading={flowIsLoading}
                  onPrepare={handlePrepareClick}
                  onRenderImproved={handleImprovedRenderClick}
                  onExpand={() => setExpandedWorkflowStep("action")}
                />

                <DocumentManualEditorPanel
                  mode={manualStepMode}
                  workflowStage={workflowStage}
                  manualSourcePayload={manualSourcePayload}
                  manualEditorOpen={manualExpanded}
                  manualAutosavePrompt={manualAutosavePrompt}
                  manualEditedPayload={manualEditedPayload}
                  prepareResponse={prepareResponse}
                  manualRenderResponse={manualRenderResponse}
                  manualSourceLabel={manualSourceLabel}
                  manualRenderLoading={manualRenderLoading}
                  manualAutosaveStatus={manualAutosaveStatus}
                  hasSavedLocalChanges={hasSavedLocalChanges}
                  flowIsLoading={flowIsLoading}
                  formatSavedAt={formatSavedAt}
                  onOpenEditor={openManualEditor}
                  onCloseEditor={closeManualEditor}
                  onRestoreAutosave={restoreManualAutosave}
                  onStartFromAi={startManualEditFromAi}
                  onDeleteAutosaveAndStartFromAi={deleteManualAutosaveAndStartFromAi}
                  onManualPayloadChange={handleManualPayloadChange}
                  onManualRender={handleManualRenderClick}
                  onClearAutosave={clearManualAutosave}
                />
              </div>
            </section>

            <DocumentDebugPanel
              prepareResponse={prepareResponse}
              renderResponse={renderResponse}
              analysisResponse={analysisResponse}
              fitResponse={fitResponse}
              improvedRenderResponse={improvedRenderResponse}
              manualRenderResponse={manualRenderResponse}
            />
          </>
        )}
        right={(
          <>
            <PdfPreviewPanel
              versions={documentVersions}
              activeVersion={activeDocumentVersion}
              recommendedVersion={recommendedPdfVersion}
              workflowStage={workflowStage}
              onVersionChange={setActiveDocumentVersion}
            />

            {analysisLoading ? (
              <div className="message info document-compact-message">
                Trwa analiza jakości dokumentu...
              </div>
            ) : null}

            <DocumentQualitySummary
              response={analysisResponse}
              fitCtaState={fitCtaState}
              workflowStage={workflowStage}
              fitLoading={fitLoading}
              fitDisabled={flowIsLoading || !prepareResponse?.typst_payload}
              onFitToPage={handleFitToPageClick}
            />
          </>
        )}
      />
    </section>
  );
}
