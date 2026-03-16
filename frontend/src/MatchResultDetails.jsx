/**
 * Structured presentation of a MatchResult with a collapsible raw JSON block.
 */

/**
 * Format a fractional score into a compact percentage-like label.
 *
 * @param {number} value Numeric score in 0.0-1.0 range.
 * @returns {string} Readable score label.
 */
function formatScore(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "brak";
  }
  return `${Math.round(value * 100)}%`;
}

/**
 * Build CSS modifier for fit classification and recommendation badges.
 *
 * @param {string} value Current badge value.
 * @returns {string} CSS class suffix used by the shared badge styles.
 */
function getBadgeTone(value) {
  if (value === "high" || value === "generate" || value === "matched") {
    return "success";
  }
  if (value === "medium" || value === "generate_with_caution" || value === "partial") {
    return "warning";
  }
  return "danger";
}

/**
 * Render the structured detail view of a MatchResult payload.
 *
 * @param {{matchResult: object}} props Component props.
 * @returns {JSX.Element} Structured MatchResult detail section.
 */
export default function MatchResultDetails({ matchResult }) {
  const strengths = Array.isArray(matchResult?.strengths) ? matchResult.strengths : [];
  const gaps = Array.isArray(matchResult?.gaps) ? matchResult.gaps : [];
  const requirementMatches = Array.isArray(matchResult?.requirement_matches) ? matchResult.requirement_matches : [];

  return (
    <div className="match-result-details">
      <div className="result-summary-grid">
        <div className="result-metric-card">
          <span className="metric-label">Overall score</span>
          <strong className="metric-value">{formatScore(matchResult.overall_score)}</strong>
        </div>
        <div className="result-metric-card">
          <span className="metric-label">Fit classification</span>
          <span className={`status-badge ${getBadgeTone(matchResult.fit_classification)}`}>
            {matchResult.fit_classification}
          </span>
        </div>
        <div className="result-metric-card">
          <span className="metric-label">Recommendation</span>
          <span className={`status-badge ${getBadgeTone(matchResult.recommendation)}`}>
            {matchResult.recommendation}
          </span>
        </div>
      </div>

      <section className="detail-section">
        <h4>Final summary</h4>
        <p className="detail-text">{matchResult.final_summary || "Brak podsumowania."}</p>
      </section>

      <div className="result-columns">
        <section className="detail-section">
          <h4>Strengths</h4>
          {strengths.length > 0 ? (
            <ul className="detail-list">
              {strengths.map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="placeholder">Brak mocnych stron do pokazania.</p>
          )}
        </section>

        <section className="detail-section">
          <h4>Gaps</h4>
          {gaps.length > 0 ? (
            <ul className="detail-list">
              {gaps.map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="placeholder">Brak luk do pokazania.</p>
          )}
        </section>
      </div>

      <section className="detail-section">
        <h4>Requirement matches</h4>
        {requirementMatches.length > 0 ? (
          <div className="requirement-match-list">
            {requirementMatches.map((item) => (
              <article key={item.requirement_id} className="requirement-match-card">
                <div className="card-title-row">
                  <div>
                    <h5>{item.requirement_id}</h5>
                    <p className="helper-text">{item.explanation}</p>
                  </div>
                  <span className={`status-badge ${getBadgeTone(item.match_status)}`}>{item.match_status}</span>
                </div>

                {Array.isArray(item.matched_skill_names) && item.matched_skill_names.length > 0 ? (
                  <div className="detail-section compact-detail-section">
                    <h6>Matched skills</h6>
                    <div className="chip-row">
                      {item.matched_skill_names.map((skill) => (
                        <span key={skill} className="chip accent">
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                {Array.isArray(item.missing_elements) && item.missing_elements.length > 0 ? (
                  <div className="detail-section compact-detail-section">
                    <h6>Missing elements</h6>
                    <div className="chip-row">
                      {item.missing_elements.map((element, index) => (
                        <span key={`${element}-${index}`} className="chip missing-chip">
                          {element}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                {Array.isArray(item.evidence_texts) && item.evidence_texts.length > 0 ? (
                  <div className="detail-section compact-detail-section">
                    <h6>Evidence</h6>
                    <ul className="detail-list">
                      {item.evidence_texts.map((evidence, index) => (
                        <li key={`${evidence}-${index}`}>{evidence}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="placeholder">Brak requirement_matches do pokazania.</p>
        )}
      </section>

      <details className="raw-json-toggle">
        <summary>Raw JSON MatchResult</summary>
        <pre>{JSON.stringify(matchResult, null, 2)}</pre>
      </details>
    </div>
  );
}
