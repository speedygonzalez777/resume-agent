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
 * Format one FastAPI or Pydantic validation path into a readable dotted label.
 *
 * @param {unknown} location Raw `loc` value returned by the backend.
 * @returns {string} Human-readable field path.
 */
function formatErrorLocation(location) {
  if (!Array.isArray(location)) {
    return "";
  }

  return location
    .filter((part) => part !== "body" && part !== "query" && part !== "path")
    .map((part) => String(part))
    .join(".");
}

/**
 * Convert one structured backend error item into a readable line.
 *
 * @param {unknown} detailItem Raw detail item returned by the backend.
 * @returns {string | null} User-facing error line or null when unavailable.
 */
function formatStructuredDetailItem(detailItem) {
  if (typeof detailItem === "string") {
    return detailItem;
  }

  if (!detailItem || typeof detailItem !== "object") {
    return null;
  }

  const message =
    typeof detailItem.msg === "string"
      ? detailItem.msg
      : typeof detailItem.message === "string"
        ? detailItem.message
        : typeof detailItem.error === "string"
          ? detailItem.error
          : null;

  if (!message) {
    return null;
  }

  const location = formatErrorLocation(detailItem.loc);
  return location ? `${location}: ${message}` : message;
}

/**
 * Normalize any backend error payload into readable UI text.
 *
 * @param {unknown} payload Parsed backend payload.
 * @returns {string} User-facing error text.
 */
function extractErrorMessage(payload) {
  if (!payload || typeof payload !== "object") {
    return "Backend request failed.";
  }

  const detail = payload.detail ?? payload.message ?? payload.error;

  if (typeof detail === "string" && detail) {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail.map(formatStructuredDetailItem).filter(Boolean);
    if (messages.length > 0) {
      return `Niepoprawne dane formularza: ${messages.join(" | ")}`;
    }
  }

  if (detail && typeof detail === "object") {
    const structuredMessage = formatStructuredDetailItem(detail);
    if (structuredMessage) {
      return structuredMessage;
    }
  }

  if (typeof payload.message === "string" && payload.message) {
    return payload.message;
  }

  if (typeof payload.error === "string" && payload.error) {
    return payload.error;
  }

  return "Backend request failed.";
}

/**
 * Error thrown by API helpers while preserving backend response metadata.
 */
export class ApiError extends Error {
  /**
   * @param {string} message User-facing message.
   * @param {{status: number, responseBody: unknown}} options Response metadata.
   */
  constructor(message, { status, responseBody }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.responseBody = responseBody;
    this.data = responseBody;
  }
}

/**
 * Read a JSON response and convert HTTP failures into readable errors.
 *
 * @param {Response} response Raw Fetch API response.
 * @returns {Promise<unknown>} Parsed JSON payload.
 * @throws {Error} Raised when the backend responds with a non-2xx status.
 */
