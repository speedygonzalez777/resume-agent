/**
 * Structured presentation of a ChangeReport together with the fit data used for generation.
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
 * @returns {string} CSS class suffix used by shared badge styles.
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
 * Build a readable label describing which fit result powered the draft.
 *
 * @param {{type?: string, id?: number | null, savedAt?: string | null} | null} matchSource Zrodlo dopasowania metadata.
 * @returns {string} Readable source label.
 */
function describeMatchSource(matchSource) {
  if (matchSource?.type === "snapshot" || matchSource?.type === "saved") {
    return matchSource?.id
      ? `Swiezy aktywny wynik roboczy zapisany jako snapshot #${matchSource.id}`
      : "Swiezy aktywny wynik roboczy zapisany jako snapshot historii";
  }
  if (matchSource?.type === "session_unsaved" || matchSource?.type === "inline") {
    return "Swiezy aktywny wynik roboczy policzony w tej sesji";
  }
  return "Brak aktywnego dopasowania roboczego";
}

/**
 * Map the backend generation mode enum to a readable Polish label.
 *
 * @param {string | null | undefined} generationMode Backend generation mode value.
 * @returns {string} User-facing label.
 */
function describeGenerationMode(generationMode) {
  if (generationMode === "openai_structured") {
    return "Generacja AI (ustrukturyzowana)";
  }
  if (generationMode === "rule_based_fallback") {
    return "Tryb zapasowy (regulowy)";
  }
  return "Brak danych";
}

/**
 * Explain the current generation mode in one short sentence.
 *
 * @param {string | null | undefined} generationMode Backend generation mode value.
 * @returns {string} Short helper text for the metadata card.
 */
function describeGenerationModeHint(generationMode) {
  if (generationMode === "openai_structured") {
    return "Draft zostal przygotowany z wykorzystaniem ustrukturyzowanej odpowiedzi AI.";
  }
  if (generationMode === "rule_based_fallback") {
    return "Draft zostal przygotowany w bezpiecznym trybie zapasowym, bez finalnego wyniku AI.";
  }
  return "Brak dodatkowych informacji o trybie generacji.";
}

/**
 * Map the fallback reason enum to a readable Polish label.
 *
 * @param {string | null | undefined} fallbackReason Backend fallback reason value.
 * @returns {string} User-facing label.
 */
function describeFallbackReason(fallbackReason) {
  if (fallbackReason === "missing_api_key") {
    return "Brak klucza API OpenAI.";
  }
  if (fallbackReason === "openai_error") {
    return "Wystapil blad po stronie integracji OpenAI.";
  }
  if (fallbackReason === "invalid_ai_output") {
    return "AI zwrocilo nieprawidlowy lub nieuzywalny wynik.";
  }
  return "Brak zarejestrowanego powodu fallbacku.";
}

/**
 * Render a string list with a placeholder fallback.
 *
 * @param {string[]} items List of strings to render.
 * @param {string} emptyText Fallback text shown when the list is empty.
 * @returns {JSX.Element} Rendered list or placeholder.
 */
function renderStringList(items, emptyText) {
  return items.length > 0 ? (
    <ul className="detail-list">
      {items.map((item, index) => (
        <li key={`${item}-${index}`}>{item}</li>
      ))}
    </ul>
  ) : (
    <p className="placeholder">{emptyText}</p>
  );
}

/**
 * Split requirement matches into covered and missing groups.
 *
 * @param {object | null} matchResult MatchResult payload used for generation.
 * @returns {{covered: object[], missing: object[]}} Requirement groups for display.
 */
function splitRequirements(matchResult) {
  const requirementMatches = Array.isArray(matchResult?.requirement_matches) ? matchResult.requirement_matches : [];

  return {
    covered: requirementMatches.filter((item) => item.match_status === "matched" || item.match_status === "partial"),
    missing: requirementMatches.filter((item) => item.match_status === "missing"),
  };
}

