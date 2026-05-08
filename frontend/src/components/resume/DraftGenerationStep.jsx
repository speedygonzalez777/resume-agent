import DocumentWorkflowRow from "../document/DocumentWorkflowRow";

function getRecommendationNote(matchResult) {
  const recommendation = matchResult?.recommendation;
  if (recommendation === "generate_with_caution") {
    return "Dopasowanie jest średnie. Warto później uważnie przejrzeć draft przed przejściem do PDF.";
  }
  if (recommendation && recommendation !== "generate") {
    return "Dopasowanie jest słabsze. Draft nadal możesz wygenerować, ale potraktuj go jako materiał do ostrożnej korekty.";
  }
  return null;
}

/**
 * @param {{
 *   mode?: "active" | "completed" | "locked" | "available" | "editing",
 *   expanded?: boolean,
 *   activeMatchResult: object | null,
 *   resumeArtifacts: object | null,
 *   hasRefinedResumeDraft: boolean,
 *   currentResumeDraftRecordId: number | null,
 *   busy: boolean,
 *   loading: boolean,
 *   generationModeLabel: string,
 *   savedAt?: string | null,
 *   onGenerate: () => void,
 *   onExpand: () => void,
 *   onOpenReview: () => void,
 * }} props
 * @returns {JSX.Element}
 */
export default function DraftGenerationStep({
  mode = "locked",
  expanded = false,
  activeMatchResult,
  resumeArtifacts,
  hasRefinedResumeDraft,
  currentResumeDraftRecordId,
  busy,
  loading,
  generationModeLabel,
  savedAt = null,
  onGenerate,
  onExpand,
  onOpenReview,
}) {
  const isLocked = mode === "locked";
  const hasDraft = Boolean(resumeArtifacts?.resume_draft);
  const cautionNote = getRecommendationNote(activeMatchResult);

  const summary = !isLocked && hasDraft ? (
    <div className="document-row-summary-list">
      <span>{currentResumeDraftRecordId ? `Draft #${currentResumeDraftRecordId}` : "Draft gotowy"}</span>
      <span>{generationModeLabel}</span>
      <span>{hasRefinedResumeDraft ? "Poprawa AI dostępna" : "Tylko bazowy draft"}</span>
      {savedAt ? <span>zapisano {savedAt}</span> : null}
    </div>
  ) : null;

  const actions = !isLocked && !expanded && hasDraft ? (
    <>
      <button type="button" className="ghost-button document-row-action-button" onClick={onOpenReview}>
        Otwórz
      </button>
      <button
        type="button"
        className="ghost-button document-row-action-button"
        onClick={onGenerate}
        disabled={busy}
      >
        {loading ? "Generowanie..." : "Wygeneruj ponownie"}
      </button>
    </>
  ) : !isLocked && !expanded ? (
    <button type="button" className="ghost-button document-row-action-button" onClick={onExpand}>
      Otwórz
    </button>
  ) : null;

  return (
    <DocumentWorkflowRow
      status={mode}
      expanded={!isLocked && expanded}
      stepLabel="Krok 3"
      title="Draft CV"
      summary={summary}
      note={isLocked ? "Najpierw sprawdź dopasowanie." : !hasDraft ? "Wygeneruj draft na bazie aktywnego dopasowania." : null}
      actions={actions}
      body={(
        <div className="document-workflow-form">
          {cautionNote ? <div className="message info">{cautionNote}</div> : null}

          <div className="document-action-stack document-action-stack-compact">
            {!hasDraft ? (
              <button
                type="button"
                className="primary-button document-primary-action"
                onClick={onGenerate}
                disabled={busy}
              >
                {loading ? "Generowanie..." : "Wygeneruj draft CV"}
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="primary-button document-primary-action"
                  onClick={onOpenReview}
                  disabled={busy}
                >
                  Otwórz podgląd i raport
                </button>
                <button
                  type="button"
                  className="ghost-button document-row-action-button"
                  onClick={onGenerate}
                  disabled={busy}
                >
                  {loading ? "Generowanie..." : "Wygeneruj ponownie"}
                </button>
              </>
            )}
          </div>

          {hasDraft ? (
            <div className="document-status-list resume-match-status-list">
              <div className="document-status-item">
                <span>Draft</span>
                <strong>{currentResumeDraftRecordId ? `#${currentResumeDraftRecordId}` : "gotowy"}</strong>
                <small>{savedAt ? `zapisano ${savedAt}` : "sesja bieżąca"}</small>
              </div>
              <div className="document-status-item">
                <span>Tryb</span>
                <strong>{generationModeLabel}</strong>
                <small>źródło generacji</small>
              </div>
              <div className="document-status-item">
                <span>AI refinement</span>
                <strong>{hasRefinedResumeDraft ? "tak" : "nie"}</strong>
                <small>wersja poprawiona</small>
              </div>
            </div>
          ) : null}
        </div>
      )}
    />
  );
}
