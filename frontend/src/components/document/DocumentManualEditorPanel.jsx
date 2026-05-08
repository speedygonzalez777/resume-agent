/**
 * Compact workflow row for final manual editing.
 */

import FinalTypstPayloadEditor from "../../FinalTypstPayloadEditor";
import DocumentWorkflowRow from "./DocumentWorkflowRow";

/**
 * @param {{
 *   mode?: "active" | "completed" | "locked" | "available" | "editing",
 *   workflowStage?: string,
 *   manualSourcePayload: object | null,
 *   manualEditorOpen: boolean,
 *   manualAutosavePrompt: {record?: {saved_at?: string}} | null,
 *   manualEditedPayload: object | null,
 *   prepareResponse: object | null,
 *   manualRenderResponse?: object | null,
 *   manualSourceLabel: string,
 *   manualRenderLoading: boolean,
 *   manualAutosaveStatus: object | null,
 *   hasSavedLocalChanges?: boolean,
 *   flowIsLoading: boolean,
 *   formatSavedAt: (savedAt: string) => string,
 *   onOpenEditor: () => void,
 *   onCloseEditor: () => void,
 *   onRestoreAutosave: () => void,
 *   onStartFromAi: () => void,
 *   onDeleteAutosaveAndStartFromAi: () => void,
 *   onManualPayloadChange: (payload: object) => void,
 *   onManualRender: () => void,
 *   onClearAutosave: () => void,
 * }} props Component props.
 * @returns {JSX.Element} Manual editor workflow row.
 */
export default function DocumentManualEditorPanel({
  mode = "locked",
  workflowStage = "select-draft",
  manualSourcePayload,
  manualEditorOpen,
  manualAutosavePrompt,
  manualEditedPayload,
  prepareResponse,
  manualRenderResponse = null,
  manualSourceLabel,
  manualRenderLoading,
  manualAutosaveStatus,
  hasSavedLocalChanges = false,
  flowIsLoading,
  formatSavedAt,
  onOpenEditor,
  onCloseEditor,
  onRestoreAutosave,
  onStartFromAi,
  onDeleteAutosaveAndStartFromAi,
  onManualPayloadChange,
  onManualRender,
  onClearAutosave,
}) {
  const isLocked = mode === "locked";
  const hasFinalPdf = Boolean(manualRenderResponse);

  const summary = !isLocked ? (
    <div className="document-row-summary-list">
      <span>{hasFinalPdf ? "Finalny PDF gotowy" : "Edycja ręczna dostępna"}</span>
      {hasSavedLocalChanges ? <span>zmiany zapisane lokalnie</span> : null}
      {workflowStage === "final-ready" && !hasFinalPdf ? <span>gotowe do ponownego renderu</span> : null}
    </div>
  ) : null;

  const actions = manualEditorOpen ? (
    <button type="button" className="ghost-button document-row-action-button" onClick={onCloseEditor}>
      Zwiń edycję
    </button>
  ) : !isLocked ? (
    <button
      type="button"
      className={`${mode === "active" ? "primary-button" : "ghost-button"} document-row-action-button`}
      onClick={onOpenEditor}
      disabled={flowIsLoading || !manualSourcePayload}
    >
      {hasFinalPdf ? "Wróć do edycji" : "Edytuj finalną wersję"}
    </button>
  ) : null;

  const body = manualEditorOpen ? (
    <div className="document-workflow-form">
      <p className="section-copy">Popraw treść i wygeneruj finalny PDF z edycji.</p>

      {manualAutosavePrompt ? (
        <div className="manual-autosave-prompt">
          <div>
            <h4>Znaleziono zapis roboczy</h4>
            <p className="helper-text">
              Zapisano lokalnie: {formatSavedAt(manualAutosavePrompt.record.saved_at)}. Możesz go przywrócić,
              zacząć od aktualnej wersji AI albo usunąć zapis roboczy.
            </p>
          </div>
          <div className="manual-editor-actions">
            <button type="button" className="primary-button" onClick={onRestoreAutosave}>
              Przywróć zapisaną edycję
            </button>
            <button type="button" className="ghost-button" onClick={onStartFromAi}>
              Zacznij od wersji AI
            </button>
            <button type="button" className="ghost-button danger-ghost-button" onClick={onDeleteAutosaveAndStartFromAi}>
              Usuń zapis roboczy
            </button>
          </div>
        </div>
      ) : (
        <FinalTypstPayloadEditor
          payload={manualEditedPayload}
          limitConfig={prepareResponse?.prepare_debug?.limit_config ?? {}}
          sourceLabel={manualSourceLabel}
          onChange={onManualPayloadChange}
          onRender={onManualRender}
          onReset={onStartFromAi}
          onClearAutosave={onClearAutosave}
          renderLoading={manualRenderLoading}
          autosaveStatus={manualAutosaveStatus}
        />
      )}
    </div>
  ) : null;

  return (
    <DocumentWorkflowRow
      status={mode}
      expanded={manualEditorOpen}
      stepLabel="Krok 4"
      title="Finalna edycja"
      summary={summary}
      note={isLocked ? "Najpierw przygotuj PDF." : null}
      actions={actions}
      body={body}
    />
  );
}
