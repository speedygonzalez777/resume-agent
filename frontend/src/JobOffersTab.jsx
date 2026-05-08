/**
 * Offer-management tab for parsing, saving and browsing stored job postings.
 */

import { useEffect, useState } from "react";

import {
  deleteJobPosting,
  getJobPostingDetail,
  listJobPostings,
  parseJobPosting,
  saveJobPosting,
} from "./api";
import JobPostingDetails from "./JobPostingDetails";
import RawJsonPanel from "./RawJsonPanel";

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
  return "Wystąpił nieoczekiwany błąd.";
}

/**
 * Format an ISO datetime into a compact local timestamp for list views.
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
 * Check whether a stored job matches the current frontend filter text.
 *
 * @param {object} job Stored job list item.
 * @param {string} normalizedFilter Lowercased filter text.
 * @returns {boolean} True when the job should remain visible.
 */
function matchesHistoryFilter(job, normalizedFilter) {
  if (!normalizedFilter) {
    return true;
  }

  const title = String(job.title ?? "").toLowerCase();
  const companyName = String(job.company_name ?? "").toLowerCase();
  return title.includes(normalizedFilter) || companyName.includes(normalizedFilter);
}

/**
 * Build short preview stats for the freshly parsed offer shown in the top panel.
 *
 * @param {object} jobPosting Parsed JobPosting payload returned by the backend.
 * @returns {Array<{label: string, value: string}>} Compact stats rendered above the raw JSON helper.
 */
function buildParsedPreviewStats(jobPosting) {
  const requirementsCount = Array.isArray(jobPosting?.requirements) ? jobPosting.requirements.length : 0;
  const responsibilitiesCount = Array.isArray(jobPosting?.responsibilities) ? jobPosting.responsibilities.length : 0;
  const keywordsCount = Array.isArray(jobPosting?.keywords) ? jobPosting.keywords.length : 0;

  return [
    { label: "Lokalizacja", value: jobPosting?.location || "brak" },
    { label: "Źródło", value: jobPosting?.source || "brak" },
    { label: "Wymagania", value: String(requirementsCount) },
    { label: "Obowiązki", value: String(responsibilitiesCount) },
    { label: "Słowa kluczowe", value: String(keywordsCount) },
  ];
}

/**
 * Render the job-offer tab used for parser and history workflows.
 *
 * @returns {JSX.Element} Offer-management tab content.
 */
