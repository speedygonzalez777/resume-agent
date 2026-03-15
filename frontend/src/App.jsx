import { useEffect, useState } from "react";

import { checkBackendHealth, parseJobPosting, saveJobPosting } from "./api";

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
 * Render the single-screen frontend MVP for parsing and saving job postings.
 *
 * @returns {JSX.Element} Root application view.
 */
export default function App() {
  const [backendStatus, setBackendStatus] = useState("Sprawdzanie...");
  const [jobUrl, setJobUrl] = useState("");
  const [parsedJobPosting, setParsedJobPosting] = useState(null);
  const [parseLoading, setParseLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    /**
     * Load backend health once on initial render.
     *
     * @returns {Promise<void>} Promise resolved after the health status is updated.
     */
    async function loadHealth() {
      try {
        const payload = await checkBackendHealth();
        setBackendStatus(payload.status === "ok" ? "Backend dziala" : "Backend odpowiada nieoczekiwanie");
      } catch (error) {
        setBackendStatus(`Blad polaczenia: ${getErrorMessage(error)}`);
      }
    }

    loadHealth();
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
      setMessage({ type: "success", text: "Oferta zostala sparsowana." });
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setParseLoading(false);
    }
  }

  /**
   * Save the currently parsed JobPosting using the existing backend persistence endpoint.
   *
   * @returns {Promise<void>} Promise resolved after save state is updated.
   */
  async function handleSaveClick() {
    if (!parsedJobPosting) {
      return;
    }

    setSaveLoading(true);
    setMessage(null);

    try {
      const payload = await saveJobPosting(parsedJobPosting, jobUrl.trim());
      setMessage({
        type: "success",
        text: `Oferta zostala zapisana z ID ${payload.id}.`,
      });
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setSaveLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="panel">
        <h1>Resume Tailoring Agent</h1>
        <p className="subtitle">Minimalny frontend MVP dla parsowania ofert pracy i zapisu do SQLite.</p>

        <div className="status-row">
          <span className="label">Health check:</span>
          <span>{backendStatus}</span>
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
            {parseLoading ? "Parsowanie..." : "Parsuj oferte"}
          </button>
          <button type="button" onClick={handleSaveClick} disabled={saveLoading || !parsedJobPosting}>
            {saveLoading ? "Zapisywanie..." : "Zapisz oferte"}
          </button>
        </div>

        {message ? <div className={`message ${message.type}`}>{message.text}</div> : null}

        <section className="result-panel">
          <h2>JobPosting</h2>
          {parsedJobPosting ? (
            <pre>{JSON.stringify(parsedJobPosting, null, 2)}</pre>
          ) : (
            <p className="placeholder">Po sparsowaniu tutaj pojawi sie odpowiedz backendu.</p>
          )}
        </section>
      </section>
    </main>
  );
}
