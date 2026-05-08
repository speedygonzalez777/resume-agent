/**
 * Compact metrics summary for the currently selected PDF version.
 */

function formatNumber(value, fractionDigits = 1) {
  if (typeof value !== "number") {
    return "brak";
  }
  return value.toFixed(fractionDigits);
}

function formatPercent(value) {
  if (typeof value !== "number") {
    return "brak";
  }
  return `${Math.round(value * 100)}%`;
}

/**
 * @param {{metrics: object | null | undefined, warnings?: string[]}} props Component props.
 * @returns {JSX.Element} Compact metrics list.
 */
export default function DocumentMetricsSummary({ metrics, warnings = [] }) {
  const hasWarnings = Array.isArray(warnings) && warnings.length > 0;

  if (!metrics) {
    return (
      <div className="document-status-list">
        <div className="document-status-item">
          <span>PDF</span>
          <strong>brak metryk</strong>
        </div>
      </div>
    );
  }

  return (
    <div className="document-status-list">
      <div className="document-status-item">
        <span>Strony</span>
        <strong>{metrics.page_count ?? "brak"}</strong>
        <small>{metrics.is_single_page ? "jedna strona" : "więcej niż jedna"}</small>
      </div>
      <div className="document-status-item">
        <span>Wypełnienie</span>
        <strong>{formatPercent(metrics.estimated_fill_ratio)}</strong>
        <small>{metrics.underfilled ? "niedopełniony" : "OK"}</small>
      </div>
      <div className="document-status-item">
        <span>Wolne miejsce</span>
        <strong>{formatNumber(metrics.free_space_before_footer_pt)} pt</strong>
        <small>przed stopką</small>
      </div>
      <div className="document-status-item">
        <span>Warningi</span>
        <strong>{hasWarnings ? warnings.length : "0"}</strong>
        <small>{metrics.overfilled || metrics.footer_overlap_risk ? "sprawdź układ" : "bez krytycznych"}</small>
      </div>
    </div>
  );
}
