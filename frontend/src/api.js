const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * Build a full backend URL from a relative API path.
 *
 * @param {string} path Relative API path starting with a slash.
 * @returns {string} Fully qualified backend URL.
 */
function buildApiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

/**
 * Read a JSON response and convert HTTP failures into readable errors.
 *
 * @param {Response} response Raw Fetch API response.
 * @returns {Promise<unknown>} Parsed JSON payload.
 * @throws {Error} Raised when the backend responds with a non-2xx status.
 */
async function readJson(response) {
  const payload = await response.json();
  if (!response.ok) {
    const message =
      payload?.detail?.message ??
      payload?.detail?.error ??
      payload?.detail ??
      payload?.message ??
      "Backend request failed.";
    throw new Error(String(message));
  }
  return payload;
}

/**
 * Check whether the backend health endpoint is reachable.
 *
 * @returns {Promise<{status: string}>} Health payload returned by the backend.
 */
export async function checkBackendHealth() {
  const response = await fetch(buildApiUrl("/health"));
  return /** @type {Promise<{status: string}>} */ (readJson(response));
}

/**
 * Parse a job posting from a public URL using the backend parser flow.
 *
 * @param {string} url Public job posting URL.
 * @returns {Promise<object>} Parsed JobPosting payload.
 */
export async function parseJobPosting(url) {
  const response = await fetch(buildApiUrl("/job/parse-url"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ url }),
  });
  return /** @type {Promise<object>} */ (readJson(response));
}

/**
 * Save a parsed JobPosting through the existing backend persistence endpoint.
 *
 * @param {object} jobPosting Parsed JobPosting payload.
 * @param {string} sourceUrl Source URL used to obtain the offer.
 * @returns {Promise<object>} Stored job posting response from the backend.
 */
export async function saveJobPosting(jobPosting, sourceUrl) {
  const response = await fetch(buildApiUrl("/job/save"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      job_posting: jobPosting,
      source_url: sourceUrl || null,
    }),
  });
  return /** @type {Promise<object>} */ (readJson(response));
}
