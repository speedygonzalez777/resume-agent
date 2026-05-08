import RawJsonPanel from "../../RawJsonPanel";

/**
 * @param {{
 *   canGenerate: boolean,
 *   busy: boolean,
 *   onAnalyzeDebug: () => void,
 *   lastResumeMatchingHandoff: boolean | null,
 *   lastResumeRequestBodyUnavailableReason: string | null,
 *   matchingDebugEnvelope: object,
 *   resumeDebugEnvelope: object,
 * }} props
 * @returns {JSX.Element}
 */
export default function ResumeDebugPanel({
  canGenerate,
  busy,
  onAnalyzeDebug,
  lastResumeMatchingHandoff,
  lastResumeRequestBodyUnavailableReason,
  matchingDebugEnvelope,
  resumeDebugEnvelope,
}) {
  const hasTechnicalData = Boolean(
    matchingDebugEnvelope?.request_body ||
      matchingDebugEnvelope?.response_body ||
      resumeDebugEnvelope?.request_body ||
      resumeDebugEnvelope?.response_body,
  );

  return (
    <section className="document-work-card document-debug-card">
      <details className="document-advanced-details">
        <summary>
          <span>Szczegóły techniczne</span>
          <span className="document-debug-hint">Debug dopasowania, JSON i matching handoff</span>
        </summary>

        <div className="document-debug-stack">
          <div className="actions debug-action-row">
            <button
              type="button"
              className="ghost-button"
              onClick={onAnalyzeDebug}
              disabled={!canGenerate || busy}
            >
              {busy ? "Przygotowywanie..." : "Uruchom debug dopasowania"}
            </button>
          </div>

          <p className="helper-text">
            matching_handoff:{" "}
            {lastResumeMatchingHandoff === true
              ? "tak"
              : lastResumeMatchingHandoff === false
                ? "nie"
                : lastResumeRequestBodyUnavailableReason
                  ? "brak danych historycznych"
                  : "brak"}
          </p>

          {!hasTechnicalData ? (
            <p className="placeholder">
              Dane techniczne pojawią się po przeliczeniu dopasowania albo wygenerowaniu draftu.
            </p>
          ) : null}

          <RawJsonPanel summary="JSON dopasowania" value={matchingDebugEnvelope} />

          <RawJsonPanel
            summary="JSON draftu CV"
            value={resumeDebugEnvelope}
            helperText={lastResumeRequestBodyUnavailableReason}
          />
        </div>
      </details>
    </section>
  );
}
