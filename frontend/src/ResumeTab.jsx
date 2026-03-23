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
  if (matchSource?.type === "saved") {
    return `Uzywane jest zapisane dopasowanie #${matchSource.id}.`;
  }
  if (matchSource?.type === "inline") {
    return "Uzywane jest dopasowanie przygotowane w tej sesji. Nie zostalo zapisane automatycznie.";
  }
  return "Brak zapisanego dopasowania dla tej pary. Mozesz przygotowac nowe dopasowanie.";
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
 * Render the tab used for generating a structured CV draft from saved inputs.
 *
 * @returns {JSX.Element} Resume-generation tab content.
 */
export default function ResumeTab() {
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
  const [activeMatchResult, setActiveMatchResult] = useState(null);
  const [matchSource, setMatchSource] = useState({ type: "none" });

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
    setActiveMatchResult(null);
    setMatchSource({ type: "none" });
    setMatchLookupError(null);
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
        await loadSavedMatchForSelection(selectedProfileId, selectedJobId);
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
    if (selectedProfileId && selectedJobId) {
      void loadSavedMatchForSelection(selectedProfileId, selectedJobId);
      return;
    }

    clearMatchState();
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
   * Load the newest saved fit result for the selected profile and offer pair.
   *
   * @param {number} profileId Selected candidate profile ID.
   * @param {number} jobId Selected job posting ID.
   * @returns {Promise<void>} Promise resolved after the fit state is updated.
   */
  async function loadSavedMatchForSelection(profileId, jobId) {
    setMatchLoading(true);
    setMatchLookupError(null);
    setActiveMatchResult(null);
    setMatchSource({ type: "none" });

    try {
      const matchItems = await listMatchResults();
      const latestSavedMatch = matchItems.find(
        (item) => item.candidate_profile_id === profileId && item.job_posting_id === jobId,
      );

      if (!latestSavedMatch) {
        return;
      }

      const payload = await getMatchResultDetail(latestSavedMatch.id);
      setActiveMatchResult(payload.payload);
      setMatchSource({
        type: "saved",
        id: payload.id,
        savedAt: payload.saved_at,
      });
    } catch (error) {
      setMatchLookupError(getErrorMessage(error));
    } finally {
      setMatchLoading(false);
    }
  }

  /**
   * Run inline fit analysis for the selected profile and offer without saving the result.
   *
   * @returns {Promise<object>} MatchResult payload returned by the backend.
   */
  async function runInlineMatch() {
    if (!selectedProfileDetail?.payload || !selectedJobDetail?.payload) {
      throw new Error("Najpierw wybierz zapisany profil i oferte.");
    }

    setMatchLoading(true);
    setMatchLookupError(null);

    try {
      const payload = await analyzeMatch(selectedProfileDetail.payload, selectedJobDetail.payload);
      setActiveMatchResult(payload);
      setMatchSource({ type: "inline" });
      return payload;
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
      await runInlineMatch();
      setMessage({
        type: "success",
        text: "Dopasowanie zostalo przygotowane dla tego CV. Wynik nie zostal zapisany automatycznie.",
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
      const matchResult = activeMatchResult ?? (await runInlineMatch());
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
                {matchSource?.type === "saved" && matchSource?.savedAt ? (
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
                  <p className="helper-text">Przy generowaniu mozna tez przygotowac dopasowanie bez zapisu.</p>
                )}
              </>
            )}
          </article>
        </div>

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
