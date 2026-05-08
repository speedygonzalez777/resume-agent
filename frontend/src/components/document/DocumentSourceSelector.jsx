/**
 * Draft selection row for the PDF document workflow.
 */

import DocumentWorkflowRow from "./DocumentWorkflowRow";

function formatDraftVariantLabel(draftVariant, hasRefinedVersion) {
  if (draftVariant === "refined") {
    return "AI poprawiony draft";
  }
  return hasRefinedVersion ? "Bazowy draft" : "Bazowy draft";
}

/**
 * @param {{
 *   mode?: "active" | "completed" | "locked" | "available" | "editing",
 *   expanded?: boolean,
 *   drafts: object[],
 *   draftsLoading: boolean,
 *   selectedDraftId: string,
 *   selectedDraft: object | null,
 *   draftVariant: string,
 *   flowIsLoading: boolean,
 *   onDraftChange: (draftId: string) => void,
 *   onDraftVariantChange: (variant: string) => void,
 *   onRefreshDrafts: () => void,
 *   onExpand: () => void,
 *   onCollapse: () => void,
 *   formatSavedAt: (savedAt: string) => string,
 * }} props Component props.
 * @returns {JSX.Element} Draft source workflow row.
 */
export default function DocumentSourceSelector({
  mode = "active",
  expanded = false,
  drafts,
  draftsLoading,
  selectedDraftId,
  selectedDraft,
  draftVariant,
  flowIsLoading,
  onDraftChange,
  onDraftVariantChange,
  onRefreshDrafts,
  onExpand,
  onCollapse,
  formatSavedAt,
}) {
  function renderControls() {
    return (
      <div className="document-workflow-form">
        <div className="document-row-toolbar">
          <button
            type="button"
            className="ghost-button document-row-action-button"
            onClick={onRefreshDrafts}
            disabled={draftsLoading || flowIsLoading}
          >
            {draftsLoading ? "Odświeżanie..." : "Odśwież listę"}
          </button>
          {selectedDraft ? (
            <button type="button" className="ghost-button document-row-action-button" onClick={onCollapse}>
              Gotowe
            </button>
          ) : null}
        </div>

        <div className="form-grid document-form-grid">
          <label className="field section-wide-field">
            <span>Zapisany draft</span>
            <select
              className="select-input"
              value={selectedDraftId}
              onChange={(event) => onDraftChange(event.target.value)}
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
              onChange={(event) => onDraftVariantChange(event.target.value)}
              disabled={!selectedDraft || flowIsLoading}
            >
              <option value="base">Bazowy draft</option>
              <option value="refined" disabled={!selectedDraft?.has_refined_version}>
                AI poprawiony draft{selectedDraft?.has_refined_version ? "" : " - niedostępny"}
              </option>
            </select>
          </label>
        </div>
      </div>
    );
  }

  const summary = selectedDraft ? (
    <div className="document-row-summary-list">
      <span>{selectedDraft.target_job_title || "Brak stanowiska"}</span>
      <span>{selectedDraft.target_company_name || "Brak firmy"}</span>
      <span>{formatDraftVariantLabel(draftVariant, selectedDraft.has_refined_version)}</span>
      <span>zapisano {formatSavedAt(selectedDraft.updated_at ?? selectedDraft.saved_at)}</span>
    </div>
  ) : null;

  const actions = selectedDraft && !expanded ? (
    <button type="button" className="ghost-button document-row-action-button" onClick={onExpand}>
      Zmień
    </button>
  ) : null;

  return (
    <DocumentWorkflowRow
      status={mode}
      expanded={expanded}
      stepLabel="Krok 1"
      title="Draft CV"
      summary={summary}
      note={!selectedDraft ? "Wybierz zapisany draft, aby przygotować dokument." : null}
      actions={actions}
      body={renderControls()}
    />
  );
}
