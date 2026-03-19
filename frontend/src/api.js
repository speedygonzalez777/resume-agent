/**
 * Minimal frontend helpers for talking to the local FastAPI backend.
 */

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

/**
 * Load the stored job posting history from the backend.
 *
 * @param {number} [limit=50] Maximum number of records to fetch.
 * @returns {Promise<object[]>} Stored job posting list items.
 */
export async function listJobPostings(limit = 50) {
  const response = await fetch(buildApiUrl(`/job?limit=${limit}`));
  return /** @type {Promise<object[]>} */ (readJson(response));
}

/**
 * Load the full stored job posting payload for a selected record.
 *
 * @param {number} jobPostingId Database identifier of the stored job posting.
 * @returns {Promise<object>} Stored job posting detail response.
 */
export async function getJobPostingDetail(jobPostingId) {
  const response = await fetch(buildApiUrl(`/job/${jobPostingId}`));
  return /** @type {Promise<object>} */ (readJson(response));
}

/**
 * Delete one stored job posting from the backend history.
 *
 * @param {number} jobPostingId Database identifier of the stored job posting.
 * @returns {Promise<{id: number, deleted: boolean, message: string}>} Delete confirmation payload.
 */
export async function deleteJobPosting(jobPostingId) {
  const response = await fetch(buildApiUrl(`/job/${jobPostingId}`), {
    method: "DELETE",
  });
  return /** @type {Promise<{id: number, deleted: boolean, message: string}>} */ (readJson(response));
}

/**
 * Save a candidate profile through the existing backend persistence endpoint.
 *
 * @param {object} profile CandidateProfile payload.
 * @returns {Promise<object>} Stored candidate profile response from the backend.
 */
export async function saveCandidateProfile(profile) {
  const response = await fetch(buildApiUrl("/profile/save"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(profile),
  });
  return /** @type {Promise<object>} */ (readJson(response));
}

/**
 * Load the stored candidate profile history from the backend.
 *
 * @param {number} [limit=50] Maximum number of records to fetch.
 * @returns {Promise<object[]>} Stored candidate profile list items.
 */
export async function listCandidateProfiles(limit = 50) {
  const response = await fetch(buildApiUrl(`/profile?limit=${limit}`));
  return /** @type {Promise<object[]>} */ (readJson(response));
}

/**
 * Load the full stored candidate profile payload for a selected record.
 *
 * @param {number} profileId Database identifier of the stored candidate profile.
 * @returns {Promise<object>} Stored candidate profile detail response.
 */
export async function getCandidateProfileDetail(profileId) {
  const response = await fetch(buildApiUrl(`/profile/${profileId}`));
  return /** @type {Promise<object>} */ (readJson(response));
}

/**
 * Delete one stored candidate profile from the backend history.
 *
 * @param {number} profileId Database identifier of the stored candidate profile.
 * @returns {Promise<{id: number, deleted: boolean, message: string}>} Delete confirmation payload.
 */
export async function deleteCandidateProfile(profileId) {
  const response = await fetch(buildApiUrl(`/profile/${profileId}`), {
    method: "DELETE",
  });
  return /** @type {Promise<{id: number, deleted: boolean, message: string}>} */ (readJson(response));
}

/**
 * Run matching analysis for one selected profile and one selected job posting.
 *
 * @param {object} candidateProfile CandidateProfile payload.
 * @param {object} jobPosting JobPosting payload.
 * @returns {Promise<object>} MatchResult payload returned by the backend.
 */
export async function analyzeMatch(candidateProfile, jobPosting) {
  const response = await fetch(buildApiUrl("/match/analyze"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      candidate_profile: candidateProfile,
      job_posting: jobPosting,
    }),
  });
  return /** @type {Promise<object>} */ (readJson(response));
}

/**
 * Load the stored match-result history from the backend.
 *
 * @param {number} [limit=50] Maximum number of records to fetch.
 * @returns {Promise<object[]>} Stored match-result list items.
 */
export async function listMatchResults(limit = 50) {
  const response = await fetch(buildApiUrl(`/match?limit=${limit}`));
  return /** @type {Promise<object[]>} */ (readJson(response));
}

/**
 * Load the full stored MatchResult payload for a selected record.
 *
 * @param {number} matchResultId Database identifier of the stored match result.
 * @returns {Promise<object>} Stored match-result detail response.
 */
export async function getMatchResultDetail(matchResultId) {
  const response = await fetch(buildApiUrl(`/match/${matchResultId}`));
  return /** @type {Promise<object>} */ (readJson(response));
}

/**
 * Save a MatchResult through the backend persistence endpoint.
 *
 * @param {object} matchResult MatchResult payload.
 * @param {number | null} candidateProfileId Selected stored profile ID.
 * @param {number | null} jobPostingId Selected stored job posting ID.
 * @returns {Promise<object>} Stored match result response from the backend.
 */
export async function saveMatchResult(matchResult, candidateProfileId, jobPostingId) {
  const response = await fetch(buildApiUrl("/match/save"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      match_result: matchResult,
      candidate_profile_id: candidateProfileId,
      job_posting_id: jobPostingId,
    }),
  });
  return /** @type {Promise<object>} */ (readJson(response));
}

/**
 * Generate a structured ResumeDraft and ChangeReport from profile, offer and matching.
 *
 * @param {object} candidateProfile CandidateProfile payload.
 * @param {object} jobPosting JobPosting payload.
 * @param {object} matchResult MatchResult payload.
 * @returns {Promise<{resume_draft: object, change_report: object}>} Generated draft artifacts.
 */
export async function generateResumeDraft(candidateProfile, jobPosting, matchResult) {
  const response = await fetch(buildApiUrl("/resume/generate"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      candidate_profile: candidateProfile,
      job_posting: jobPosting,
      match_result: matchResult,
    }),
  });
  return /** @type {Promise<{resume_draft: object, change_report: object}>} */ (readJson(response));
}
