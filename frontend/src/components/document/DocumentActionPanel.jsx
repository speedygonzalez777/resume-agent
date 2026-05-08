/**
 * Compact workflow row for PDF preparation and fit-to-page actions.
 */

import DocumentWorkflowRow from "./DocumentWorkflowRow";

function formatPercent(value) {
  if (typeof value !== "number") {
    return null;
  }
  return `${Math.round(value * 100)}%`;
}

function formatPageCount(pageCount) {
  if (typeof pageCount !== "number") {
    return null;
  }
  return `${pageCount} ${pageCount === 1 ? "strona" : "strony"}`;
}

/**
 * @param {{
 *   mode?: "active" | "completed" | "locked" | "available" | "editing",
 *   expanded?: boolean,
 *   workflowStage?: string,
 *   fitCtaState?: string,
 *   currentActionLabel: string,
 *   canPrepare: boolean,
 *   hasPreparedPdf: boolean,
 *   hasFitPayload: boolean,
 *   hasImprovedPdf?: boolean,
 *   renderMetrics?: object | null,
 *   renderWarnings?: string[],
 *   improvedRenderLoading: boolean,
 *   flowIsLoading: boolean,
 *   onPrepare: () => void,
 *   onRenderImproved: () => void,
 *   onExpand: () => void,
 * }} props Component props.
 * @returns {JSX.Element} Generation workflow row.
 */
export default function DocumentActionPanel({
  mode = "active",
  expanded = false,
  workflowStage = "configure",
  fitCtaState = "unavailable",
  currentActionLabel,
  canPrepare,
  hasPreparedPdf,
  hasFitPayload,
  hasImprovedPdf = false,
  renderMetrics = null,
  renderWarnings = [],
  improvedRenderLoading,
  flowIsLoading,
  onPrepare,
  onRenderImproved,
  onExpand,
}) {
  const isLocked = mode === "locked";
  const isFitReady = fitCtaState === "ready-to-render";
  const needsFitAction =
    fitCtaState === "required" || fitCtaState === "optional" || fitCtaState === "ready-to-render";
  const fillRatio = formatPercent(renderMetrics?.estimated_fill_ratio);
  const pageSummary = formatPageCount(renderMetrics?.page_count);
  const warningCount = Array.isArray(renderWarnings) ? renderWarnings.length : 0;

  const summaryParts = [];
  if (hasImprovedPdf) {
    summaryParts.push("PDF po dopasowaniu gotowy");
  } else if (hasPreparedPdf) {
    summaryParts.push("Pierwszy PDF gotowy");
  } else if (!isLocked) {
    summaryParts.push("PDF jeszcze niegotowy");
  }
  if (pageSummary) {
    summaryParts.push(pageSummary);
  }
  if (fillRatio) {
    summaryParts.push(`wypełnienie ${fillRatio}`);
  }
  if (warningCount > 0) {
    summaryParts.push(`warningi: ${warningCount}`);
  }
  if (isFitReady) {
    summaryParts.push("dopasowanie gotowe");
  }

  const summary = !isLocked ? (
    <div className="document-row-summary-list">
      {summaryParts.map((item) => (
        <span key={item}>{item}</span>
      ))}
    </div>
  ) : null;

  const rowAction = isLocked ? null : isFitReady ? (
    <button
      type="button"
      className={expanded ? "primary-button document-row-action-button" : "ghost-button document-row-action-button"}
      onClick={onRenderImproved}
      disabled={flowIsLoading}
    >
      {improvedRenderLoading ? "Generowanie..." : expanded ? "Wygeneruj PDF po dopasowaniu" : "PDF po dopasowaniu"}
    </button>
  ) : !hasPreparedPdf ? (
    <button
      type="button"
      className={`${expanded ? "primary-button" : "ghost-button"} document-row-action-button`}
      onClick={onPrepare}
      disabled={!canPrepare}
    >
      {workflowStage === "configure" ? "Przygotuj PDF" : currentActionLabel}
    </button>
  ) : (
    <button type="button" className="ghost-button document-row-action-button" onClick={expanded ? onPrepare : onExpand} disabled={flowIsLoading}>
      {expanded ? "Przygotuj ponownie" : "Przygotuj ponownie"}
    </button>
  );

  const body = isLocked ? null : (
    <div className="document-workflow-form">
      <div className="document-action-stack document-action-stack-compact">
        {!isFitReady ? (
          <button
            type="button"
            className="primary-button document-primary-action"
            onClick={onPrepare}
            disabled={!canPrepare}
          >
            {workflowStage === "configure" || !hasPreparedPdf ? currentActionLabel : "Przygotuj PDF ponownie"}
          </button>
        ) : null}

        <div className="document-action-status" role="status">
          <span className={`status-badge ${hasPreparedPdf ? "success" : "warning"}`}>
            {hasPreparedPdf ? "PDF gotowy" : "Brak PDF"}
          </span>
          <p className="helper-text">
            {!hasPreparedPdf
              ? "Przygotowanie PDF uruchomi też analizę jakości dokumentu."
              : isFitReady
                ? "Dopasowanie do strony jest gotowe do wygenerowania jako osobna wersja PDF."
                : "Możesz przygotować PDF ponownie po zmianie draftu lub opcji."}
          </p>
        </div>
      </div>

      {fitCtaState === "required" ? (
        <div className="document-fit-inline-actions">
          <button
            type="button"
            className="ghost-button document-row-action-button"
            onClick={onExpand}
            disabled={flowIsLoading}
          >
            Sprawdź dopasowanie w panelu po prawej
          </button>
        </div>
      ) : null}

      {hasFitPayload && !isFitReady ? (
        <button
          type="button"
          className="ghost-button document-row-action-button"
          onClick={onRenderImproved}
          disabled={flowIsLoading}
        >
          {improvedRenderLoading ? "Generowanie..." : "Pokaż PDF po dopasowaniu"}
        </button>
      ) : null}

      {fitCtaState === "optional" ? (
        <p className="helper-text">Dokument ma wolne miejsce. Możesz spróbować wypełnić stronę w panelu po prawej.</p>
      ) : null}
    </div>
  );

  return (
    <DocumentWorkflowRow
      status={mode}
      expanded={expanded}
      stepLabel="Krok 3"
      title="Generowanie PDF"
      summary={summary}
      note={isLocked ? "Najpierw wybierz draft CV." : null}
      actions={rowAction}
      body={expanded ? body : null}
    />
  );
}
