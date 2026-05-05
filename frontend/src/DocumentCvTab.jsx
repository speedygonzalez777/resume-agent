/**
 * Final CV document tab for Typst prepare, render and artifact download.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import {
  analyzeTypstRender,
  buildTypstArtifactDownloadUrl,
  buildTypstArtifactPreviewUrl,
  fitTypstPayloadToPage,
  listResumeDrafts,
  prepareTypstResume,
  renderTypstResume,
  uploadResumePhoto,
} from "./api";
import FinalTypstPayloadEditor from "./FinalTypstPayloadEditor";
import RawJsonPanel from "./RawJsonPanel";

const MANUAL_TYPST_AUTOSAVE_VERSION = 1;
const MANUAL_TYPST_AUTOSAVE_PREFIX = "resume-agent:manual-typst-payload:v1";

function getErrorMessage(error) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Wystapil nieoczekiwany blad.";
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

function formatBytes(sizeBytes) {
  if (typeof sizeBytes !== "number") {
    return "brak danych";
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatNumber(value, fractionDigits = 1) {
  if (typeof value !== "number") {
    return "brak danych";
  }
  return value.toFixed(fractionDigits);
}

function formatPercent(value) {
  if (typeof value !== "number") {
    return "brak danych";
  }
  return `${Math.round(value * 100)}%`;
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

function createDefaultDocumentOptions() {
  return {
    language: "en",
    includePhoto: false,
    consentMode: "default",
    customConsentText: "",
  };
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

function ArtifactSummary({ artifact, renderId, artifactType, label }) {
  if (!artifact) {
    return null;
  }

  const downloadUrl = renderId ? buildTypstArtifactDownloadUrl(renderId, artifactType) : null;

  return (
    <article className="selection-card">
      <h4>{label}</h4>
      <p className="detail-text">{artifact.filename}</p>
      <p className="helper-text">{artifact.relative_path}</p>
      <p className="helper-text">
        {artifact.media_type} · {formatBytes(artifact.size_bytes)}
      </p>
      {downloadUrl ? (
        <a className="ghost-button" href={downloadUrl} download={artifact.filename}>
          Pobierz {artifactType === "pdf" ? ".pdf" : ".typ"}
        </a>
      ) : null}
    </article>
  );
}

function PdfPreview({ renderResponse, title = "Podglad PDF CV" }) {
  const pdfUrl = renderResponse?.render_id
    ? buildTypstArtifactPreviewUrl(renderResponse.render_id, "pdf")
    : null;

  if (!pdfUrl) {
    return <p className="placeholder">Po przygotowaniu dokumentu tutaj pojawi sie podglad PDF.</p>;
  }

  return (
    <div className="pdf-preview-shell">
      <iframe
        className="pdf-preview-frame"
        src={pdfUrl}
        title={title}
      />
      <div className="pdf-preview-actions">
        <a className="ghost-button" href={pdfUrl} target="_blank" rel="noreferrer">
          Otworz PDF w nowej karcie
        </a>
      </div>
    </div>
  );
}

function MetricsComparisonPanel({ beforeMetrics, afterMetrics }) {
  if (!beforeMetrics || !afterMetrics) {
    return <p className="placeholder">Porownanie metryk bedzie dostepne po renderze poprawionej wersji.</p>;
  }

  return (
    <div className="selection-grid resume-config-grid">
      <article className="selection-card">
        <h4>Wolne miejsce przed stopka</h4>
        <p className="detail-text">
          {formatNumber(beforeMetrics.free_space_before_footer_pt)} pt{" -> "}
          {formatNumber(afterMetrics.free_space_before_footer_pt)} pt
        </p>
      </article>
      <article className="selection-card">
        <h4>Wypelnienie</h4>
        <p className="detail-text">
          {formatPercent(beforeMetrics.estimated_fill_ratio)}{" -> "}{formatPercent(afterMetrics.estimated_fill_ratio)}
        </p>
      </article>
      <article className="selection-card">
        <h4>Strony</h4>
        <p className="detail-text">
          {beforeMetrics.page_count ?? "brak"}{" -> "}{afterMetrics.page_count ?? "brak"}
        </p>
        <p className="helper-text">
          Underfilled: {String(beforeMetrics.underfilled)}{" -> "}{String(afterMetrics.underfilled)} · Overfilled:{" "}
          {String(beforeMetrics.overfilled)}{" -> "}{String(afterMetrics.overfilled)}
        </p>
      </article>
    </div>
  );
}

function LayoutMetricsPanel({ metrics }) {
  if (!metrics) {
    return (
      <div className="message warning">
        Metryki ukladu PDF nie sa dostepne. Sprawdz warningi renderu.
      </div>
    );
  }

  return (
    <div className="analysis-stack">
      <div className="selection-grid resume-config-grid">
        <article className="selection-card">
          <h4>Strony</h4>
          <p className="detail-text">
            {metrics.page_count} · {metrics.is_single_page ? "jedna strona" : "wiecej niz jedna strona"}
          </p>
          <p className="helper-text">
            {metrics.overfilled ? "Ryzyko przepelnienia dokumentu." : "Brak wykrytego przepelnienia."}
          </p>
        </article>
        <article className="selection-card">
          <h4>Wypelnienie</h4>
          <p className="detail-text">{formatPercent(metrics.estimated_fill_ratio)}</p>
          <p className="helper-text">
            Wolne miejsce przed stopka: {formatNumber(metrics.free_space_before_footer_pt)} pt
          </p>
        </article>
        <article className="selection-card">
          <h4>Stopka</h4>
          <p className="detail-text">{metrics.footer_detected ? "wykryta" : "niewykryta"}</p>
          <p className="helper-text">
            {metrics.footer_overlap_risk ? "Ryzyko nachodzenia tresci na stopke." : "Bez ryzyka nachodzenia."}
          </p>
        </article>
      </div>
      {metrics.underfilled ? (
        <div className="message warning">Dokument wyglada na niedopelniony wzgledem dostepnej strony.</div>
      ) : null}
      {Array.isArray(metrics.analysis_warnings) && metrics.analysis_warnings.length > 0 ? (
        <div className="message info">{metrics.analysis_warnings.join(" ")}</div>
      ) : null}
      <RawJsonPanel summary="layout_metrics JSON" value={metrics} />
    </div>
  );
}

function QualityAnalysisPanel({ response, layoutMetrics, onFitToPage, fitLoading, fitDisabled }) {
  const analysis = response?.analysis;
  if (!analysis) {
    return <p className="placeholder">Po analizie tutaj pojawi sie diagnoza jakosci dokumentu.</p>;
  }

  const plan = analysis.fit_to_page_plan;
  const optionalFitAvailable = !analysis.should_offer_fit_to_page && hasOptionalFitToPageRoom(layoutMetrics);
  const optionalFitTooFull = !analysis.should_offer_fit_to_page && !optionalFitAvailable && isDocumentTooFullForOptionalFit(layoutMetrics);

  return (
    <div className="analysis-stack">
      <article className="selection-card">
        <h4>Status: {analysis.overall_status}</h4>
        <p className="detail-text">{analysis.summary}</p>
        <p className="helper-text">
          Model: {response.model || "brak danych"} · Pewnosc: {formatPercent(analysis.confidence)}
        </p>
      </article>

      {analysis.recommended_actions?.length ? (
        <article className="selection-card">
          <h4>Rekomendowane akcje</h4>
          <ul className="detail-list">
            {analysis.recommended_actions.map((item, index) => (
              <li key={`${item}-${index}`}>{item}</li>
            ))}
          </ul>
        </article>
      ) : null}

      <div className="selection-grid resume-config-grid">
        <article className="selection-card">
          <h4>Sekcje do rozwiniecia</h4>
          <p className="helper-text">
            {analysis.sections_to_expand?.length ? analysis.sections_to_expand.join(", ") : "brak"}
          </p>
        </article>
        <article className="selection-card">
          <h4>Sekcje do skrocenia</h4>
          <p className="helper-text">
            {analysis.sections_to_shorten?.length ? analysis.sections_to_shorten.join(", ") : "brak"}
          </p>
        </article>
      </div>

      {plan ? (
        <article className="selection-card">
          <h4>Plan fit-to-page</h4>
          <p className="detail-text">
            {plan.action} · {plan.intensity}
          </p>
          <p className="helper-text">{plan.reason}</p>
          <p className="helper-text">
            Priorytet: {plan.priority_sections?.length ? plan.priority_sections.join(", ") : "brak"} · Omijaj:{" "}
            {plan.avoid_sections?.length ? plan.avoid_sections.join(", ") : "brak"}
          </p>
        </article>
      ) : null}

      {analysis.risk_notes?.length ? (
        <div className="message warning">{analysis.risk_notes.join(" ")}</div>
      ) : null}

      {analysis.should_offer_fit_to_page ? (
        <button
          type="button"
          className="primary-button"
          onClick={() => onFitToPage({ force: false })}
          disabled={fitDisabled || fitLoading}
        >
          {fitLoading ? "Poprawianie dopasowania..." : "Popraw dopasowanie do strony"}
        </button>
      ) : optionalFitAvailable ? (
        <div className="analysis-stack">
          <div className="message info">
            Analiza nie wymaga poprawki, ale dokument ma jeszcze wolne miejsce. Mozesz opcjonalnie sprobowac rozwinac Experience i Projects.
          </div>
          <button
            type="button"
            className="ghost-button"
            onClick={() => onFitToPage({ force: true })}
            disabled={fitDisabled || fitLoading}
          >
            {fitLoading ? "Poprawianie dopasowania..." : "Rozwin tresc mimo wszystko"}
          </button>
        </div>
      ) : optionalFitTooFull ? (
        <div className="message info">Poprawka dopasowania nie jest zalecana, bo dokument jest juz wystarczajaco pelny.</div>
      ) : (
        <div className="message info">Poprawka dopasowania nie jest zalecana dla tej wersji.</div>
      )}

      <RawJsonPanel summary="AI quality analysis JSON" value={response} />
    </div>
  );
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
        <RawJsonPanel summary="Szczegoly bledu / Debug JSON" value={error.responseBody} />
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
  const manualAutosaveInitialLoadRef = useRef(false);
  const [message, setMessage] = useState(null);

  const selectedDraft = useMemo(
    () => drafts.find((draft) => String(draft.id) === String(selectedDraftId)) ?? null,
    [drafts, selectedDraftId],
  );

  const manualSourcePayload = fitResponse?.typst_payload ?? prepareResponse?.typst_payload ?? null;
  const manualSourceLabel = fitResponse?.typst_payload
    ? "Aktualna wersja AI po fit-to-page"
    : prepareResponse?.typst_payload
      ? "Pierwotna wersja AI po prepare"
      : "Brak przygotowanego payloadu";
  const manualComparisonMetrics = improvedRenderResponse?.layout_metrics ?? renderResponse?.layout_metrics ?? null;

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

  function resetPreparedDocument() {
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
        resetPreparedDocument();
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
          text: `Nie udalo sie zapisac zmian lokalnie: ${getErrorMessage(error)}`,
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
    resetPreparedDocument();
  }

  function updateDocumentOption(fieldName, nextValue) {
    setDocumentOptions((currentOptions) => ({
      ...currentOptions,
      [fieldName]: nextValue,
    }));
    setMessage(null);
    resetPreparedDocument();
  }

  async function handlePhotoUpload(file) {
    if (!file) {
      return;
    }

    setPhotoUploadLoading(true);
    setPhotoUploadError(null);
    setMessage(null);
    resetPreparedDocument();

    try {
      const payload = await uploadResumePhoto(file);
      setUploadedPhoto(payload);
      setMessage({
        type: "success",
        text: `Zdjecie zostalo zapisane jako asset ${payload.photo_asset_id}.`,
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
      return "Wgraj zdjecie albo wybierz wariant bez zdjecia.";
    }
    if (documentOptions.consentMode === "custom" && !documentOptions.customConsentText.trim()) {
      return "Wpisz tresc wlasnej klauzuli albo wybierz inny tryb klauzuli.";
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
      setMessage({ type: "success", text: "Dokument zostal przygotowany, wyrenderowany i przeanalizowany." });
    } catch (error) {
      setAnalysisResponse(null);
      setAnalysisError(buildDocumentFlowError(error, "analyze-render"));
      setMessage({
        type: "warning",
        text: "PDF zostal wygenerowany, ale analiza AI nie powiodla sie.",
      });
    } finally {
      setAnalysisLoading(false);
    }
  }

  async function handleFitToPageClick({ force = false } = {}) {
    if (!prepareResponse?.typst_payload || !analysisResponse?.analysis) {
      setFitError(buildLocalDocumentFlowError("Najpierw przygotuj i przeanalizuj dokument.", "fit-to-page"));
      return;
    }

    setFitLoading(true);
    setFitError(null);
    setFitResponse(null);
    setImprovedRenderResponse(null);
    setImprovedRenderError(null);
    resetManualDocumentState();
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
      setMessage({ type: "success", text: "Payload zostal poprawiony do podgladu poprawionej wersji." });
    } catch (error) {
      setFitResponse(null);
      setFitError(buildDocumentFlowError(error, "fit-to-page"));
    } finally {
      setFitLoading(false);
    }
  }

  async function handleImprovedRenderClick() {
    if (!fitResponse?.typst_payload) {
      setImprovedRenderError(buildLocalDocumentFlowError("Najpierw wykonaj poprawke dopasowania.", "render"));
      return;
    }

    setImprovedRenderLoading(true);
    setImprovedRenderError(null);
    setMessage(null);

    try {
      const payload = await renderTypstResume(fitResponse.typst_payload);
      setImprovedRenderResponse(payload);
      setMessage({ type: "success", text: "Poprawiona wersja PDF zostala wyrenderowana." });
    } catch (error) {
      setImprovedRenderResponse(null);
      setImprovedRenderError(buildDocumentFlowError(error, "render"));
    } finally {
      setImprovedRenderLoading(false);
    }
  }

  function openManualEditor() {
    if (!manualSourcePayload) {
      setManualRenderError(buildLocalDocumentFlowError("Najpierw przygotuj dokument.", "manual-edit"));
      return;
    }

    const nextAutosaveKey = buildManualAutosaveKey(
      manualSourcePayload,
      prepareResponse,
      selectedDraftId,
      draftVariant,
    );
    const savedRecord = readManualAutosaveRecord(nextAutosaveKey);

    setManualEditorOpen(true);
    setManualAutosaveKey(nextAutosaveKey);
    setManualRenderError(null);
    setManualRenderResponse(null);
    setMessage(null);

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
      text: "Edytor startuje od aktualnej wersji AI. Zmiany zostana zapisane lokalnie po edycji.",
    });
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
    setManualAutosaveStatus({
      type: "success",
      text: `Przywrocono lokalny zapis roboczy z ${formatSavedAt(manualAutosavePrompt.record.saved_at)}.`,
    });
  }

  function startManualEditFromAi() {
    if (!manualSourcePayload) {
      setManualRenderError(buildLocalDocumentFlowError("Nie ma aktualnej wersji AI do przywrocenia.", "manual-edit"));
      return;
    }
    manualAutosaveInitialLoadRef.current = true;
    setManualEditedPayload(deepCloneJson(manualSourcePayload));
    setManualAutosavePrompt(null);
    setManualRenderResponse(null);
    setManualRenderError(null);
    setManualAutosaveStatus({
      type: "info",
      text: "Edytor zostal ustawiony na aktualna wersje AI. Istniejacy zapis roboczy nie zostal usuniety.",
    });
  }

  function deleteManualAutosaveAndStartFromAi() {
    const keyToDelete = manualAutosavePrompt?.key ?? manualAutosaveKey;
    try {
      removeManualAutosaveRecord(keyToDelete);
      startManualEditFromAi();
      setManualAutosaveStatus({
        type: "success",
        text: "Zapis roboczy zostal usuniety. Edytor startuje od aktualnej wersji AI.",
      });
    } catch (error) {
      setManualAutosaveStatus({
        type: "error",
        text: `Nie udalo sie usunac zapisu roboczego: ${getErrorMessage(error)}`,
      });
    }
  }

  function clearManualAutosave() {
    try {
      removeManualAutosaveRecord(manualAutosaveKey);
      setManualAutosavePrompt(null);
      setManualAutosaveStatus({
        type: "success",
        text: "Lokalny zapis roboczy zostal wyczyszczony. Kolejne zmiany znowu zapisza sie automatycznie.",
      });
    } catch (error) {
      setManualAutosaveStatus({
        type: "error",
        text: `Nie udalo sie wyczyscic zapisu roboczego: ${getErrorMessage(error)}`,
      });
    }
  }

  function handleManualPayloadChange(nextPayload) {
    setManualEditedPayload(nextPayload);
    setManualRenderResponse(null);
    setManualRenderError(null);
    setMessage(null);
  }

  async function handleManualRenderClick() {
    if (!manualEditedPayload) {
      setManualRenderError(buildLocalDocumentFlowError("Najpierw otworz albo przywroc edytowana wersje.", "render"));
      return;
    }

    setManualRenderLoading(true);
    setManualRenderError(null);
    setMessage(null);

    try {
      const payload = await renderTypstResume(manualEditedPayload);
      setManualRenderResponse(payload);
      setMessage({ type: "success", text: "Edytowana recznie wersja PDF zostala wyrenderowana." });
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
  const currentActionLabel = prepareLoading
    ? "Przygotowywanie payloadu..."
    : renderLoading
      ? "Renderowanie PDF..."
      : analysisLoading
        ? "Analiza jakosci..."
        : fitLoading
          ? "Poprawianie dopasowania..."
          : improvedRenderLoading
            ? "Renderowanie poprawionej wersji..."
            : manualRenderLoading
              ? "Renderowanie edytowanej wersji..."
              : "Przygotuj dokument";

  return (
    <section className="tab-content">
      <div className="section-header tab-header">
        <div>
          <h2>Dokument CV</h2>
          <p className="section-copy">
            Przygotuj finalny TypstPayload, wyrenderuj PDF i pobierz artefakty dokumentu.
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

      <section className="section-card section-wide">
        <div className="section-header section-header-inline">
          <div>
            <h3>Zrodlo draftu</h3>
            <p className="section-copy">
              Wybierz zapisany draft i wariant, ktory ma zostac przeksztalcony w finalny dokument.
            </p>
          </div>
          <button
            type="button"
            className="ghost-button"
            onClick={() => void refreshDrafts()}
            disabled={draftsLoading || flowIsLoading}
          >
            {draftsLoading ? "Odswiezanie..." : "Odswiez drafty"}
          </button>
        </div>

        <div className="form-grid resume-form-grid">
          <label className="field section-wide-field">
            <span>Zapisany draft</span>
            <select
              className="select-input"
              value={selectedDraftId}
              onChange={(event) => handleDraftChange(event.target.value)}
              disabled={draftsLoading || flowIsLoading}
            >
              <option value="">Wybierz draft</option>
              {drafts.map((draft) => (
                <option key={draft.id} value={draft.id}>
                  Draft #{draft.id} - {draft.target_job_title || "Brak stanowiska"} -{" "}
                  {draft.target_company_name || "Brak firmy"}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Wariant</span>
            <select
              className="select-input"
              value={draftVariant}
              onChange={(event) => {
                setDraftVariant(event.target.value);
                setMessage(null);
                resetPreparedDocument();
              }}
              disabled={!selectedDraft || flowIsLoading}
            >
              <option value="base">Bazowy draft</option>
              <option value="refined" disabled={!selectedDraft?.has_refined_version}>
                AI poprawiony draft{selectedDraft?.has_refined_version ? "" : " - niedostepny"}
              </option>
            </select>
          </label>
        </div>

        {selectedDraft ? (
          <div className="selection-grid resume-config-grid">
            <article className="selection-card">
              <h4>Wybrany draft</h4>
              <p className="detail-text">
                {selectedDraft.target_job_title || "Brak stanowiska"} ·{" "}
                {selectedDraft.target_company_name || "Brak firmy"}
              </p>
              <p className="helper-text">
                Zapisano: {formatSavedAt(selectedDraft.saved_at)} · Aktualizacja:{" "}
                {formatSavedAt(selectedDraft.updated_at)}
              </p>
              <p className="helper-text">
                {selectedDraft.has_refined_version ? "Wersja AI poprawiona jest dostepna." : "Dostepny jest tylko bazowy draft."}
              </p>
            </article>
          </div>
        ) : (
          <p className="placeholder">Wybierz zapisany draft, aby skonfigurowac dokument.</p>
        )}
      </section>

      <section className="section-card section-wide">
        <div className="section-header">
          <div>
            <h3>Opcje dokumentu</h3>
            <p className="section-copy">
              Te opcje trafiaja do prepare i renderu Typst. Prepare uruchamia AI fitter dopiero po kliknieciu.
            </p>
          </div>
        </div>

        <div className="form-grid resume-form-grid">
          <label className="field">
            <span>Jezyk</span>
            <select
              className="select-input"
              value={documentOptions.language}
              onChange={(event) => updateDocumentOption("language", event.target.value)}
              disabled={flowIsLoading}
            >
              <option value="en">EN</option>
              <option value="pl">PL</option>
            </select>
          </label>

          <label className="field">
            <span>Zdjecie</span>
            <select
              className="select-input"
              value={documentOptions.includePhoto ? "yes" : "no"}
              onChange={(event) => updateDocumentOption("includePhoto", event.target.value === "yes")}
              disabled={flowIsLoading}
            >
              <option value="no">Nie</option>
              <option value="yes">Tak</option>
            </select>
          </label>

          <label className="field">
            <span>Klauzula</span>
            <select
              className="select-input"
              value={documentOptions.consentMode}
              onChange={(event) => updateDocumentOption("consentMode", event.target.value)}
              disabled={flowIsLoading}
            >
              <option value="default">Domyslna</option>
              <option value="custom">Wlasna</option>
              <option value="none">Brak</option>
            </select>
          </label>

          {documentOptions.includePhoto ? (
            <label className="field section-wide-field">
              <span>Upload zdjecia</span>
              <input
                type="file"
                accept=".jpg,.jpeg,.png,image/jpeg,image/png"
                onChange={(event) => void handlePhotoUpload(event.target.files?.[0])}
                disabled={photoUploadLoading || flowIsLoading}
              />
              <p className="helper-text">
                Akceptowane sa pliki JPG/JPEG/PNG. Upload jest wymagany tylko dla wariantu ze zdjeciem.
              </p>
              {uploadedPhoto?.photo_asset_id ? (
                <p className="helper-text">
                  Aktywny photo_asset_id: {uploadedPhoto.photo_asset_id}
                </p>
              ) : null}
            </label>
          ) : null}

          {documentOptions.consentMode === "custom" ? (
            <label className="field section-wide-field">
              <span>Wlasna klauzula</span>
              <textarea
                className="form-textarea compact-textarea"
                value={documentOptions.customConsentText}
                onChange={(event) => updateDocumentOption("customConsentText", event.target.value)}
                placeholder="Wpisz tresc klauzuli do stopki CV."
                disabled={flowIsLoading}
              />
            </label>
          ) : null}
        </div>
      </section>

      <section className="section-card section-wide">
        <div className="section-header">
          <div>
            <h3>Akcje dokumentu</h3>
            <p className="section-copy">
              Jeden krok uruchamia prepare, render pierwotnego PDF i analize jakosci dokumentu.
            </p>
          </div>
        </div>

        <div className="resume-actions" role="group" aria-label="Akcje dokumentu CV">
          <button
            type="button"
            className="primary-button resume-primary-action"
            onClick={handlePrepareClick}
            disabled={!canPrepare}
          >
            {currentActionLabel}
          </button>
        </div>
      </section>

      <section className="section-card section-wide">
        <div className="section-header">
          <div>
            <h3>Wersja pierwotna</h3>
            <p className="section-copy">Podglad PDF i artefakty wygenerowane bez automatycznej poprawki payloadu.</p>
          </div>
        </div>
        {renderResponse ? (
          <div className="document-preview-grid">
            <PdfPreview renderResponse={renderResponse} />
            <div className="analysis-stack">
              <div className="selection-grid resume-config-grid">
                <ArtifactSummary
                  artifact={renderResponse.typ_source_artifact}
                  renderId={renderResponse.render_id}
                  artifactType="typ"
                  label="Zrodlo .typ"
                />
                <ArtifactSummary
                  artifact={renderResponse.pdf_artifact}
                  renderId={renderResponse.render_id}
                  artifactType="pdf"
                  label="PDF"
                />
              </div>
              {Array.isArray(renderResponse.warnings) && renderResponse.warnings.length > 0 ? (
                <div className="message info">{renderResponse.warnings.join(" ")}</div>
              ) : null}
            </div>
          </div>
        ) : (
          <p className="placeholder">Po przygotowaniu dokumentu tutaj pojawi sie podglad PDF i artefakty.</p>
        )}
      </section>

      <div className="document-results-grid">
        <section className="section-card scroll-panel">
          <div className="section-header">
            <div>
              <h3>TypstPayload</h3>
              <p className="section-copy">Payload i debug przygotowania po kliknieciu prepare.</p>
            </div>
          </div>
          <div className="scroll-panel-body document-panel-body">
            {prepareResponse ? (
              <>
                <RawJsonPanel summary="TypstPayload" value={prepareResponse.typst_payload} />
                <RawJsonPanel summary="prepare_debug" value={prepareResponse.prepare_debug} />
              </>
            ) : (
              <p className="placeholder">Po przygotowaniu dokumentu tutaj pojawi sie TypstPayload.</p>
            )}
          </div>
        </section>

        <section className="section-card scroll-panel">
          <div className="section-header">
            <div>
              <h3>Metryki ukladu</h3>
              <p className="section-copy">Lokalna analiza PDF przez PyMuPDF.</p>
            </div>
          </div>
          <div className="scroll-panel-body document-panel-body">
            {renderResponse ? (
              <LayoutMetricsPanel metrics={renderResponse.layout_metrics} />
            ) : (
              <p className="placeholder">Po renderze tutaj pojawia sie metryki ukladu PDF.</p>
            )}
          </div>
        </section>
      </div>

      <section className="section-card section-wide">
        <div className="section-header">
          <div>
            <h3>Analiza jakosci AI</h3>
            <p className="section-copy">
              Diagnoza dokumentu i rekomendacja przyszlej poprawki dopasowania do strony.
            </p>
          </div>
        </div>
        {analysisLoading ? <div className="message info">Trwa analiza jakosci dokumentu...</div> : null}
        <QualityAnalysisPanel
          response={analysisResponse}
          layoutMetrics={renderResponse?.layout_metrics ?? null}
          onFitToPage={handleFitToPageClick}
          fitLoading={fitLoading}
          fitDisabled={flowIsLoading || !prepareResponse?.typst_payload}
        />
      </section>

      {fitResponse ? (
        <section className="section-card section-wide">
          <div className="section-header section-header-inline">
            <div>
              <h3>Poprawka dopasowania</h3>
              <p className="section-copy">
                Patch AI scalony z pierwotnym payloadem. Oryginalna wersja nie jest nadpisywana.
              </p>
            </div>
            <button
              type="button"
              className="primary-button"
              onClick={handleImprovedRenderClick}
              disabled={flowIsLoading}
            >
              {improvedRenderLoading ? "Renderowanie..." : "Podglad poprawionej wersji"}
            </button>
          </div>

          <div className="document-results-grid">
            <section className="scroll-panel">
              <div className="scroll-panel-body document-panel-body">
                <RawJsonPanel summary="Poprawiony TypstPayload" value={fitResponse.typst_payload} />
                <RawJsonPanel summary="Patch fit-to-page" value={fitResponse.patch} />
              </div>
            </section>
            <section className="scroll-panel">
              <div className="scroll-panel-body document-panel-body">
                <RawJsonPanel summary="fit_debug" value={fitResponse.fit_debug} />
                {Array.isArray(fitResponse.fit_debug?.warnings) && fitResponse.fit_debug.warnings.length > 0 ? (
                  <div className="message info">{fitResponse.fit_debug.warnings.join(" ")}</div>
                ) : null}
              </div>
            </section>
          </div>
        </section>
      ) : null}

      {improvedRenderResponse ? (
        <section className="section-card section-wide">
          <div className="section-header">
            <div>
              <h3>Wersja poprawiona</h3>
              <p className="section-copy">Osobny render poprawionego payloadu i porownanie metryk przed/po.</p>
            </div>
          </div>
          <div className="document-preview-grid">
            <PdfPreview renderResponse={improvedRenderResponse} title="Podglad poprawionej wersji PDF CV" />
            <div className="analysis-stack">
              <div className="selection-grid resume-config-grid">
                <ArtifactSummary
                  artifact={improvedRenderResponse.typ_source_artifact}
                  renderId={improvedRenderResponse.render_id}
                  artifactType="typ"
                  label="Poprawione zrodlo .typ"
                />
                <ArtifactSummary
                  artifact={improvedRenderResponse.pdf_artifact}
                  renderId={improvedRenderResponse.render_id}
                  artifactType="pdf"
                  label="Poprawiony PDF"
                />
              </div>
              {Array.isArray(improvedRenderResponse.warnings) && improvedRenderResponse.warnings.length > 0 ? (
                <div className="message info">{improvedRenderResponse.warnings.join(" ")}</div>
              ) : null}
              <MetricsComparisonPanel
                beforeMetrics={renderResponse?.layout_metrics ?? null}
                afterMetrics={improvedRenderResponse.layout_metrics}
              />
              <RawJsonPanel summary="layout_metrics poprawionej wersji" value={improvedRenderResponse.layout_metrics} />
            </div>
          </div>
        </section>
      ) : null}

      <section className="section-card section-wide">
        <div className="section-header section-header-inline">
          <div>
            <h3>Finalna edycja CV</h3>
            <p className="section-copy">
              Popraw finalny tekst w formularzu przed renderem ostatniego PDF-a. Wersje AI pozostaja dostepne jako punkt odniesienia.
            </p>
          </div>
          <button
            type="button"
            className="primary-button"
            onClick={openManualEditor}
            disabled={flowIsLoading || !manualSourcePayload}
          >
            Edytuj finalna wersje
          </button>
        </div>

        {!manualSourcePayload ? (
          <p className="placeholder">Najpierw przygotuj dokument, aby otworzyc finalny edytor.</p>
        ) : null}

        {manualEditorOpen && manualAutosavePrompt ? (
          <div className="manual-autosave-prompt">
            <div>
              <h4>Znaleziono zapis roboczy</h4>
              <p className="helper-text">
                Zapisano lokalnie: {formatSavedAt(manualAutosavePrompt.record.saved_at)}. Mozesz go przywrocic,
                zaczac od aktualnej wersji AI albo usunac zapis roboczy.
              </p>
            </div>
            <div className="manual-editor-actions">
              <button type="button" className="primary-button" onClick={restoreManualAutosave}>
                Przywroc zapisana edycje
              </button>
              <button type="button" className="ghost-button" onClick={startManualEditFromAi}>
                Zacznij od wersji AI
              </button>
              <button type="button" className="ghost-button danger-ghost-button" onClick={deleteManualAutosaveAndStartFromAi}>
                Usun zapis roboczy
              </button>
            </div>
          </div>
        ) : null}

        {manualEditorOpen && !manualAutosavePrompt ? (
          <FinalTypstPayloadEditor
            payload={manualEditedPayload}
            limitConfig={prepareResponse?.prepare_debug?.limit_config ?? {}}
            sourceLabel={manualSourceLabel}
            onChange={handleManualPayloadChange}
            onRender={handleManualRenderClick}
            onReset={startManualEditFromAi}
            onClearAutosave={clearManualAutosave}
            renderLoading={manualRenderLoading}
            autosaveStatus={manualAutosaveStatus}
          />
        ) : null}
      </section>

      {manualRenderResponse ? (
        <section className="section-card section-wide">
          <div className="section-header">
            <div>
              <h3>Wersja edytowana recznie</h3>
              <p className="section-copy">Osobny render recznie poprawionego payloadu i metryki ukladu po edycji.</p>
            </div>
          </div>
          <div className="document-preview-grid">
            <PdfPreview renderResponse={manualRenderResponse} title="Podglad recznie edytowanej wersji PDF CV" />
            <div className="analysis-stack">
              <div className="selection-grid resume-config-grid">
                <ArtifactSummary
                  artifact={manualRenderResponse.typ_source_artifact}
                  renderId={manualRenderResponse.render_id}
                  artifactType="typ"
                  label="Edytowane zrodlo .typ"
                />
                <ArtifactSummary
                  artifact={manualRenderResponse.pdf_artifact}
                  renderId={manualRenderResponse.render_id}
                  artifactType="pdf"
                  label="Edytowany PDF"
                />
              </div>
              {Array.isArray(manualRenderResponse.warnings) && manualRenderResponse.warnings.length > 0 ? (
                <div className="message info">{manualRenderResponse.warnings.join(" ")}</div>
              ) : null}
              <MetricsComparisonPanel
                beforeMetrics={manualComparisonMetrics}
                afterMetrics={manualRenderResponse.layout_metrics}
              />
              <RawJsonPanel summary="layout_metrics wersji edytowanej recznie" value={manualRenderResponse.layout_metrics} />
            </div>
          </div>
        </section>
      ) : null}
    </section>
  );
}