/**
 * Render the report explaining why the generated draft looks the way it does.
 *
 * @param {{
 *   changeReport: object,
 *   matchResult: object | null,
 *   matchSource: object | null,
 *   generationMode?: string | null,
 *   fallbackReason?: string | null,
 *   generationNotes?: string[] | null,
 * }} props Component props.
 * @returns {JSX.Element} Structured change report view.
 */
export default function ChangeReportDetails({
  changeReport,
  matchResult,
  matchSource,
  generationMode,
  fallbackReason,
  generationNotes,
}) {
  const generationMetadataNotes = Array.isArray(generationNotes) ? generationNotes : [];
  const addedElements = Array.isArray(changeReport?.added_elements) ? changeReport.added_elements : [];
  const emphasizedElements = Array.isArray(changeReport?.emphasized_elements) ? changeReport.emphasized_elements : [];
  const omittedElements = Array.isArray(changeReport?.omitted_elements) ? changeReport.omitted_elements : [];
  const omissionReasons = Array.isArray(changeReport?.omission_reasons) ? changeReport.omission_reasons : [];
  const detectedKeywords = Array.isArray(changeReport?.detected_keywords) ? changeReport.detected_keywords : [];
  const usedKeywords = Array.isArray(changeReport?.used_keywords) ? changeReport.used_keywords : [];
  const unusedKeywords = Array.isArray(changeReport?.unused_keywords) ? changeReport.unused_keywords : [];
  const blockedItems = Array.isArray(changeReport?.blocked_items) ? changeReport.blocked_items : [];
  const warnings = Array.isArray(changeReport?.warnings)
    ? changeReport.warnings.filter((item) => !generationMetadataNotes.includes(item))
    : [];
  const { covered, missing } = splitRequirements(matchResult);

  return (
    <div className="change-report-details">
      <div className="result-summary-grid resume-report-summary-grid">
        <div className="result-metric-card">
          <span className="metric-label">Zrodlo dopasowania</span>
          <strong className="metric-value compact-metric-value">{describeMatchSource(matchSource)}</strong>
        </div>
        <div className="result-metric-card">
          <span className="metric-label">Ocena dopasowania</span>
          <strong className="metric-value">{formatScore(matchResult?.overall_score)}</strong>
        </div>
        <div className="result-metric-card">
          <span className="metric-label">Klasyfikacja</span>
          <span className={`status-badge ${getBadgeTone(matchResult?.fit_classification)}`}>
            {matchResult?.fit_classification || "brak"}
          </span>
        </div>
        <div className="result-metric-card">
          <span className="metric-label">Rekomendacja</span>
          <span className={`status-badge ${getBadgeTone(matchResult?.recommendation)}`}>
            {matchResult?.recommendation || "brak"}
          </span>
        </div>
      </div>

      <section className="detail-section">
        <h4>Metadane generacji</h4>
        <div className="result-metric-card">
          <span className="metric-label">Tryb generacji</span>
          <strong className="metric-value compact-metric-value">{describeGenerationMode(generationMode)}</strong>
          <p className="helper-text">{describeGenerationModeHint(generationMode)}</p>
        </div>

        {fallbackReason ? (
          <div className="message info">
            <strong>Uzyto trybu zapasowego.</strong> Powod: {describeFallbackReason(fallbackReason)}
          </div>
        ) : null}
      </section>

      {generationMetadataNotes.length > 0 ? (
        <section className="detail-section">
          <h4>Notatki generacji</h4>
          {renderStringList(generationMetadataNotes, "Brak dodatkowych notatek o przebiegu generacji.")}
        </section>
      ) : null}

      <div className="result-columns">
        <section className="detail-section">
          <h4>Co zostalo uzyte</h4>
          {renderStringList(addedElements, "Brak zarejestrowanych uzytych elementow.")}
        </section>

        <section className="detail-section">
          <h4>Co zostalo wyeksponowane</h4>
          {renderStringList(emphasizedElements, "Brak dodatkowo wyeksponowanych elementow.")}
        </section>
      </div>

      <div className="result-columns">
        <section className="detail-section">
          <h4>Co zostalo pominiete</h4>
          {renderStringList(omittedElements, "Brak pominietych elementow do pokazania.")}
        </section>

        <section className="detail-section">
          <h4>Powody pominiecia</h4>
          {renderStringList(omissionReasons, "Brak powodow pominiecia do pokazania.")}
        </section>
      </div>

      <div className="result-columns">
        <section className="detail-section">
          <h4>Pokryte wymagania</h4>
          {covered.length > 0 ? (
            <div className="requirement-match-list">
              {covered.map((item) => (
                <article key={item.requirement_id} className="requirement-match-card">
                  <div className="card-title-row">
                    <div>
                      <h5>{item.requirement_id}</h5>
                      <p className="helper-text">{item.explanation}</p>
                    </div>
                    <span className={`status-badge ${getBadgeTone(item.match_status)}`}>{item.match_status}</span>
                  </div>

                  {Array.isArray(item.matched_skill_names) && item.matched_skill_names.length > 0 ? (
                    <div className="chip-row">
                      {item.matched_skill_names.map((skill) => (
                        <span key={skill} className="chip accent">
                          {skill}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          ) : (
            <p className="placeholder">Brak pokrytych wymagan do pokazania.</p>
          )}
        </section>

        <section className="detail-section">
          <h4>Brakujace wymagania</h4>
          {missing.length > 0 ? (
            <div className="requirement-match-list">
              {missing.map((item) => (
                <article key={item.requirement_id} className="requirement-match-card">
                  <div className="card-title-row">
                    <div>
                      <h5>{item.requirement_id}</h5>
                      <p className="helper-text">{item.explanation}</p>
                    </div>
                    <span className={`status-badge ${getBadgeTone(item.match_status)}`}>{item.match_status}</span>
                  </div>

                  {Array.isArray(item.missing_elements) && item.missing_elements.length > 0 ? (
                    <div className="chip-row">
                      {item.missing_elements.map((element, index) => (
                        <span key={`${element}-${index}`} className="chip missing-chip">
                          {element}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          ) : (
            <p className="placeholder">Brak calkowicie brakujacych wymagan.</p>
          )}
        </section>
      </div>

      <div className="result-columns">
        <section className="detail-section">
          <h4>Slowa kluczowe oferty</h4>
          {detectedKeywords.length > 0 ? (
            <div className="chip-row">
              {detectedKeywords.map((keyword) => (
                <span key={keyword} className="chip muted">
                  {keyword}
                </span>
              ))}
            </div>
          ) : (
            <p className="placeholder">Brak keywords wykrytych w ofercie.</p>
          )}
        </section>

        <section className="detail-section">
          <h4>Slowa kluczowe uzyte w draftcie</h4>
          {usedKeywords.length > 0 ? (
            <div className="chip-row">
              {usedKeywords.map((keyword) => (
                <span key={keyword} className="chip accent">
                  {keyword}
                </span>
              ))}
            </div>
          ) : (
            <p className="placeholder">Brak keywords uzytych w draftcie.</p>
          )}
        </section>
      </div>

      <div className="result-columns">
        <section className="detail-section">
          <h4>Niewykorzystane slowa kluczowe</h4>
          {unusedKeywords.length > 0 ? (
            <div className="chip-row">
              {unusedKeywords.map((keyword) => (
                <span key={keyword} className="chip missing-chip">
                  {keyword}
                </span>
              ))}
            </div>
          ) : (
            <p className="placeholder">Wszystkie wykryte keywords zostaly wykorzystane.</p>
          )}
        </section>

        <section className="detail-section">
          <h4>Zabezpieczenia truthful-first</h4>
          {renderStringList(blockedItems, "Brak zarejestrowanych zabezpieczen do pokazania.")}
        </section>
      </div>

      <section className="detail-section">
        <h4>Uwagi do przegladu</h4>
        {renderStringList(warnings, "Brak dodatkowych ostrzezen dla tego draftu.")}
      </section>

      <details className="raw-json-toggle">
        <summary>Raw JSON ChangeReport</summary>
        <pre>{JSON.stringify(changeReport, null, 2)}</pre>
      </details>
    </div>
  );
}
