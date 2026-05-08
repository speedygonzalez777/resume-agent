import DocumentWorkflowRow from "../document/DocumentWorkflowRow";
import {
  formatFitClassificationLabel,
  formatFitClassificationMetricLabel,
  formatRecommendationLabel,
  formatRecommendationMetricLabel,
  getRecommendationTone,
} from "./displayHelpers";

function formatPercent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "brak";
  }
  return `${Math.round(value * 100)}%`;
}

/**
 * @param {{
 *   mode?: "active" | "completed" | "locked" | "available" | "editing",
 *   expanded?: boolean,
 *   activeMatchResult: object | null,
 *   matchSourceLabel: string,
 *   sourceMeta?: string | null,
 *   strengthsPreview: string[],
 *   gapsPreview: string[],
 *   loading: boolean,
 *   busy: boolean,
 *   errorText?: string | null,
 *   onAnalyze: () => void,
 *   onExpand: () => void,
 *   onContinue: () => void,
 * }} props
 * @returns {JSX.Element}
 */
export default function MatchStep({
  mode = "locked",
  expanded = false,
  activeMatchResult,
  matchSourceLabel,
  sourceMeta = null,
  strengthsPreview,
  gapsPreview,
  loading,
  busy,
  errorText = null,
  onAnalyze,
  onExpand,
  onContinue,
}) {
  const isLocked = mode === "locked";
  const hasActiveMatch = Boolean(activeMatchResult);

  const summary = !isLocked && hasActiveMatch ? (
    <div className="document-row-summary-list">
      <span>{formatPercent(activeMatchResult.overall_score)}</span>
      <span>{formatFitClassificationLabel(activeMatchResult.fit_classification)}</span>
      <span>{formatRecommendationLabel(activeMatchResult.recommendation)}</span>
      <span>{matchSourceLabel}</span>
    </div>
  ) : null;

  const actions = !isLocked && !expanded && hasActiveMatch ? (
    <button type="button" className="ghost-button document-row-action-button" onClick={onExpand}>
      Otwórz
    </button>
  ) : null;

  return (
    <DocumentWorkflowRow
      status={mode}
      expanded={!isLocked && expanded}
      stepLabel="Krok 2"
      title="Dopasowanie"
      summary={summary}
      note={isLocked ? "Najpierw wybierz profil i ofertę." : !hasActiveMatch ? "Policz świeży wynik dla tej pary." : null}
      actions={actions}
      body={(
        <div className="document-workflow-form">
          {errorText ? <div className="message error">{errorText}</div> : null}

          <div className="document-action-stack document-action-stack-compact">
            <button
              type="button"
              className="primary-button document-primary-action"
              onClick={onAnalyze}
              disabled={busy}
            >
              {loading ? "Sprawdzanie..." : hasActiveMatch ? "Sprawdź dopasowanie ponownie" : "Sprawdź dopasowanie"}
            </button>

            {hasActiveMatch ? (
              <div className="document-action-status" role="status">
                <span className={`status-badge ${getRecommendationTone(activeMatchResult.recommendation)}`}>
                  {formatRecommendationLabel(activeMatchResult.recommendation)}
                </span>
                <p className="helper-text">
                  {sourceMeta || matchSourceLabel}
                </p>
              </div>
            ) : (
              <p className="helper-text">
                Świeży wynik dopasowania stanie się aktywną bazą dla generowania draftu CV.
              </p>
            )}
          </div>

          {hasActiveMatch ? (
            <>
              <div className="document-status-list resume-match-status-list">
                <div className="document-status-item">
                  <span>Wynik</span>
                  <strong>{formatPercent(activeMatchResult.overall_score)}</strong>
                </div>
                <div className="document-status-item">
                  <span>Dopasowanie</span>
                  <strong>{formatFitClassificationMetricLabel(activeMatchResult.fit_classification)}</strong>
                </div>
                <div className="document-status-item">
                  <span>Rekomendacja</span>
                  <strong>{formatRecommendationMetricLabel(activeMatchResult.recommendation)}</strong>
                </div>
              </div>

              {activeMatchResult.final_summary ? (
                <p className="detail-text resume-match-summary-copy">{activeMatchResult.final_summary}</p>
              ) : null}

              {(strengthsPreview.length > 0 || gapsPreview.length > 0) ? (
                <div className="resume-match-insight-grid">
                  <section className="resume-match-insight-card">
                    <h4>Mocne strony</h4>
                    {strengthsPreview.length > 0 ? (
                      <ul className="detail-list">
                        {strengthsPreview.map((item, index) => (
                          <li key={`${item}-${index}`}>{item}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="placeholder">Brak skrótu mocnych stron.</p>
                    )}
                  </section>

                  <section className="resume-match-insight-card">
                    <h4>Luki</h4>
                    {gapsPreview.length > 0 ? (
                      <ul className="detail-list">
                        {gapsPreview.map((item, index) => (
                          <li key={`${item}-${index}`}>{item}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="placeholder">Brak skrótu luk.</p>
                    )}
                  </section>
                </div>
              ) : null}

              <div className="document-row-toolbar">
                <button
                  type="button"
                  className="primary-button document-row-action-button"
                  onClick={onContinue}
                  disabled={busy}
                >
                  Przejdź do draftu
                </button>
              </div>
            </>
          ) : null}
        </div>
      )}
    />
  );
}
