/**
 * Resume-generation tab for selecting saved records, preparing fit data and generating CV drafts.
 */

import { useEffect, useState } from "react";

import {
  analyzeMatch,
  generateResumeDraft,
  getCandidateProfileDetail,
  getJobPostingDetail,
  getMatchResultDetail,
  listCandidateProfiles,
  listJobPostings,
  listMatchResults,
  saveMatchResult,
} from "./api";
import ChangeReportDetails from "./ChangeReportDetails";
import ResumeDraftDetails from "./ResumeDraftDetails";

/**
 * Convert an unknown error into a short user-facing message.
 *
 * @param {unknown} error Error-like value thrown by fetch helpers.
 * @returns {string} Readable message safe to show in the UI.
 */
function getErrorMessage(error) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Wystapil nieoczekiwany blad.";
}

/**
 * Convert a select value into an integer ID or null.
 *
 * @param {string} value Select value taken from the DOM.
 * @returns {number | null} Parsed integer ID or null when no record is selected.
 */
function parseSelectedId(value) {
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

/**
 * Format an ISO datetime into a compact local timestamp for metadata cards.
 *
 * @param {string} savedAt ISO datetime string returned by the backend.
 * @returns {string} Formatted local timestamp or the raw value when parsing fails.
 */
function formatSavedAt(savedAt) {
  const parsedDate = new Date(savedAt);
  if (Number.isNaN(parsedDate.getTime())) {
    return savedAt;
  }
  return parsedDate.toLocaleString("pl-PL");
}

/**
 * Describe which saved or inline fit result will be used to build the draft.
 *
 * @param {{type?: string, id?: number | null, savedAt?: string | null} | null} matchSource Fit source metadata.
 * @returns {string} Readable label shown in the config card.
 */
function describeMatchSource(matchSource) {
  if (matchSource?.type === "snapshot") {
    return `Uzywane jest swieze dopasowanie robocze zapisane jako snapshot #${matchSource.id}.`;
  }
  if (matchSource?.type === "session_unsaved") {
    return "Uzywane jest swieze dopasowanie robocze z tej sesji, ale snapshot historii nie zostal zapisany.";
  }
  return "Brak aktywnego dopasowania roboczego dla tej pary. Przygotuj nowe dopasowanie albo wygeneruj CV.";
}

/**
 * Build CSS modifier for fit classification and recommendation badges.
 *
 * @param {string | undefined} value Current badge value.
 * @returns {string} CSS class suffix used by the shared badge styles.
 */
function getBadgeTone(value) {
  if (value === "high" || value === "generate") {
    return "success";
  }
  if (value === "medium" || value === "generate_with_caution") {
    return "warning";
  }
  return "danger";
}

/**
 * Build the empty active match session state used by the resume flow.
 *
 * @returns {{matchResult: object | null, profileId: number | null, jobId: number | null, source: {type: string, id?: number | null, savedAt?: string | null}}}
 * Fresh empty session state.
 */
function createEmptyActiveMatchSession() {
  return {
    matchResult: null,
    profileId: null,
    jobId: null,
    source: { type: "none" },
  };
}

/**
 * Check whether the current active match session belongs to the selected pair.
 *
 * @param {{matchResult: object | null, profileId: number | null, jobId: number | null}} activeMatchSession Active working match session.
 * @param {number | null} profileId Currently selected profile ID.
 * @param {number | null} jobId Currently selected job ID.
 * @returns {boolean} True when the active match can be safely reused.
 */
function isActiveMatchForSelection(activeMatchSession, profileId, jobId) {
  return (
    Boolean(activeMatchSession.matchResult) &&
    activeMatchSession.profileId === profileId &&
    activeMatchSession.jobId === jobId
  );
}

/**
 * Count requirement-match statuses inside one MatchResult payload.
 *
 * @param {object | null} matchResult MatchResult payload.
 * @returns {{matched: number, partial: number, missing: number, notVerifiable: number}} Compact status counters.
 */
function summarizeRequirementStatuses(matchResult) {
  const requirementMatches = Array.isArray(matchResult?.requirement_matches) ? matchResult.requirement_matches : [];
  return requirementMatches.reduce(
    (summary, item) => {
      if (item.match_status === "matched") {
        summary.matched += 1;
      } else if (item.match_status === "partial") {
        summary.partial += 1;
      } else if (item.match_status === "missing") {
        summary.missing += 1;
      } else if (item.match_status === "not_verifiable") {
        summary.notVerifiable += 1;
      }
      return summary;
    },
    { matched: 0, partial: 0, missing: 0, notVerifiable: 0 },
  );
}

/**
 * Return a short preview list limited to the first few non-empty strings.
 *
 * @param {string[] | null | undefined} values List values to preview.
 * @param {number} [limit=3] Maximum number of preview items.
 * @returns {string[]} Short preview list.
 */
function buildPreviewList(values, limit = 3) {
  return Array.isArray(values)
    ? values.filter((value) => typeof value === "string" && value.trim()).slice(0, limit)
    : [];
}

/**
 * Render the tab used for generating a structured CV draft from saved inputs.
 *
 * @returns {JSX.Element} Resume-generation tab content.
 */
export default function ResumeTab({ jobListRefreshVersion = 0 }) {
  const [profiles, setProfiles] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState(null);

  const [selectedProfileId, setSelectedProfileId] = useState(null);
  const [selectedProfileDetail, setSelectedProfileDetail] = useState(null);
  const [selectedProfileLoading, setSelectedProfileLoading] = useState(false);

  const [selectedJobId, setSelectedJobId] = useState(null);
  const [selectedJobDetail, setSelectedJobDetail] = useState(null);
  const [selectedJobLoading, setSelectedJobLoading] = useState(false);

  const [matchLoading, setMatchLoading] = useState(false);
  const [matchLookupError, setMatchLookupError] = useState(null);
  const [activeMatchSession, setActiveMatchSession] = useState(createEmptyActiveMatchSession);
  const [matchHistory, setMatchHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);
  const [historyPreviewId, setHistoryPreviewId] = useState(null);
  const [historyPreviewCache, setHistoryPreviewCache] = useState({});
  const [historyPreviewLoadingId, setHistoryPreviewLoadingId] = useState(null);
  const [historyPreviewError, setHistoryPreviewError] = useState(null);

  const [generateLoading, setGenerateLoading] = useState(false);
  const [resumeArtifacts, setResumeArtifacts] = useState(null);
  const [message, setMessage] = useState(null);

  /**
   * Reset the generated draft state when the selection or fit context changes.
   *
   * @returns {void} No return value.
   */
  function resetGeneratedDraft() {
    setResumeArtifacts(null);
  }

  /**
   * Clear the currently active fit state.
   *
   * @returns {void} No return value.
   */
  function clearMatchState() {
    setActiveMatchSession(createEmptyActiveMatchSession());
    setMatchLookupError(null);
  }

  /**
   * Clear the currently loaded archival history state.
   *
   * @returns {void} No return value.
   */
  function clearHistoryState() {
    setMatchHistory([]);
    setHistoryError(null);
    setHistoryPreviewId(null);
    setHistoryPreviewCache({});
    setHistoryPreviewError(null);
    setHistoryPreviewLoadingId(null);
  }

  /**
   * Refresh the stored profile and job lists used by the resume selectors.
   *
   * @returns {Promise<void>} Promise resolved after selector data is refreshed.
   */
  async function refreshSelectorData() {
    setLookupLoading(true);
    setLookupError(null);

    try {
      const [profileItems, jobItems] = await Promise.all([listCandidateProfiles(), listJobPostings()]);
      setProfiles(profileItems);
      setJobs(jobItems);

      if (selectedProfileId && !profileItems.some((profile) => profile.id === selectedProfileId)) {
        setSelectedProfileId(null);
        setSelectedProfileDetail(null);
      }
      if (selectedJobId && !jobItems.some((job) => job.id === selectedJobId)) {
        setSelectedJobId(null);
        setSelectedJobDetail(null);
      }

      if (
        selectedProfileId &&
        selectedJobId &&
        profileItems.some((profile) => profile.id === selectedProfileId) &&
        jobItems.some((job) => job.id === selectedJobId)
      ) {
        await refreshMatchHistory(selectedProfileId, selectedJobId);
      }
    } catch (error) {
      setLookupError(getErrorMessage(error));
    } finally {
      setLookupLoading(false);
    }
  }

  useEffect(() => {
    void refreshSelectorData();
  }, []);

  useEffect(() => {
    if (jobListRefreshVersion === 0) {
      return;
    }
    void refreshSelectorData();
  }, [jobListRefreshVersion]);

  useEffect(() => {
    if (selectedProfileId && selectedJobId) {
      clearMatchState();
      resetGeneratedDraft();
      void refreshMatchHistory(selectedProfileId, selectedJobId);
      return;
    }

    clearMatchState();
    clearHistoryState();
    resetGeneratedDraft();
  }, [selectedProfileId, selectedJobId]);

  /**
   * Load one stored candidate profile selected in the resume form.
   *
   * @param {number | null} profileId Database identifier of the stored candidate profile.
   * @returns {Promise<void>} Promise resolved after the selected profile state is updated.
   */
  async function loadSelectedProfile(profileId) {
    setSelectedProfileId(profileId);
    setSelectedProfileDetail(null);
    resetGeneratedDraft();
    setMessage(null);

    if (!profileId) {
      return;
    }

    setSelectedProfileLoading(true);
    try {
      const payload = await getCandidateProfileDetail(profileId);
      setSelectedProfileDetail(payload);
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setSelectedProfileLoading(false);
    }
  }

  /**
   * Load one stored job posting selected in the resume form.
   *
   * @param {number | null} jobId Database identifier of the stored job posting.
   * @returns {Promise<void>} Promise resolved after the selected job state is updated.
   */
  async function loadSelectedJob(jobId) {
    setSelectedJobId(jobId);
    setSelectedJobDetail(null);
    resetGeneratedDraft();
    setMessage(null);

    if (!jobId) {
      return;
    }

    setSelectedJobLoading(true);
    try {
      const payload = await getJobPostingDetail(jobId);
      setSelectedJobDetail(payload);
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setSelectedJobLoading(false);
    }
  }

  /**
   * Load archival match snapshots for the selected profile and offer pair.
   *
   * @param {number} profileId Selected candidate profile ID.
   * @param {number} jobId Selected job posting ID.
   * @returns {Promise<void>} Promise resolved after the history state is updated.
   */
  async function refreshMatchHistory(profileId, jobId) {
    if (!profileId || !jobId) {
      clearHistoryState();
      return;
    }

    setHistoryLoading(true);
    setHistoryError(null);

    try {
      const matchItems = await listMatchResults(100);
      const filteredItems = matchItems.filter(
        (item) => item.candidate_profile_id === profileId && item.job_posting_id === jobId,
      );
      setMatchHistory(filteredItems);
    } catch (error) {
      setHistoryError(getErrorMessage(error));
    } finally {
      setHistoryLoading(false);
    }
  }

  /**
   * Fetch one stored match snapshot on demand for archival preview.
   *
   * @param {number} matchResultId Snapshot ID to preview.
   * @returns {Promise<void>} Promise resolved after preview state is updated.
   */
  async function handleHistoryPreviewToggle(matchResultId) {
    if (historyPreviewId === matchResultId) {
      setHistoryPreviewId(null);
      setHistoryPreviewError(null);
      return;
    }

    setHistoryPreviewError(null);

    if (historyPreviewCache[matchResultId]) {
      setHistoryPreviewId(matchResultId);
      return;
    }

    setHistoryPreviewLoadingId(matchResultId);
    try {
      const payload = await getMatchResultDetail(matchResultId);
      setHistoryPreviewCache((currentCache) => ({
        ...currentCache,
        [matchResultId]: payload,
      }));
      setHistoryPreviewId(matchResultId);
    } catch (error) {
      setHistoryPreviewError(getErrorMessage(error));
    } finally {
      setHistoryPreviewLoadingId(null);
    }
  }

  /**
   * Run a fresh fit analysis, set it as the active working result and save a history snapshot.
   *
   * @returns {Promise<{matchResult: object, snapshotSaved: boolean}>} Fresh working result and snapshot status.
   */
  async function runFreshMatchSnapshot() {
    if (!selectedProfileDetail?.payload || !selectedJobDetail?.payload) {
      throw new Error("Najpierw wybierz zapisany profil i oferte.");
    }

    const profileId = selectedProfileId;
    const jobId = selectedJobId;

    setMatchLoading(true);
    setMatchLookupError(null);

    try {
      const matchResult = await analyzeMatch(selectedProfileDetail.payload, selectedJobDetail.payload);
      let nextSource = { type: "session_unsaved" };
      setActiveMatchSession({
        matchResult,
        profileId,
        jobId,
        source: nextSource,
      });
      let snapshotSaved = false;

      try {
        const savedSnapshot = await saveMatchResult(matchResult, profileId, jobId);
        nextSource = {
          type: "snapshot",
          id: savedSnapshot.id,
          savedAt: savedSnapshot.saved_at,
        };
        setActiveMatchSession({
          matchResult,
          profileId,
          jobId,
          source: nextSource,
        });
        snapshotSaved = true;
      } catch (error) {
        setMatchLookupError(
          `Dopasowanie zostalo przeliczone, ale snapshot historii nie zostal zapisany: ${getErrorMessage(error)}`,
        );
      }

      await refreshMatchHistory(profileId, jobId);
      return { matchResult, snapshotSaved, source: nextSource };
    } finally {
      setMatchLoading(false);
    }
  }

  /**
   * Prepare fresh fit analysis explicitly for the current selection.
   *
   * @returns {Promise<void>} Promise resolved after the inline fit analysis finishes.
   */
  async function handleAnalyzeClick() {
    setMessage(null);
    resetGeneratedDraft();

    try {
      const { snapshotSaved } = await runFreshMatchSnapshot();
      setMessage({
        type: "success",
        text: snapshotSaved
          ? "Dopasowanie zostalo przeliczone od nowa i zapisane jako snapshot historii."
          : "Dopasowanie zostalo przeliczone od nowa, ale snapshot historii nie zostal zapisany.",
      });
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    }
  }

  /**
   * Generate a ResumeDraft using the active or freshly calculated MatchResult.
   *
   * @returns {Promise<void>} Promise resolved after resume generation finishes.
   */
  async function handleGenerateClick() {
    if (!selectedProfileDetail?.payload || !selectedJobDetail?.payload) {
      return;
    }

    setGenerateLoading(true);
    setMessage(null);
    resetGeneratedDraft();

    try {
      const matchResult = isActiveMatchForSelection(activeMatchSession, selectedProfileId, selectedJobId)
        ? activeMatchSession.matchResult
        : (await runFreshMatchSnapshot()).matchResult;
      const payload = await generateResumeDraft(
        selectedProfileDetail.payload,
        selectedJobDetail.payload,
        matchResult,
      );
      setResumeArtifacts(payload);
      setMessage({ type: "success", text: "Draft CV zostal wygenerowany." });
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setGenerateLoading(false);
    }
  }

  const canGenerate =
    Boolean(selectedProfileDetail?.payload) &&
    Boolean(selectedJobDetail?.payload) &&
    !selectedProfileLoading &&
    !selectedJobLoading;
  const activeMatchResult = activeMatchSession.matchResult;
  const matchSource = activeMatchSession.source;
  const selectedHistoryPreview = historyPreviewId ? historyPreviewCache[historyPreviewId] ?? null : null;
  const selectedHistoryPreviewMatchResult = selectedHistoryPreview?.payload ?? null;
  const selectedHistoryPreviewStats = summarizeRequirementStatuses(selectedHistoryPreviewMatchResult);
  const selectedHistoryStrengthsPreview = buildPreviewList(selectedHistoryPreviewMatchResult?.strengths);
  const selectedHistoryGapsPreview = buildPreviewList(selectedHistoryPreviewMatchResult?.gaps);

  return (
    <section className="tab-content">
      <div className="section-header tab-header">
        <div>
          <h2>CV i list motywacyjny</h2>
          <p className="section-copy">
            Przygotuj dopasowanie dla wybranego profilu i oferty, a nastepnie wygeneruj CV.
          </p>
        </div>
      </div>

      {message ? <div className={`message ${message.type}`}>{message.text}</div> : null}
      {lookupError ? <div className="message error">{lookupError}</div> : null}
      {matchLookupError ? <div className="message error">{matchLookupError}</div> : null}

      <section className="section-card section-wide">
        <div className="section-header section-header-inline">
          <div>
            <h3>Konfiguracja generowania</h3>
            <p className="section-copy">
              Przygotuj dopasowanie dla wybranego profilu i oferty, a nastepnie wygeneruj CV.
            </p>
          </div>
          <button
            type="button"
            className="ghost-button"
            onClick={() => void refreshSelectorData()}
            disabled={lookupLoading || matchLoading || generateLoading}
          >
            {lookupLoading ? "Odswiezanie..." : "Odswiez listy"}
          </button>
        </div>

        <div className="resume-config-stack">
          <div className="form-grid resume-form-grid">
            <label className="field">
              <span>Zapisany profil</span>
              <select
                className="select-input"
                value={selectedProfileId ?? ""}
                onChange={(event) => void loadSelectedProfile(parseSelectedId(event.target.value))}
                disabled={lookupLoading || matchLoading || generateLoading}
              >
                <option value="">Wybierz profil</option>
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.full_name} ({profile.email})
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Zapisana oferta</span>
              <select
                className="select-input"
                value={selectedJobId ?? ""}
                onChange={(event) => void loadSelectedJob(parseSelectedId(event.target.value))}
                disabled={lookupLoading || matchLoading || generateLoading}
              >
                <option value="">Wybierz oferte</option>
                {jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.title} - {job.company_name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="resume-actions" role="group" aria-label="Akcje generowania CV">
            <button
              type="button"
              className="ghost-button resume-secondary-action"
              onClick={handleAnalyzeClick}
              disabled={!canGenerate || matchLoading || generateLoading}
            >
              {matchLoading ? "Przygotowywanie..." : "Przygotuj dopasowanie do CV"}
            </button>
            <button
              type="button"
              className="primary-button resume-primary-action"
              onClick={handleGenerateClick}
              disabled={!canGenerate || matchLoading || generateLoading}
            >
              {generateLoading ? "Generowanie..." : "Generuj CV"}
            </button>
          </div>
        </div>

        <div className="selection-grid resume-config-grid">
          <article className="selection-card">
            <h4>Wybrany profil</h4>
            {selectedProfileLoading ? (
              <p className="placeholder">Ladowanie profilu...</p>
            ) : selectedProfileDetail?.payload ? (
              <>
                <strong className="selection-card-title">{selectedProfileDetail.payload.personal_info.full_name}</strong>
                <p className="detail-text">{selectedProfileDetail.payload.personal_info.email}</p>
                <p className="detail-text">{selectedProfileDetail.payload.personal_info.location}</p>
                <p className="helper-text">
                  ID: {selectedProfileDetail.id} · Zapisano: {formatSavedAt(selectedProfileDetail.saved_at)}
                </p>
              </>
            ) : (
              <p className="placeholder">Wybierz zapisany profil.</p>
            )}
          </article>

          <article className="selection-card">
            <h4>Wybrana oferta</h4>
            {selectedJobLoading ? (
              <p className="placeholder">Ladowanie oferty...</p>
            ) : selectedJobDetail?.payload ? (
              <>
                <strong className="selection-card-title">{selectedJobDetail.payload.title}</strong>
                <p className="detail-text">{selectedJobDetail.payload.company_name}</p>
                <p className="detail-text">{selectedJobDetail.payload.location}</p>
                <p className="helper-text">
                  ID: {selectedJobDetail.id} · Zapisano: {formatSavedAt(selectedJobDetail.saved_at)}
                </p>
              </>
            ) : (
              <p className="placeholder">Wybierz zapisana oferte.</p>
            )}
          </article>

          <article className="selection-card">
            <h4>Dopasowanie uzyte do CV</h4>
            {matchLoading ? (
              <p className="placeholder">Ladowanie dopasowania...</p>
            ) : (
              <>
                <p className="detail-text">{describeMatchSource(matchSource)}</p>
                {matchSource?.type === "snapshot" && matchSource?.savedAt ? (
                  <p className="helper-text">Zapisano: {formatSavedAt(matchSource.savedAt)}</p>
                ) : null}

                {activeMatchResult ? (
                  <div className="match-source-status-grid">
                    <div className="result-metric-card compact-metric-card">
                      <span className="metric-label">Ocena dopasowania</span>
                      <strong className="metric-value">{Math.round(activeMatchResult.overall_score * 100)}%</strong>
                    </div>
                    <div className="result-metric-card compact-metric-card">
                      <span className="metric-label">Klasyfikacja</span>
                      <span className={`status-badge ${getBadgeTone(activeMatchResult.fit_classification)}`}>
                        {activeMatchResult.fit_classification}
                      </span>
                    </div>
                    <div className="result-metric-card compact-metric-card">
                      <span className="metric-label">Rekomendacja</span>
                      <span className={`status-badge ${getBadgeTone(activeMatchResult.recommendation)}`}>
                        {activeMatchResult.recommendation}
                      </span>
                    </div>
                  </div>
                ) : (
                  <p className="helper-text">Historia jest archiwalna. Aktywny wynik roboczy powstaje dopiero po swiezym przeliczeniu.</p>
                )}
              </>
            )}
          </article>
        </div>

        <div className="section-header" style={{ marginTop: "20px" }}>
          <div>
            <h3>Historia snapshotow dopasowania</h3>
            <p className="section-copy">
              Archiwalne wyniki dla tej pary profilu i oferty. Nie ustawiaja automatycznie aktywnego dopasowania roboczego.
            </p>
          </div>
        </div>

        {historyError ? <div className="message error">{historyError}</div> : null}

        {historyLoading ? (
          <p className="placeholder">Ladowanie historii dopasowan...</p>
        ) : !selectedProfileId || !selectedJobId ? (
          <p className="placeholder">Wybierz profil i oferte, aby zobaczyc snapshoty historii.</p>
        ) : matchHistory.length > 0 ? (
          <div className="history-list-wrapper">
            <div className="history-list">
              {matchHistory.map((item) => (
                <div
                  key={item.id}
                  className={`history-item${matchSource?.type === "snapshot" && matchSource?.id === item.id ? " active" : ""}`}
                >
                  <div>
                    <span className="history-title">Snapshot #{item.id}</span>
                    <span className="history-company">
                      {Math.round(item.overall_score * 100)}% · {item.fit_classification}
                    </span>
                    <span className="history-meta">Rekomendacja: {item.recommendation}</span>
                    <span className="history-meta history-meta-secondary">
                      Zapisano: {formatSavedAt(item.saved_at)}
                    </span>
                  </div>
                  <div className="history-item-actions">
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() => void handleHistoryPreviewToggle(item.id)}
                      disabled={historyPreviewLoadingId === item.id}
                    >
                      {historyPreviewLoadingId === item.id
                        ? "Ladowanie..."
                        : historyPreviewId === item.id
                          ? "Ukryj szczegoly"
                          : "Podglad"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="placeholder">Brak zapisanych snapshotow dla tej pary.</p>
        )}

        {historyPreviewError ? <div className="message error">{historyPreviewError}</div> : null}

        {selectedHistoryPreviewMatchResult ? (
          <section className="detail-section">
            <div className="section-header section-header-inline">
              <div>
                <h4>Szczegoly snapshotu #{selectedHistoryPreview.id}</h4>
                <p className="section-copy">
                  Archiwalny podglad porownawczy dla wybranego snapshotu historii.
                </p>
              </div>
              <button
                type="button"
                className="ghost-button"
                onClick={() => setHistoryPreviewId(null)}
              >
                Zamknij podglad
              </button>
            </div>

            <div className="result-summary-grid resume-report-summary-grid">
              <div className="result-metric-card">
                <span className="metric-label">Ocena dopasowania</span>
                <strong className="metric-value">
                  {Math.round(selectedHistoryPreviewMatchResult.overall_score * 100)}%
                </strong>
              </div>
              <div className="result-metric-card">
                <span className="metric-label">Klasyfikacja</span>
                <span className={`status-badge ${getBadgeTone(selectedHistoryPreviewMatchResult.fit_classification)}`}>
                  {selectedHistoryPreviewMatchResult.fit_classification}
                </span>
              </div>
              <div className="result-metric-card">
                <span className="metric-label">Rekomendacja</span>
                <span className={`status-badge ${getBadgeTone(selectedHistoryPreviewMatchResult.recommendation)}`}>
                  {selectedHistoryPreviewMatchResult.recommendation}
                </span>
              </div>
              <div className="result-metric-card">
                <span className="metric-label">Zapisano</span>
                <strong className="metric-value compact-metric-value">
                  {formatSavedAt(selectedHistoryPreview.saved_at)}
                </strong>
              </div>
            </div>

            <div className="match-source-status-grid">
              <div className="result-metric-card compact-metric-card">
                <span className="metric-label">Matched</span>
                <strong className="metric-value">{selectedHistoryPreviewStats.matched}</strong>
              </div>
              <div className="result-metric-card compact-metric-card">
                <span className="metric-label">Partial</span>
                <strong className="metric-value">{selectedHistoryPreviewStats.partial}</strong>
              </div>
              <div className="result-metric-card compact-metric-card">
                <span className="metric-label">Missing</span>
                <strong className="metric-value">{selectedHistoryPreviewStats.missing}</strong>
              </div>
              <div className="result-metric-card compact-metric-card">
                <span className="metric-label">Not verifiable</span>
                <strong className="metric-value">{selectedHistoryPreviewStats.notVerifiable}</strong>
              </div>
            </div>

            <p className="detail-text">
              {selectedHistoryPreviewMatchResult.final_summary || "Brak podsumowania dla tego snapshotu."}
            </p>

            <div className="result-columns">
              <section className="detail-section">
                <h5>Preview strengths</h5>
                {selectedHistoryStrengthsPreview.length > 0 ? (
                  <ul className="detail-list">
                    {selectedHistoryStrengthsPreview.map((item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="placeholder">Brak mocnych stron do podgladu.</p>
                )}
              </section>

              <section className="detail-section">
                <h5>Preview gaps</h5>
                {selectedHistoryGapsPreview.length > 0 ? (
                  <ul className="detail-list">
                    {selectedHistoryGapsPreview.map((item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="placeholder">Brak luk do podgladu.</p>
                )}
              </section>
            </div>
          </section>
        ) : null}

        <div className="resume-info-note" role="note" aria-label="Informacja o liscie motywacyjnym">
          Na tym etapie dostepne jest generowanie CV. List motywacyjny zostanie dodany pozniej.
        </div>
      </section>

      <div className="document-results-grid">
        <section className="section-card scroll-panel">
          <div className="section-header">
            <div>
              <h3>Podglad CV</h3>
              <p className="section-copy">Czytelny podglad wygenerowanego draftu CV.</p>
            </div>
          </div>

          <div className="scroll-panel-body document-panel-body">
            {resumeArtifacts?.resume_draft ? (
              <ResumeDraftDetails resumeDraft={resumeArtifacts.resume_draft} />
            ) : (
              <p className="placeholder">
                Wybierz zapisany profil i oferte, a potem wygeneruj draft CV dla tej pary.
              </p>
            )}
          </div>
        </section>

        <section className="section-card scroll-panel">
          <div className="section-header">
            <div>
              <h3>Raport zmian</h3>
              <p className="section-copy">Wyjasnienie, co zostalo uzyte, pominiete i czego nie dodano.</p>
            </div>
          </div>

          <div className="scroll-panel-body document-panel-body">
            {resumeArtifacts?.change_report ? (
              <ChangeReportDetails
                changeReport={resumeArtifacts.change_report}
                matchResult={activeMatchResult}
                matchSource={matchSource}
                generationMode={resumeArtifacts.generation_mode}
                fallbackReason={resumeArtifacts.fallback_reason}
                generationNotes={resumeArtifacts.generation_notes}
              />
            ) : (
              <p className="placeholder">
                Po wygenerowaniu draftu tutaj pojawi sie raport zmian i pokrycia wymaganych.
              </p>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
