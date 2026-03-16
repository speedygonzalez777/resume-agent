/**
 * Matching tab for selecting stored profile and job records, running analysis and saving results.
 */

import { useEffect, useState } from "react";

import {
  analyzeMatch,
  getCandidateProfileDetail,
  getJobPostingDetail,
  listCandidateProfiles,
  listJobPostings,
  saveMatchResult,
} from "./api";
import MatchResultDetails from "./MatchResultDetails";

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
 * Render the matching tab used for analyzing fit between one profile and one offer.
 *
 * @returns {JSX.Element} Matching tab content.
 */
export default function MatchingTab() {
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

  const [matchResult, setMatchResult] = useState(null);
  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [message, setMessage] = useState(null);

  /**
   * Refresh the stored profile and job lists used by the matching selectors.
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
    } catch (error) {
      setLookupError(getErrorMessage(error));
    } finally {
      setLookupLoading(false);
    }
  }

  useEffect(() => {
    void refreshSelectorData();
  }, []);

  /**
   * Load one stored candidate profile selected in the matching form.
   *
   * @param {number | null} profileId Database identifier of the stored candidate profile.
   * @returns {Promise<void>} Promise resolved after the selected profile state is updated.
   */
  async function loadSelectedProfile(profileId) {
    setSelectedProfileId(profileId);
    setSelectedProfileDetail(null);

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
   * Load one stored job posting selected in the matching form.
   *
   * @param {number | null} jobId Database identifier of the stored job posting.
   * @returns {Promise<void>} Promise resolved after the selected job state is updated.
   */
  async function loadSelectedJob(jobId) {
    setSelectedJobId(jobId);
    setSelectedJobDetail(null);

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
   * Run match analysis for the currently selected profile and offer.
   *
   * @returns {Promise<void>} Promise resolved after the MatchResult state is updated.
   */
  async function handleAnalyzeClick() {
    if (!selectedProfileDetail?.payload || !selectedJobDetail?.payload) {
      return;
    }

    setAnalyzeLoading(true);
    setMessage(null);
    setMatchResult(null);

    try {
      const payload = await analyzeMatch(selectedProfileDetail.payload, selectedJobDetail.payload);
      setMatchResult(payload);
      setMessage({ type: "success", text: "Matching zostal policzony." });
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setAnalyzeLoading(false);
    }
  }

  /**
   * Save the currently visible MatchResult together with selected record links.
   *
   * @returns {Promise<void>} Promise resolved after the save call finishes.
   */
  async function handleSaveMatchClick() {
    if (!matchResult) {
      return;
    }

    setSaveLoading(true);
    setMessage(null);

    try {
      const payload = await saveMatchResult(matchResult, selectedProfileId, selectedJobId);
      setMessage({
        type: "success",
        text: `Wynik matchingu zostal zapisany z ID ${payload.id}.`,
      });
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setSaveLoading(false);
    }
  }

  return (
    <section className="tab-content">
      <div className="section-header tab-header">
        <div>
          <h2>Matching</h2>
          <p className="section-copy">
            Porownaj wybrana oferte z zapisanym profilem kandydata.
          </p>
        </div>
      </div>

      {message ? <div className={`message ${message.type}`}>{message.text}</div> : null}
      {lookupError ? <div className="message error">{lookupError}</div> : null}

      <div className="workspace-grid">
        <section className="section-card section-wide">
          <div className="section-header">
            <div>
              <h3>Konfiguracja matchingu</h3>
              <p className="section-copy">Wybierz profil i oferte, uruchom analize i zapisz wynik.</p>
            </div>
          </div>

          <div className="form-grid">
            <label className="field">
              <span>Zapisany profil</span>
              <select
                className="select-input"
                value={selectedProfileId ?? ""}
                onChange={(event) => void loadSelectedProfile(parseSelectedId(event.target.value))}
                disabled={lookupLoading || analyzeLoading || saveLoading}
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
                disabled={lookupLoading || analyzeLoading || saveLoading}
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

          <div className="actions">
            <button
              type="button"
              onClick={handleAnalyzeClick}
              disabled={
                analyzeLoading ||
                saveLoading ||
                !selectedProfileDetail?.payload ||
                !selectedJobDetail?.payload ||
                selectedProfileLoading ||
                selectedJobLoading
              }
            >
              {analyzeLoading ? "Analiza..." : "Uruchom matching"}
            </button>
            <button type="button" onClick={handleSaveMatchClick} disabled={saveLoading || !matchResult}>
              {saveLoading ? "Zapisywanie..." : "Zapisz wynik"}
            </button>
          </div>
        </section>

        <section className="section-card">
          <div className="section-header">
            <div>
              <h3>Wybrane rekordy</h3>
              <p className="section-copy">Podsumowanie danych, ktore wejda do analizy.</p>
            </div>
          </div>

          <div className="selection-grid">
            <article className="selection-card">
              <h4>Profil</h4>
              {selectedProfileLoading ? (
                <p className="placeholder">Ladowanie profilu...</p>
              ) : selectedProfileDetail?.payload ? (
                <>
                  <strong className="selection-card-title">{selectedProfileDetail.payload.personal_info.full_name}</strong>
                  <p className="detail-text">{selectedProfileDetail.payload.personal_info.email}</p>
                  <p className="detail-text">{selectedProfileDetail.payload.personal_info.location}</p>
                  <p className="helper-text">ID: {selectedProfileDetail.id} · Zapisano: {formatSavedAt(selectedProfileDetail.saved_at)}</p>
                </>
              ) : (
                <p className="placeholder">Wybierz zapisany profil.</p>
              )}
            </article>

            <article className="selection-card">
              <h4>Oferta</h4>
              {selectedJobLoading ? (
                <p className="placeholder">Ladowanie oferty...</p>
              ) : selectedJobDetail?.payload ? (
                <>
                  <strong className="selection-card-title">{selectedJobDetail.payload.title}</strong>
                  <p className="detail-text">{selectedJobDetail.payload.company_name}</p>
                  <p className="detail-text">{selectedJobDetail.payload.location}</p>
                  <p className="helper-text">ID: {selectedJobDetail.id} · Zapisano: {formatSavedAt(selectedJobDetail.saved_at)}</p>
                </>
              ) : (
                <p className="placeholder">Wybierz zapisana oferte.</p>
              )}
            </article>
          </div>
        </section>

        <section className="section-card scroll-panel section-wide">
          <div className="section-header">
            <div>
              <h3>Wynik matchingu</h3>
              <p className="section-copy">Wynik dopasowania w czytelnej formie.</p>
            </div>
          </div>

          <div className="scroll-panel-body match-results-panel-body">
            {matchResult ? (
              <MatchResultDetails matchResult={matchResult} />
            ) : (
              <p className="placeholder">Uruchom matching po wybraniu zapisanego profilu i oferty.</p>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}