async function readJson(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = {
      detail: response.statusText || "Backend request failed.",
    };
  }

  if (!response.ok) {
    throw new ApiError(extractErrorMessage(payload), {
      status: response.status,
      responseBody: payload,
    });
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
 * Update one existing candidate profile through the backend persistence endpoint.
 *
 * @param {number} profileId Database identifier of the stored candidate profile.
 * @param {object} profile CandidateProfile payload.
 * @returns {Promise<object>} Updated candidate profile response from the backend.
 */
export async function updateCandidateProfile(profileId, profile) {
  const response = await fetch(buildApiUrl(`/profile/${profileId}`), {
    method: "PUT",
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
 * Run debug matching analysis for one selected profile and one selected job posting.
 *
 * @param {object} candidateProfile CandidateProfile payload.
 * @param {object} jobPosting JobPosting payload.
 * @returns {Promise<{match_result: object, matching_debug: object, matching_handoff: object}>}
 * Debug match payload returned by the backend.
 */
export async function analyzeMatchDebug(candidateProfile, jobPosting) {
  const response = await fetch(buildApiUrl("/match/analyze-debug"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      candidate_profile: candidateProfile,
      job_posting: jobPosting,
    }),
  });
  return /** @type {Promise<{match_result: object, matching_debug: object, matching_handoff: object}>} */ (readJson(response));
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
 * Save one MatchResult as an archival snapshot tied to a profile and job pair.
 *
 * @param {object} matchResult MatchResult payload.
 * @param {number | null} candidateProfileId Stored candidate profile ID.
 * @param {number | null} jobPostingId Stored job posting ID.
 * @returns {Promise<object>} Stored match snapshot response.
 */
export async function saveMatchResult(matchResult, candidateProfileId, jobPostingId) {
  const response = await fetch(buildApiUrl("/match/save"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      match_result: matchResult,
      candidate_profile_id: candidateProfileId ?? null,
      job_posting_id: jobPostingId ?? null,
    }),
  });
  return /** @type {Promise<object>} */ (readJson(response));
}

/**
 * Generate a structured ResumeDraft and ChangeReport from profile, offer and matching.
 *
 * @param {object} candidateProfile CandidateProfile payload.
 * @param {object} jobPosting JobPosting payload.
 * @param {object | null | undefined} matchResult MatchResult payload.
 * @param {object | null | undefined} matchingHandoff Optional matching sidecars reused by generation.
 * @param {number | null | undefined} candidateProfileId Stored candidate profile ID used for persistence links.
 * @param {number | null | undefined} jobPostingId Stored job posting ID used for persistence links.
 * @param {number | null | undefined} matchResultId Stored match-result snapshot ID used for persistence links.
 * @returns {Promise<{
 *   resume_draft: object,
 *   change_report: object,
 *   generation_mode: string,
 *   match_result_source: string,
 *   fallback_reason: string | null,
 *   generation_notes: string[],
 *   offer_signal_debug: object | null,
 *   generation_debug: object | null,
 *   resume_draft_record_id: number | null,
 *   resume_draft_saved_at: string | null,
 *   persistence_warning: string | null
 * }>} Generated draft artifacts together with generation metadata.
 */
export async function generateResumeDraft(
  candidateProfile,
  jobPosting,
  matchResult,
  matchingHandoff,
  candidateProfileId,
  jobPostingId,
  matchResultId,
) {
  const response = await fetch(buildApiUrl("/resume/generate"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      candidate_profile: candidateProfile,
      job_posting: jobPosting,
      match_result: matchResult ?? null,
      matching_handoff: matchingHandoff ?? null,
      candidate_profile_id: candidateProfileId ?? null,
      job_posting_id: jobPostingId ?? null,
      match_result_id: matchResultId ?? null,
    }),
  });
  return /** @type {Promise<{resume_draft: object, change_report: object, generation_mode: string, match_result_source: string, fallback_reason: string | null, generation_notes: string[], offer_signal_debug: object | null, generation_debug: object | null, resume_draft_record_id: number | null, resume_draft_saved_at: string | null, persistence_warning: string | null}>} */ (readJson(response));
}

/**
 * Apply optional AI refinement to an already generated ResumeDraft.
 *
 * @param {object} resumeDraft Existing ResumeDraft payload.
 * @param {{
 *   must_include_terms: string[],
 *   avoid_or_deemphasize_terms: string[],
 *   forbidden_claims_or_phrases: string[],
 *   skills_allowlist: string[],
 *   additional_instructions?: string | null
 * }} guidance Optional user guidance for the refinement step.
 * @param {number | null | undefined} resumeDraftRecordId Stored resume-draft record ID used for persistence update.
 * @returns {Promise<{
 *   refined_resume_draft: object,
 *   refinement_patch: object,
 *   resume_draft_record_id: number | null,
 *   resume_draft_updated_at: string | null,
 *   persistence_warning: string | null
 * }>} Refined draft together with the structured patch returned by the model.
 */
export async function refineResumeDraft(resumeDraft, guidance, resumeDraftRecordId) {
  const response = await fetch(buildApiUrl("/resume/refine-draft"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      resume_draft: resumeDraft,
      guidance,
      resume_draft_record_id: resumeDraftRecordId ?? null,
    }),
  });
  return /** @type {Promise<{refined_resume_draft: object, refinement_patch: object, resume_draft_record_id: number | null, resume_draft_updated_at: string | null, persistence_warning: string | null}>} */ (readJson(response));
}

/**
 * Load stored resume-draft history from the backend, optionally filtered by one profile-offer pair.
 *
 * @param {number} [limit=50] Maximum number of records to fetch.
 * @param {number | null | undefined} candidateProfileId Optional stored profile ID filter.
 * @param {number | null | undefined} jobPostingId Optional stored job ID filter.
 * @returns {Promise<object[]>} Stored resume-draft list items.
 */
export async function listResumeDrafts(limit = 50, candidateProfileId, jobPostingId) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (candidateProfileId != null) {
    params.set("candidate_profile_id", String(candidateProfileId));
  }
  if (jobPostingId != null) {
    params.set("job_posting_id", String(jobPostingId));
  }

  const response = await fetch(buildApiUrl(`/resume/drafts?${params.toString()}`));
  return /** @type {Promise<object[]>} */ (readJson(response));
}