export default function JobOffersTab({ onJobSaved }) {
  const [jobUrl, setJobUrl] = useState("");
  const [parsedJobPosting, setParsedJobPosting] = useState(null);
  const [parseLoading, setParseLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [message, setMessage] = useState(null);

  const [jobHistory, setJobHistory] = useState([]);
  const [historyFilter, setHistoryFilter] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);
  const [deletingJobId, setDeletingJobId] = useState(null);

  const [selectedJobId, setSelectedJobId] = useState(null);
  const [selectedJobDetail, setSelectedJobDetail] = useState(null);
  const [selectedJobLoading, setSelectedJobLoading] = useState(false);
  const [selectedJobError, setSelectedJobError] = useState(null);

  /**
   * Clear the currently selected stored job state.
   *
   * @returns {void} No return value.
   */
  function clearSelectedJob() {
    setSelectedJobId(null);
    setSelectedJobDetail(null);
    setSelectedJobError(null);
    setSelectedJobLoading(false);
  }

  /**
   * Refresh the stored job history from SQLite without loading full record payloads.
   *
   * @returns {Promise<object[] | null>} Loaded list items or null when the refresh fails.
   */
  async function refreshJobHistory() {
    setHistoryLoading(true);
    setHistoryError(null);

    try {
      const payload = await listJobPostings();
      setJobHistory(payload);

      if (selectedJobId && !payload.some((job) => job.id === selectedJobId)) {
        clearSelectedJob();
      }

      return payload;
    } catch (error) {
      setHistoryError(getErrorMessage(error));
      return null;
    } finally {
      setHistoryLoading(false);
    }
  }

  /**
   * Load the full detail of one stored job posting selected from history.
   *
   * @param {number} jobPostingId Database identifier of the stored offer.
   * @returns {Promise<void>} Promise resolved after the detail panel state is updated.
   */
  async function selectStoredJob(jobPostingId) {
    setSelectedJobId(jobPostingId);
    setSelectedJobDetail(null);
    setSelectedJobError(null);
    setSelectedJobLoading(true);

    try {
      const payload = await getJobPostingDetail(jobPostingId);
      setSelectedJobDetail(payload);
    } catch (error) {
      setSelectedJobError(getErrorMessage(error));
    } finally {
      setSelectedJobLoading(false);
    }
  }

  useEffect(() => {
    void refreshJobHistory();
  }, []);

  /**
   * Parse a job posting URL through the backend and show the returned JobPosting.
   *
   * @returns {Promise<void>} Promise resolved after parse state is updated.
   */
  async function handleParseClick() {
    setParseLoading(true);
    setMessage(null);
    setParsedJobPosting(null);

    try {
      const payload = await parseJobPosting(jobUrl.trim());
      setParsedJobPosting(payload);
      setMessage({ type: "success", text: "Oferta została wczytana." });
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setParseLoading(false);
    }
  }

  /**
   * Save the currently parsed JobPosting and refresh the local job history view.
   *
   * @returns {Promise<void>} Promise resolved after save-related state is updated.
   */
  async function handleSaveClick() {
    if (!parsedJobPosting) {
      return;
    }

    setSaveLoading(true);
    setMessage(null);

    try {
      const payload = await saveJobPosting(parsedJobPosting, jobUrl.trim());
      await refreshJobHistory();
      onJobSaved?.();

      if (payload?.id) {
        await selectStoredJob(payload.id);
        setMessage({
          type: "success",
          text: `Oferta została zapisana z ID ${payload.id} i ustawiona jako aktywna.`,
        });
      } else {
        setMessage({ type: "success", text: "Oferta została zapisana." });
      }
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setSaveLoading(false);
    }
  }

  /**
   * Delete one stored job posting from history after a simple confirmation.
   *
   * @param {number} jobPostingId Database identifier of the stored job posting.
   * @param {MouseEvent} event Click event used to stop row-selection propagation.
   * @returns {Promise<void>} Promise resolved after the history and selection state are updated.
   */
  async function handleDeleteJobClick(jobPostingId, event) {
    event.stopPropagation();

    const shouldDelete = window.confirm("Czy na pewno chcesz usunąć tę ofertę z historii?");
    if (!shouldDelete) {
      return;
    }

    const deletedWasSelected = selectedJobId === jobPostingId;
    setDeletingJobId(jobPostingId);
    setMessage(null);

    try {
      const payload = await deleteJobPosting(jobPostingId);
      const refreshedJobs = await refreshJobHistory();

      if (deletedWasSelected) {
        clearSelectedJob();
        if (Array.isArray(refreshedJobs) && refreshedJobs.length > 0) {
          await selectStoredJob(refreshedJobs[0].id);
        }
      }

      setMessage({
        type: "success",
        text: `Oferta ${payload.id} została usunięta z historii.`,
      });
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setDeletingJobId(null);
    }
  }

  const normalizedHistoryFilter = historyFilter.trim().toLowerCase();
  const filteredJobHistory = jobHistory.filter((job) => matchesHistoryFilter(job, normalizedHistoryFilter));
  const parsedPreviewStats = parsedJobPosting ? buildParsedPreviewStats(parsedJobPosting) : [];

  return (
    <section className="tab-content">
      <div className="section-header tab-header">
        <div>
          <h2>Oferta</h2>
          <p className="section-copy">
            Wczytaj ofertę pracy z linku i zapisz ją do historii.
          </p>
        </div>
      </div>

      {message ? <div className={`message ${message.type}`}>{message.text}</div> : null}

      <div className="workspace-grid">
        <section className="section-card section-wide">
          <div className="section-header">
            <div>
              <h3>Dodaj ofertę</h3>
              <p className="section-copy">
                Wklej link do oferty, wczytaj jej treść, a potem zapisz wynik do lokalnej historii.
              </p>
            </div>
          </div>

          <label className="field">
            <span>URL oferty pracy</span>
            <input
              type="url"
              placeholder="https://www.pracuj.pl/praca/..."
              value={jobUrl}
              onChange={(event) => setJobUrl(event.target.value)}
            />
          </label>

          <div className="actions">
            <button type="button" onClick={handleParseClick} disabled={parseLoading || saveLoading || !jobUrl.trim()}>
              {parseLoading ? "Wczytywanie..." : "Wczytaj ofertę"}
            </button>
            <button type="button" onClick={handleSaveClick} disabled={saveLoading || !parsedJobPosting}>
              {saveLoading ? "Zapisywanie..." : "Zapisz ofertę"}
            </button>
          </div>

          <section className="result-panel compact-preview">
            <h4>Podgląd oferty</h4>
            {parsedJobPosting ? (
              <div className="parsed-preview">
                <span className="section-eyebrow">Aktualnie wczytany wynik z linku</span>
                <div className="preview-header">
                  <div>
                    <h5 className="preview-title">{parsedJobPosting.title || "Brak tytułu"}</h5>
                    <p className="preview-company">{parsedJobPosting.company_name || "Brak nazwy firmy"}</p>
                  </div>
                </div>

                <dl className="preview-grid">
                  {parsedPreviewStats.map((item) => (
                    <div key={item.label}>
                      <dt>{item.label}</dt>
                      <dd>{item.value}</dd>
                    </div>
                  ))}
                </dl>

                <section className="detail-section preview-section">
                  <h5>Opis roli</h5>
                  <p className="detail-text">{parsedJobPosting.role_summary || "Brak opisu roli."}</p>
                </section>

                <RawJsonPanel summary="Szczegóły techniczne oferty" value={parsedJobPosting} />
              </div>
            ) : (
              <p className="placeholder">
                Po wczytaniu tutaj pojawi się krótki podgląd najważniejszych pól nowej oferty.
              </p>
            )}
          </section>
        </section>

        <section className="section-card scroll-panel">
          <div className="section-header section-header-inline">
            <div>
              <h3>Historia ofert</h3>
              <p className="section-copy">Zapisane oferty. Wybierz rekord, aby zobaczyć szczegóły.</p>
            </div>
            <button
              type="button"
              className="ghost-button"
              onClick={() => void refreshJobHistory()}
              disabled={historyLoading || parseLoading || saveLoading || deletingJobId !== null}
            >
              {historyLoading ? "Odświeżanie..." : "Odśwież"}
            </button>
          </div>

          <div className="scroll-panel-body history-panel-body">
            <label className="field">
              <span>Filtr historii</span>
              <input
                type="text"
                placeholder="Szukaj po tytule lub firmie"
                value={historyFilter}
                onChange={(event) => setHistoryFilter(event.target.value)}
              />
            </label>

            <div className="history-summary">
              {filteredJobHistory.length} z {jobHistory.length} ofert widocznych
            </div>

            {historyError ? <div className="message error">{historyError}</div> : null}

            {historyLoading ? (
              <p className="placeholder">Ładowanie historii ofert...</p>
            ) : filteredJobHistory.length > 0 ? (
              <div className="history-list-wrapper">
                <div className="history-list">
                  {filteredJobHistory.map((job) => (
                    <div key={job.id} className={`history-item${selectedJobId === job.id ? " active" : ""}`}>
                      <button
                        type="button"
                        className="history-select-button"
                        onClick={() => void selectStoredJob(job.id)}
                        disabled={selectedJobLoading || deletingJobId !== null}
                      >
                        <span className="history-title">{job.title}</span>
                        <span className="history-company">{job.company_name}</span>
                        <span className="history-meta">{job.location || "brak lokalizacji"}</span>
                        <span className="history-meta">{job.source || "brak źródła"}</span>
                        <span className="history-meta history-meta-secondary">
                          Zapisano: {formatSavedAt(job.saved_at)}
                        </span>
                      </button>

                      <button
                        type="button"
                        className="history-delete-button"
                        onClick={(event) => void handleDeleteJobClick(job.id, event)}
                        disabled={deletingJobId !== null || parseLoading || saveLoading}
                      >
                        {deletingJobId === job.id ? "Usuwanie..." : "Usuń"}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="placeholder">
                {jobHistory.length > 0
                  ? "Brak ofert pasujących do filtra."
                  : "Brak zapisanych ofert. Zapisane rekordy pojawią się tutaj."}
              </p>
            )}
          </div>
        </section>

        <section className="section-card scroll-panel">
          <div className="section-header">
            <div>
              <h3>Szczegóły wybranej oferty</h3>
              <p className="section-copy">
                To jest zapisany rekord wybrany z historii. Pełne dane pobieramy dopiero po kliknięciu oferty.
              </p>
            </div>
          </div>

          <div className="scroll-panel-body selected-job-panel-body">
            {selectedJobLoading ? <p className="placeholder">Ładowanie szczegółów oferty...</p> : null}
            {selectedJobError ? <div className="message error">{selectedJobError}</div> : null}

            {selectedJobDetail?.payload ? (
              <>
                <dl className="detail-grid record-meta-grid">
                  <div>
                    <dt>ID</dt>
                    <dd>{selectedJobDetail.id}</dd>
                  </div>
                  <div>
                    <dt>Zapisano</dt>
                    <dd>{formatSavedAt(selectedJobDetail.saved_at)}</dd>
                  </div>
                  <div>
                    <dt>Źródło</dt>
                    <dd>{selectedJobDetail.source}</dd>
                  </div>
                  <div>
                    <dt>URL</dt>
                    <dd>{selectedJobDetail.source_url ?? "brak"}</dd>
                  </div>
                </dl>

                <JobPostingDetails
                  jobPosting={selectedJobDetail.payload}
                  rawJsonLabel="Szczegóły techniczne zapisanej oferty"
                />
              </>
            ) : !selectedJobLoading ? (
              <p className="placeholder">Wybierz ofertę z historii, aby zobaczyć jej zapisane szczegóły.</p>
            ) : null}
          </div>
        </section>
      </div>
    </section>
  );
}
