/**
 * Structured presentation of a ChangeReport together with the fit data used for generation.
 */

import {
  formatFitClassificationLabel,
  formatRecommendationLabel,
  formatRequirementStatusLabel,
} from "./components/resume/displayHelpers";
import RawJsonPanel from "./RawJsonPanel";

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
      ? `Świeży wynik dopasowania zapisany jako wynik #${matchSource.id}`
      : "Świeży wynik dopasowania zapisany w historii";
  }
  if (matchSource?.type === "session_unsaved" || matchSource?.type === "inline") {
    return "Świeży wynik dopasowania policzony w tej sesji";
  }
  return "Brak aktywnego wyniku dopasowania";
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
    return "Draft został przygotowany z wykorzystaniem ustrukturyzowanej odpowiedzi AI.";
  }
  if (generationMode === "rule_based_fallback") {
    return "Draft został przygotowany w bezpiecznym trybie zapasowym, bez finalnego wyniku AI.";
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
    return "Wystąpił błąd po stronie integracji OpenAI.";
  }
  if (fallbackReason === "invalid_ai_output") {
    return "AI zwróciło nieprawidłowy lub nieużywalny wynik.";
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
 * @returns {{covered: object[], missing: object[], unresolved: object[]}} Requirement groups for display.
 */
function splitRequirements(matchResult) {
  const requirementMatches = Array.isArray(matchResult?.requirement_matches) ? matchResult.requirement_matches : [];

  return {
    covered: requirementMatches.filter((item) => item.match_status === "matched" || item.match_status === "partial"),
    missing: requirementMatches.filter((item) => item.match_status === "missing"),
    unresolved: requirementMatches.filter((item) => item.match_status === "not_verifiable"),
  };
}

function buildReportVerdict(matchResult, missingCount, unresolvedCount, warningCount, blockedCount) {
  if (matchResult?.recommendation === "do_not_recommend" || missingCount > 0 || blockedCount > 0) {
    return "Draft wymaga uważnego sprawdzenia przed przejściem do PDF.";
  }
  if (matchResult?.recommendation === "generate_with_caution" || unresolvedCount > 0 || warningCount > 0) {
    return "Draft wygląda obiecująco, ale warto go przejrzeć przed dalszym etapem.";
  }
  return "Draft wygląda spójnie i można przejść do dalszej pracy nad dokumentem.";
}

function buildReportHighlights({
  addedCount,
  omittedCount,
  missingCount,
  unresolvedCount,
  warningCount,
  blockedCount,
}) {
  const highlights = [];

  if (missingCount > 0) {
    highlights.push(`Brakuje ${missingCount} wymaga${missingCount === 1 ? "nia" : "ń"}, które warto sprawdzić ręcznie.`);
  }
  if (unresolvedCount > 0) {
    highlights.push(`Dla ${unresolvedCount} wymaga${unresolvedCount === 1 ? "nia" : "ń"} nie udało się znaleźć bezpiecznego potwierdzenia.`);
  }
  if (omittedCount > 0) {
    highlights.push(`Pominięto ${omittedCount} element${omittedCount === 1 ? "" : "ów"} z profilu, żeby lepiej dopasować draft do oferty.`);
  }
  if (warningCount > 0) {
    highlights.push(`Raport zgłasza ${warningCount} ${warningCount === 1 ? "uwagę" : "uwagi"} do ręcznej weryfikacji.`);
  }
  if (blockedCount > 0) {
    highlights.push(`Zadziałały zabezpieczenia truthful-first dla ${blockedCount} ${blockedCount === 1 ? "elementu" : "elementów"}.`);
  }
  if (addedCount > 0 && highlights.length < 4) {
    highlights.push(`W drafcie wykorzystano ${addedCount} ${addedCount === 1 ? "element" : "elementów"} z profilu kandydata.`);
  }

  return highlights.slice(0, 4);
}

function ExpandableReportSection({ title, meta = null, children, defaultOpen = false }) {
  return (
    <details className="report-disclosure" open={defaultOpen ? true : undefined}>
      <summary className="report-disclosure-summary">
        <span>{title}</span>
        {meta ? <span className="report-disclosure-meta">{meta}</span> : null}
      </summary>
      <div className="report-disclosure-body">{children}</div>
    </details>
  );
}

function RequirementMatchDisclosure({ item }) {
  const matchedSkills = Array.isArray(item.matched_skill_names) ? item.matched_skill_names : [];
  const missingElements = Array.isArray(item.missing_elements) ? item.missing_elements : [];

  return (
    <details className="requirement-match-disclosure">
      <summary className="requirement-match-summary">
        <div className="requirement-match-summary-main">
          <strong>{item.requirement_id}</strong>
          <p className="helper-text">{item.explanation}</p>
        </div>
        <span className={`status-badge ${getBadgeTone(item.match_status)}`}>
          {formatRequirementStatusLabel(item.match_status)}
        </span>
      </summary>

      <div className="requirement-match-body">
        <p className="detail-text">{item.explanation}</p>

        {matchedSkills.length > 0 ? (
          <div className="detail-section compact-detail-section">
            <h6>Powiązane umiejętności</h6>
            <div className="chip-row">
              {matchedSkills.map((skill) => (
                <span key={skill} className="chip accent">
                  {skill}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        {missingElements.length > 0 ? (
          <div className="detail-section compact-detail-section">
            <h6>Brakujące elementy</h6>
            <div className="chip-row">
              {missingElements.map((element, index) => (
                <span key={`${element}-${index}`} className="chip missing-chip">
                  {element}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </details>
  );
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
  const { covered, missing, unresolved } = splitRequirements(matchResult);
  const warningCount = warnings.length;
  const blockedCount = blockedItems.length;
  const reportVerdict = buildReportVerdict(
    matchResult,
    missing.length,
    unresolved.length,
    warningCount,
    blockedCount,
  );
  const reportHighlights = buildReportHighlights({
    addedCount: addedElements.length,
    omittedCount: omittedElements.length,
    missingCount: missing.length,
    unresolvedCount: unresolved.length,
    warningCount,
    blockedCount,
  });

  return (
    <div className="change-report-details">
      <section className="resume-report-overview">
        <div className="resume-report-overview-copy">
          <h4>Raport w skrócie</h4>
          <p className="detail-text">{reportVerdict}</p>
        </div>

        <div className="result-summary-grid resume-report-quick-grid">
          <div className="result-metric-card">
            <span className="metric-label">Użyte elementy</span>
            <strong className="metric-value">{addedElements.length}</strong>
          </div>
          <div className="result-metric-card">
            <span className="metric-label">Pominięte</span>
            <strong className="metric-value">{omittedElements.length}</strong>
          </div>
          <div className="result-metric-card">
            <span className="metric-label">Pokryte wymagania</span>
            <strong className="metric-value">{covered.length}</strong>
          </div>
          <div className="result-metric-card">
            <span className="metric-label">Ryzyka i uwagi</span>
            <strong className="metric-value">{missing.length + unresolved.length + warningCount + blockedCount}</strong>
          </div>
        </div>

        {reportHighlights.length > 0 ? (
          <ul className="resume-context-summary-points">
            {reportHighlights.map((item, index) => (
              <li key={`${item}-${index}`}>{item}</li>
            ))}
          </ul>
        ) : null}
      </section>

      <div className="result-summary-grid resume-report-summary-grid">
        <div className="result-metric-card">
          <span className="metric-label">Źródło dopasowania</span>
          <strong className="metric-value compact-metric-value">{describeMatchSource(matchSource)}</strong>
        </div>
        <div className="result-metric-card">
          <span className="metric-label">Ocena dopasowania</span>
          <strong className="metric-value">{formatScore(matchResult?.overall_score)}</strong>
        </div>
        <div className="result-metric-card">
          <span className="metric-label">Klasyfikacja</span>
          <span className={`status-badge ${getBadgeTone(matchResult?.fit_classification)}`}>
            {formatFitClassificationLabel(matchResult?.fit_classification, "brak")}
          </span>
        </div>
        <div className="result-metric-card">
          <span className="metric-label">Rekomendacja</span>
          <span className={`status-badge ${getBadgeTone(matchResult?.recommendation)}`}>
            {formatRecommendationLabel(matchResult?.recommendation, "brak")}
          </span>
        </div>
      </div>

      <div className="resume-report-disclosures">
        <ExpandableReportSection title="Pokaż metadane generacji" meta={describeGenerationMode(generationMode)}>
          <div className="result-metric-card">
            <span className="metric-label">Tryb generacji</span>
            <strong className="metric-value compact-metric-value">{describeGenerationMode(generationMode)}</strong>
            <p className="helper-text">{describeGenerationModeHint(generationMode)}</p>
          </div>

          {fallbackReason ? (
            <div className="message info">
              <strong>Użyto trybu zapasowego.</strong> Powód: {describeFallbackReason(fallbackReason)}
            </div>
          ) : null}

          {generationMetadataNotes.length > 0 ? (
            <div className="detail-section compact-detail-section">
              <h6>Notatki generacji</h6>
              {renderStringList(generationMetadataNotes, "Brak dodatkowych notatek o przebiegu generacji.")}
            </div>
          ) : null}
        </ExpandableReportSection>

        <ExpandableReportSection title="Pokaż użyte elementy" meta={`${addedElements.length} pozycji`}>
          <div className="result-columns">
            <section className="detail-section compact-detail-section">
              <h6>Co zostało użyte</h6>
              {renderStringList(addedElements, "Brak zarejestrowanych użytych elementów.")}
            </section>

            <section className="detail-section compact-detail-section">
              <h6>Co zostało wyeksponowane</h6>
              {renderStringList(emphasizedElements, "Brak dodatkowo wyeksponowanych elementów.")}
            </section>
          </div>
        </ExpandableReportSection>

        <ExpandableReportSection title="Pokaż pominięte elementy" meta={`${omittedElements.length} pozycji`}>
          <div className="result-columns">
            <section className="detail-section compact-detail-section">
              <h6>Co zostało pominięte</h6>
              {renderStringList(omittedElements, "Brak pominiętych elementów do pokazania.")}
            </section>

            <section className="detail-section compact-detail-section">
              <h6>Powody pominięcia</h6>
              {renderStringList(omissionReasons, "Brak powodów pominięcia do pokazania.")}
            </section>
          </div>
        </ExpandableReportSection>

        <ExpandableReportSection
          title="Pokaż pokrycie wymagań"
          meta={`${covered.length} pokrytych · ${missing.length} braków${unresolved.length > 0 ? ` · ${unresolved.length} niezweryfikowanych` : ""}`}
        >
          <div className="resume-report-requirements">
            <section className="detail-section compact-detail-section">
              <h6>Pokryte wymagania</h6>
              {covered.length > 0 ? (
                <div className="requirement-match-list compact-requirement-match-list">
                  {covered.map((item) => (
                    <RequirementMatchDisclosure key={item.requirement_id} item={item} />
                  ))}
                </div>
              ) : (
                <p className="placeholder">Brak pokrytych wymagań do pokazania.</p>
              )}
            </section>

            <section className="detail-section compact-detail-section">
              <h6>Brakujące wymagania</h6>
              {missing.length > 0 ? (
                <div className="requirement-match-list compact-requirement-match-list">
                  {missing.map((item) => (
                    <RequirementMatchDisclosure key={item.requirement_id} item={item} />
                  ))}
                </div>
              ) : (
                <p className="placeholder">Brak całkowicie brakujących wymagań.</p>
              )}
            </section>

            {unresolved.length > 0 ? (
              <section className="detail-section compact-detail-section">
                <h6>Wymagania nie do weryfikacji</h6>
                <div className="requirement-match-list compact-requirement-match-list">
                  {unresolved.map((item) => (
                    <RequirementMatchDisclosure key={item.requirement_id} item={item} />
                  ))}
                </div>
              </section>
            ) : null}
          </div>
        </ExpandableReportSection>

        <ExpandableReportSection title="Pokaż słowa kluczowe" meta={`${detectedKeywords.length} wykrytych`}>
          <div className="result-columns">
            <section className="detail-section compact-detail-section">
              <h6>Słowa kluczowe oferty</h6>
              {detectedKeywords.length > 0 ? (
                <div className="chip-row">
                  {detectedKeywords.map((keyword) => (
                    <span key={keyword} className="chip muted">
                      {keyword}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="placeholder">Brak słów kluczowych wykrytych w ofercie.</p>
              )}
            </section>

            <section className="detail-section compact-detail-section">
              <h6>Słowa kluczowe użyte w drafcie</h6>
              {usedKeywords.length > 0 ? (
                <div className="chip-row">
                  {usedKeywords.map((keyword) => (
                    <span key={keyword} className="chip accent">
                      {keyword}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="placeholder">Brak słów kluczowych użytych w drafcie.</p>
              )}
            </section>
          </div>

          <section className="detail-section compact-detail-section">
            <h6>Niewykorzystane słowa kluczowe</h6>
            {unusedKeywords.length > 0 ? (
              <div className="chip-row">
                {unusedKeywords.map((keyword) => (
                  <span key={keyword} className="chip missing-chip">
                    {keyword}
                  </span>
                ))}
              </div>
            ) : (
              <p className="placeholder">Wszystkie wykryte słowa kluczowe zostały wykorzystane.</p>
            )}
          </section>
        </ExpandableReportSection>

        <ExpandableReportSection
          title="Pokaż zabezpieczenia truthful-first"
          meta={`${blockedItems.length + warnings.length} pozycji`}
        >
          <div className="result-columns">
            <section className="detail-section compact-detail-section">
              <h6>Zabezpieczenia truthful-first</h6>
              {renderStringList(blockedItems, "Brak zarejestrowanych zabezpieczeń do pokazania.")}
            </section>

            <section className="detail-section compact-detail-section">
              <h6>Uwagi do przeglądu</h6>
              {renderStringList(warnings, "Brak dodatkowych ostrzeżeń dla tego draftu.")}
            </section>
          </div>
        </ExpandableReportSection>
      </div>

      <RawJsonPanel summary="Szczegóły techniczne raportu zmian" value={changeReport} />
    </div>
  );
}