/**
 * Load one stored resume-draft record together with its base and refined artifacts.
 *
 * @param {number} draftId Database identifier of the stored resume draft.
 * @returns {Promise<{
 *   id: number,
 *   saved_at: string,
 *   updated_at: string,
 *   candidate_profile_id: number | null,
 *   job_posting_id: number | null,
 *   match_result_id: number | null,
 *   target_job_title: string | null,
 *   target_company_name: string | null,
 *   generation_mode: string,
 *   has_refined_version: boolean,
 *   base_resume_artifacts: object,
 *   resume_debug_envelope: {
 *     matching_handoff: boolean | null,
 *     request_body: object | null,
 *     response_body: object | null,
 *     request_body_unavailable_reason: string | null,
 *   },
 *   refined_resume_artifacts: object | null,
 * }>} Stored resume-draft detail response.
 */
export async function getResumeDraftDetail(draftId) {
  const response = await fetch(buildApiUrl(`/resume/drafts/${draftId}`));
  return /** @type {Promise<object>} */ (readJson(response));
}

/**
 * Prepare a final TypstPayload from a stored or inline ResumeDraft source.
 *
 * @param {object} requestBody Typst prepare request body.
 * @returns {Promise<{typst_payload: object, prepare_debug: object | null}>} Prepared Typst payload.
 */
export async function prepareTypstResume(requestBody) {
  const response = await fetch(buildApiUrl("/resume/typst/prepare"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });
  return /** @type {Promise<{typst_payload: object, prepare_debug: object | null}>} */ (readJson(response));
}

/**
 * Render one prepared TypstPayload into local .typ and .pdf artifacts.
 *
 * @param {object} typstPayload Prepared TypstPayload returned by /resume/typst/prepare.
 * @returns {Promise<object>} Typst render response with artifact metadata.
 */
export async function renderTypstResume(typstPayload) {
  const response = await fetch(buildApiUrl("/resume/typst/render"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      typst_payload: typstPayload,
    }),
  });
  return /** @type {Promise<object>} */ (readJson(response));
}

/**
 * Analyze a rendered Typst CV document without modifying the TypstPayload.
 *
 * @param {object} requestBody Typst quality-analysis request body.
 * @returns {Promise<object>} Structured quality-analysis response.
 */
export async function analyzeTypstRender(requestBody) {
  const response = await fetch(buildApiUrl("/resume/typst/analyze-render"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });
  return /** @type {Promise<object>} */ (readJson(response));
}

/**
 * Create a safe patch for fitting an existing TypstPayload to the rendered page.
 *
 * @param {object} requestBody Typst fit-to-page request body.
 * @returns {Promise<object>} Fit-to-page response with patch, merged payload and debug metadata.
 */
export async function fitTypstPayloadToPage(requestBody) {
  const response = await fetch(buildApiUrl("/resume/typst/fit-to-page"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });
  return /** @type {Promise<object>} */ (readJson(response));
}

/**
 * Upload one resume photo asset for the Typst renderer.
 *
 * @param {File} file Selected JPEG or PNG photo file.
 * @returns {Promise<{photo_asset_id: string, photo_artifact: object, warnings: string[]}>} Stored photo metadata.
 */
export async function uploadResumePhoto(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(buildApiUrl("/resume/typst/photo-assets"), {
    method: "POST",
    body: formData,
  });
  return /** @type {Promise<{photo_asset_id: string, photo_artifact: object, warnings: string[]}>} */ (readJson(response));
}

/**
 * Build the public URL for downloading a generated Typst source or PDF artifact.
 *
 * @param {string} renderId Render identifier returned by /resume/typst/render.
 * @param {"typ" | "pdf"} artifactType Artifact kind to download.
 * @returns {string} Download URL.
 */
export function buildTypstArtifactDownloadUrl(renderId, artifactType) {
  return buildApiUrl(
    `/resume/typst/artifacts/${encodeURIComponent(renderId)}/${encodeURIComponent(artifactType)}?disposition=attachment`,
  );
}

/**
 * Build the public inline preview URL for a generated Typst PDF artifact.
 *
 * @param {string} renderId Render identifier returned by /resume/typst/render.
 * @param {"pdf"} artifactType Artifact kind to preview.
 * @returns {string} Inline preview URL.
 */
export function buildTypstArtifactPreviewUrl(renderId, artifactType) {
  return buildApiUrl(
    `/resume/typst/artifacts/${encodeURIComponent(renderId)}/${encodeURIComponent(artifactType)}?disposition=inline`,
  );
}
