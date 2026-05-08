/**
 * Short quality verdict and fit-to-page actions for the PDF side panel.
 */

function formatPercent(value) {
  if (typeof value !== "number") {
    return "brak danych";
  }
  return `${Math.round(value * 100)}%`;
}

function getShortText(value, maxLength = 170) {
  const text = String(value ?? "").trim();
  if (!text || text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength).trim()}...`;
}

function getVerdictTone(fitCtaState) {
  if (fitCtaState === "required") {
    return "warning";
  }
  if (fitCtaState === "optional" || fitCtaState === "ready-to-render") {
    return "info";
  }
  return "success";
}

function getVerdictLabel(fitCtaState, status) {
  if (fitCtaState === "required") {
    return "Warto dopasować";
  }
  if (fitCtaState === "optional") {
    return "Można dopracować";
  }
  if (fitCtaState === "ready-to-render") {
    return "Dopasowanie gotowe";
  }
  if (fitCtaState === "rendered") {
    return "PDF dopasowany";
  }
  return status || "OK";
}

/**
 * @param {{
 *   response: object | null,
 *   fitCtaState: string,
 *   workflowStage: string,
 *   fitLoading: boolean,
 *   fitDisabled: boolean,
 *   onFitToPage: ({force}: {force: boolean}) => void,
 * }} props Component props.
 * @returns {JSX.Element} Quality summary panel.
 */
export default function DocumentQualitySummary({
  response,
  fitCtaState,
  workflowStage,
  fitLoading,
  fitDisabled,
  onFitToPage,
}) {
  const analysis = response?.analysis;

  if (!analysis) {
    return (
      <section className="document-side-section document-quality-verdict is-empty">
        <h4>Werdykt jakości</h4>
        <p className="placeholder">
          {workflowStage === "select-draft"
            ? "Wybierz draft, aby rozpocząć przygotowanie PDF."
            : "Po przygotowaniu PDF pojawi się krótki werdykt jakości."}
        </p>
      </section>
    );
  }

  const verdictTone = getVerdictTone(fitCtaState);
  const verdictLabel = getVerdictLabel(fitCtaState, analysis.overall_status);
  const shortSummary = getShortText(analysis.summary);

  return (
    <section className={`document-side-section document-quality-verdict document-verdict-${verdictTone}`}>
      <div className="section-header section-header-inline document-mini-header">
        <div>
          <h4>Werdykt jakości</h4>
          <p className="helper-text">Pewność: {formatPercent(analysis.confidence)}</p>
        </div>
        <span className={`status-badge ${verdictTone}`}>{verdictLabel}</span>
      </div>

      {shortSummary ? <p className="detail-text document-verdict-copy">{shortSummary}</p> : null}

      {fitCtaState === "required" ? (
        <button
          type="button"
          className="primary-button document-side-action"
          onClick={() => onFitToPage({ force: false })}
          disabled={fitDisabled || fitLoading}
        >
          {fitLoading ? "Dopasowywanie..." : "Dopasuj do strony"}
        </button>
      ) : fitCtaState === "optional" ? (
        <>
          <div className="message info">
            Analiza nie wymaga poprawki, ale dokument ma jeszcze wolne miejsce.
          </div>
          <button
            type="button"
            className="ghost-button document-side-action"
            onClick={() => onFitToPage({ force: true })}
            disabled={fitDisabled || fitLoading}
          >
            {fitLoading ? "Dopasowywanie..." : "Spróbuj wypełnić stronę"}
          </button>
        </>
      ) : fitCtaState === "ready-to-render" ? (
        <div className="message info">
          Dopasowanie jest przygotowane. Wygeneruj PDF po dopasowaniu w lewym panelu.
        </div>
      ) : null}

      {fitCtaState === "not-needed" || fitCtaState === "not-recommended" || fitCtaState === "rendered" ? (
        <p className="helper-text document-verdict-note">
          Szczegóły analizy i rekomendacje są dostępne w sekcji technicznej.
        </p>
      ) : null}
    </section>
  );
}
