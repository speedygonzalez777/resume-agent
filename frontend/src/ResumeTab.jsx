/**
 * Resume-generation tab for selecting saved records, preparing fit data and generating CV drafts.
 */

import { useEffect, useState } from "react";

import {
  analyzeMatch,
  analyzeMatchDebug,
  generateResumeDraft,
  getCandidateProfileDetail,
  getJobPostingDetail,
  getMatchResultDetail,
  getResumeDraftDetail,
  listCandidateProfiles,
  listJobPostings,
  listMatchResults,
  listResumeDrafts,
  refineResumeDraft,
  saveMatchResult,
} from "./api";
import ChangeReportDetails from "./ChangeReportDetails";
import RawJsonPanel from "./RawJsonPanel";
import ResumeDraftDetails from "./ResumeDraftDetails";
import TagListInput from "./TagListInput";

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
 * Convert refinement errors into a calm, user-facing message that keeps the base draft safe.
 *
 * @param {unknown} error Error-like value thrown by the refinement request.
 * @returns {string} Friendly refinement error message.
 */
function getRefinementErrorMessage(error) {
  const message = getErrorMessage(error);

  if (message.includes("AI CV refinement is unavailable")) {
    return "Nie udalo sie uruchomic AI poprawy draftu. Bazowy draft nadal jest dostepny.";
  }

  return "Nie udalo sie przygotowac AI poprawionej wersji CV. Bazowy draft nadal jest dostepny.";
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
 * @returns {{
 *   matchResult: object | null,
 *   matchingDebug: object | null,
 *   matchingHandoff: object | null,
 *   routeMode: string,
 *   profileId: number | null,
 *   jobId: number | null,
 *   source: {type: string, id?: number | null, savedAt?: string | null}
 * }}
 * Fresh empty session state.
 */
function createEmptyActiveMatchSession() {
  return {
    matchResult: null,
    matchingDebug: null,
    matchingHandoff: null,
    routeMode: "none",
    profileId: null,
    jobId: null,
    source: { type: "none" },
  };
}

/**
 * Build the empty developer debug state shown in the collapsible debug section.
 *
 * @returns {{
 *   lastMatchingRequestBody: object | null,
 *   lastMatchingResponseBody: object | null,
 *   lastMatchingRouteMode: string,
 *   lastResumeRequestBody: object | null,
 *   lastResumeResponseBody: object | null,
 *   lastResumeMatchingHandoff: boolean | null,
 *   lastResumeRequestBodyUnavailableReason: string | null
 * }} Fresh empty developer debug state.
 */
function createEmptyDeveloperDebugState() {
  return {
    lastMatchingRequestBody: null,
    lastMatchingResponseBody: null,
    lastMatchingRouteMode: "none",
    lastResumeRequestBody: null,
    lastResumeResponseBody: null,
    lastResumeMatchingHandoff: null,
    lastResumeRequestBodyUnavailableReason: null,
  };
}

/**
 * Describe whether the historical resume request used matching handoff.
 *
 * @param {boolean | null} value Stored matching-handoff flag.
 * @param {string | null} unavailableReason Optional missing-request explanation.
 * @returns {string} Readable label used by the debug panel.
 */
function describeResumeMatchingHandoff(value, unavailableReason) {
  if (value === true) {
    return "tak";
  }
  if (value === false) {
    return "nie";
  }
  if (unavailableReason) {
    return "brak danych historycznych";
  }
  return "brak";
}

/**
 * Build the empty optional AI refinement guidance used after draft generation.
 *
 * @returns {{
 *   must_include_terms: string[],
 *   avoid_or_deemphasize_terms: string[],
 *   forbidden_claims_or_phrases: string[],
 *   skills_allowlist: string[],
 *   additional_instructions: string
 * }} Fresh empty refinement guidance state.
 */
function createEmptyRefinementGuidanceState() {
  return {
    must_include_terms: [],
    avoid_or_deemphasize_terms: [],
    forbidden_claims_or_phrases: [],
    skills_allowlist: [],
    additional_instructions: "",
  };
}

/**
 * Check whether the user has provided at least one refinement hint.
 *
 * @param {{
 *   must_include_terms: string[],
 *   avoid_or_deemphasize_terms: string[],
 *   forbidden_claims_or_phrases: string[],
 *   skills_allowlist: string[],
 *   additional_instructions: string
 * }} guidance Current refinement guidance draft.
 * @returns {boolean} True when the AI refinement step has any user guidance to use.
 */
function hasAnyRefinementGuidance(guidance) {
  return (
    guidance.must_include_terms.length > 0 ||
    guidance.avoid_or_deemphasize_terms.length > 0 ||
    guidance.forbidden_claims_or_phrases.length > 0 ||
    guidance.skills_allowlist.length > 0 ||
    guidance.additional_instructions.trim().length > 0
  );
}

/**
 * Build the backend request body used for both matching routes.
 *
 * @param {object} candidateProfile CandidateProfile payload.
 * @param {object} jobPosting JobPosting payload.
 * @returns {{candidate_profile: object, job_posting: object}} Shared matching request body.
 */
function buildMatchAnalyzeRequest(candidateProfile, jobPosting) {
  return {
    candidate_profile: candidateProfile,
    job_posting: jobPosting,
  };
}

/**
 * Build the backend request body used by resume generation.
 *
 * @param {object} candidateProfile CandidateProfile payload.
 * @param {object} jobPosting JobPosting payload.
 * @param {object | null | undefined} matchResult MatchResult payload.
 * @param {object | null | undefined} matchingHandoff Optional matching handoff payload.
 * @param {number | null | undefined} candidateProfileId Stored candidate profile ID.
 * @param {number | null | undefined} jobPostingId Stored job posting ID.
 * @param {number | null | undefined} matchResultId Stored match-result snapshot ID.
 * @returns {{
 *   candidate_profile: object,
 *   job_posting: object,
 *   match_result: object | null,
 *   matching_handoff: object | null,
 *   candidate_profile_id: number | null,
 *   job_posting_id: number | null,
 *   match_result_id: number | null,
 * }}
 * Resume-generation request body.
 */
function buildResumeGenerationRequest(
  candidateProfile,
  jobPosting,
  matchResult,
  matchingHandoff,
  candidateProfileId,
  jobPostingId,
  matchResultId,
) {
  return {
    candidate_profile: candidateProfile,
    job_posting: jobPosting,
    match_result: matchResult ?? null,
    matching_handoff: matchingHandoff ?? null,
    candidate_profile_id: candidateProfileId ?? null,
    job_posting_id: jobPostingId ?? null,
    match_result_id: matchResultId ?? null,
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
  const [resumeDraftHistory, setResumeDraftHistory] = useState([]);
  const [resumeDraftHistoryLoading, setResumeDraftHistoryLoading] = useState(false);
  const [resumeDraftHistoryError, setResumeDraftHistoryError] = useState(null);
  const [selectedSavedResumeDraftId, setSelectedSavedResumeDraftId] = useState(null);
  const [resumeDraftLoadingId, setResumeDraftLoadingId] = useState(null);

  const [generateLoading, setGenerateLoading] = useState(false);
  const [resumeArtifacts, setResumeArtifacts] = useState(null);
  const [refinementGuidance, setRefinementGuidance] = useState(createEmptyRefinementGuidanceState);
  const [refineLoading, setRefineLoading] = useState(false);
  const [refinedResumeArtifacts, setRefinedResumeArtifacts] = useState(null);
  const [refinementDirty, setRefinementDirty] = useState(false);
  const [resumeDraftView, setResumeDraftView] = useState("base");
  const [developerDebugState, setDeveloperDebugState] = useState(createEmptyDeveloperDebugState);
  const [message, setMessage] = useState(null);

  /**
   * Reset the generated draft state when the selection or fit context changes.
   *
   * @returns {void} No return value.
   */
  function resetGeneratedDraft() {
    setResumeArtifacts(null);
    setRefinedResumeArtifacts(null);
    setRefinementDirty(false);
    setResumeDraftView("base");
    setSelectedSavedResumeDraftId(null);
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
   * Clear developer-facing debug state for the current selection.
   *
   * @returns {void} No return value.
   */
  function clearDeveloperDebugState() {
    setDeveloperDebugState(createEmptyDeveloperDebugState());
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
   * Clear the currently loaded saved-resume-draft history state.
   *
   * @returns {void} No return value.
   */
  function clearResumeDraftHistoryState() {
    setResumeDraftHistory([]);
    setResumeDraftHistoryError(null);
    setSelectedSavedResumeDraftId(null);
    setResumeDraftLoadingId(null);
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
        await Promise.all([
          refreshMatchHistory(selectedProfileId, selectedJobId),
          refreshResumeDraftHistory(selectedProfileId, selectedJobId),
        ]);
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
      clearDeveloperDebugState();
      resetGeneratedDraft();
      void Promise.all([
        refreshMatchHistory(selectedProfileId, selectedJobId),
        refreshResumeDraftHistory(selectedProfileId, selectedJobId),
      ]);
      return;
    }

    clearMatchState();
    clearDeveloperDebugState();
    clearHistoryState();
    clearResumeDraftHistoryState();
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
   * Load saved resume drafts for the selected profile and offer pair.
   *
   * @param {number} profileId Selected candidate profile ID.
   * @param {number} jobId Selected job posting ID.
   * @returns {Promise<void>} Promise resolved after the saved draft list is refreshed.
   */
  async function refreshResumeDraftHistory(profileId, jobId) {
    if (!profileId || !jobId) {
      clearResumeDraftHistoryState();
      return;
    }

    setResumeDraftHistoryLoading(true);
    setResumeDraftHistoryError(null);

    try {
      const draftItems = await listResumeDrafts(100, profileId, jobId);
      setResumeDraftHistory(draftItems);
    } catch (error) {
      setResumeDraftHistoryError(getErrorMessage(error));
    } finally {
      setResumeDraftHistoryLoading(false);
    }
  }

  /**
   * Open one stored resume draft and hydrate the current preview without regenerating it.
   *
   * @param {number} draftId Stored resume-draft record ID.
   * @returns {Promise<void>} Promise resolved after the saved draft has been loaded.
   */
  async function handleSavedResumeDraftOpen(draftId) {
    setResumeDraftLoadingId(draftId);
    setResumeDraftHistoryError(null);
    setMatchLookupError(null);
    setMessage(null);

    try {
      const storedDraft = await getResumeDraftDetail(draftId);
      setResumeArtifacts(storedDraft.base_resume_artifacts);
      setRefinedResumeArtifacts(storedDraft.refined_resume_artifacts ?? null);
      setRefinementGuidance(createEmptyRefinementGuidanceState());
      setRefinementDirty(false);
      setResumeDraftView(storedDraft.has_refined_version ? "refined" : "base");
      setSelectedSavedResumeDraftId(draftId);
      setDeveloperDebugState({
        lastMatchingRequestBody: null,
        lastMatchingResponseBody: null,
        lastMatchingRouteMode: "saved",
        lastResumeRequestBody: storedDraft.resume_debug_envelope?.request_body ?? null,
        lastResumeResponseBody:
          storedDraft.resume_debug_envelope?.response_body ?? storedDraft.base_resume_artifacts ?? null,
        lastResumeMatchingHandoff: storedDraft.resume_debug_envelope?.matching_handoff ?? null,
        lastResumeRequestBodyUnavailableReason:
          storedDraft.resume_debug_envelope?.request_body_unavailable_reason ?? null,
      });

      if (storedDraft.match_result_id) {
        try {
          const savedMatch = await getMatchResultDetail(storedDraft.match_result_id);
          setActiveMatchSession({
            matchResult: savedMatch.payload,
            matchingDebug: null,
            matchingHandoff: null,
            routeMode: "saved",
            profileId: storedDraft.candidate_profile_id ?? selectedProfileId,
            jobId: storedDraft.job_posting_id ?? selectedJobId,
            source: {
              type: "saved",
              id: savedMatch.id,
              savedAt: savedMatch.saved_at,
            },
          });
        } catch (error) {
          setMatchLookupError(
            `Draft zostal otwarty, ale nie udalo sie zaladowac powiazanego snapshotu dopasowania: ${getErrorMessage(error)}`,
          );
        }
      } else {
        clearMatchState();
      }

      setMessage({
        type: "info",
        text: storedDraft.has_refined_version
          ? "Otworzono zapisany draft CV z dostepna wersja AI-refined."
          : "Otworzono zapisany draft CV.",
      });
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setResumeDraftLoadingId(null);
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
   * @param {"standard" | "debug"} [routeMode="standard"] Requested matching route mode.
   * @returns {Promise<{
   *   activeMatchSession: {
   *     matchResult: object,
   *     matchingDebug: object | null,
   *     matchingHandoff: object | null,
   *     routeMode: string,
   *     profileId: number | null,
   *     jobId: number | null,
   *     source: {type: string, id?: number | null, savedAt?: string | null}
   *   },
   *   snapshotSaved: boolean
   * }>} Fresh working result and snapshot status.
   */
  async function runFreshMatchSnapshot(routeMode = "standard") {
    if (!selectedProfileDetail?.payload || !selectedJobDetail?.payload) {
      throw new Error("Najpierw wybierz zapisany profil i oferte.");
    }

    const profileId = selectedProfileId;
    const jobId = selectedJobId;
    const requestBody = buildMatchAnalyzeRequest(selectedProfileDetail.payload, selectedJobDetail.payload);

    setMatchLoading(true);
    setMatchLookupError(null);
    setDeveloperDebugState((currentState) => ({
      ...currentState,
      lastMatchingRequestBody: requestBody,
      lastMatchingResponseBody: null,
      lastMatchingRouteMode: routeMode,
    }));

    try {
      let matchResult;
      let matchingDebug = null;
      let matchingHandoff = null;
      let responseBody = null;

      if (routeMode === "debug") {
        const debugPayload = await analyzeMatchDebug(selectedProfileDetail.payload, selectedJobDetail.payload);
        matchResult = debugPayload.match_result;
        matchingDebug = debugPayload.matching_debug ?? null;
        matchingHandoff = debugPayload.matching_handoff ?? null;
        responseBody = debugPayload;
      } else {
        matchResult = await analyzeMatch(selectedProfileDetail.payload, selectedJobDetail.payload);
        responseBody = matchResult;
      }

      setDeveloperDebugState((currentState) => ({
        ...currentState,
        lastMatchingRequestBody: requestBody,
        lastMatchingResponseBody: responseBody,
        lastMatchingRouteMode: routeMode,
      }));

      let nextSource = { type: "session_unsaved" };
      let nextSession = {
        matchResult,
        matchingDebug,
        matchingHandoff,
        routeMode,
        profileId,
        jobId,
        source: nextSource,
      };
      setActiveMatchSession(nextSession);
      let snapshotSaved = false;

      try {
        const savedSnapshot = await saveMatchResult(matchResult, profileId, jobId);
        nextSource = {
          type: "snapshot",
          id: savedSnapshot.id,
          savedAt: savedSnapshot.saved_at,
        };
        nextSession = {
          matchResult,
          matchingDebug,
          matchingHandoff,
          routeMode,
          profileId,
          jobId,
          source: nextSource,
        };
        setActiveMatchSession(nextSession);
        snapshotSaved = true;
      } catch (error) {
        setMatchLookupError(
          `Dopasowanie zostalo przeliczone, ale snapshot historii nie zostal zapisany: ${getErrorMessage(error)}`,
        );
      }

      await refreshMatchHistory(profileId, jobId);
      return { activeMatchSession: nextSession, snapshotSaved };
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
      const { snapshotSaved } = await runFreshMatchSnapshot("standard");
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
   * Run developer-focused debug matching without replacing the standard user flow.
   *
   * @returns {Promise<void>} Promise resolved after the debug matching finishes.
   */
  async function handleAnalyzeDebugClick() {
    setMessage(null);
    resetGeneratedDraft();

    try {
      const { snapshotSaved } = await runFreshMatchSnapshot("debug");
      setMessage({
        type: "info",
        text: snapshotSaved
          ? "Matching debug zostal policzony przez route debugowy i zapisany jako snapshot historii."
          : "Matching debug zostal policzony przez route debugowy, ale snapshot historii nie zostal zapisany.",
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
      const matchingSession = isActiveMatchForSelection(activeMatchSession, selectedProfileId, selectedJobId)
        ? activeMatchSession
        : (await runFreshMatchSnapshot("standard")).activeMatchSession;
      const matchingHandoff =
        matchingSession.routeMode === "debug" && matchingSession.matchingHandoff
          ? matchingSession.matchingHandoff
          : null;
      const requestBody = buildResumeGenerationRequest(
        selectedProfileDetail.payload,
        selectedJobDetail.payload,
        matchingSession.matchResult,
        matchingHandoff,
        selectedProfileId,
        selectedJobId,
        matchingSession.source?.type === "snapshot" || matchingSession.source?.type === "saved"
          ? matchingSession.source.id ?? null
          : null,
      );
      setDeveloperDebugState((currentState) => ({
        ...currentState,
        lastResumeRequestBody: requestBody,
        lastResumeResponseBody: null,
        lastResumeMatchingHandoff: Boolean(matchingHandoff),
        lastResumeRequestBodyUnavailableReason: null,
      }));
      const payload = await generateResumeDraft(
        selectedProfileDetail.payload,
        selectedJobDetail.payload,
        matchingSession.matchResult,
        matchingHandoff,
        selectedProfileId,
        selectedJobId,
        matchingSession.source?.type === "snapshot" || matchingSession.source?.type === "saved"
          ? matchingSession.source.id ?? null
          : null,
      );
      setDeveloperDebugState((currentState) => ({
        ...currentState,
        lastResumeRequestBody: requestBody,
        lastResumeResponseBody: payload,
        lastResumeMatchingHandoff: Boolean(matchingHandoff),
        lastResumeRequestBodyUnavailableReason: null,
      }));
      setResumeArtifacts(payload);
      setSelectedSavedResumeDraftId(payload.resume_draft_record_id ?? null);
      await refreshResumeDraftHistory(selectedProfileId, selectedJobId);
      setMessage(
        payload.persistence_warning
          ? {
              type: "info",
              text: `Draft CV zostal wygenerowany, ale nie zostal zapisany lokalnie: ${payload.persistence_warning}`,
            }
          : {
              type: "success",
              text: payload.resume_draft_record_id
                ? `Draft CV zostal wygenerowany i zapisany jako draft #${payload.resume_draft_record_id}.`
                : "Draft CV zostal wygenerowany.",
            },
      );
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setGenerateLoading(false);
    }
  }

  /**
   * Update one list field of the optional AI refinement guidance and invalidate stale refined results.
   *
   * @param {"must_include_terms" | "avoid_or_deemphasize_terms" | "forbidden_claims_or_phrases" | "skills_allowlist"} fieldName
   * Guidance field to update.
   * @param {string[]} nextItems New list value for that field.
   * @returns {void} No return value.
   */
  function handleRefinementGuidanceListChange(fieldName, nextItems) {
    setRefinementGuidance((currentGuidance) => ({
      ...currentGuidance,
      [fieldName]: nextItems,
    }));
    if (refinedResumeArtifacts) {
      setRefinementDirty(true);
    }
    setMessage(null);
  }

  /**
   * Update the optional free-text AI refinement instructions.
   *
   * @param {string} nextValue New textarea value.
   * @returns {void} No return value.
   */
  function handleAdditionalInstructionsChange(nextValue) {
    setRefinementGuidance((currentGuidance) => ({
      ...currentGuidance,
      additional_instructions: nextValue,
    }));
    if (refinedResumeArtifacts) {
      setRefinementDirty(true);
    }
    setMessage(null);
  }

  /**
   * Apply the optional AI refinement step to the currently generated base draft.
   *
   * @returns {Promise<void>} Promise resolved after AI refinement finishes.
   */
  async function handleRefineClick() {
    if (!resumeArtifacts?.resume_draft) {
      return;
    }

    setRefineLoading(true);
    setMessage(null);

    try {
      const normalizedGuidance = {
        ...refinementGuidance,
        additional_instructions: refinementGuidance.additional_instructions.trim() || null,
      };
      const payload = await refineResumeDraft(
        resumeArtifacts.resume_draft,
        normalizedGuidance,
        resumeArtifacts.resume_draft_record_id ?? null,
      );
      setRefinedResumeArtifacts(payload);
      setRefinementDirty(false);
      setResumeDraftView("refined");
      if (selectedProfileId && selectedJobId) {
        await refreshResumeDraftHistory(selectedProfileId, selectedJobId);
      }
      setMessage(
        payload.persistence_warning
          ? {
              type: "info",
              text: `AI przygotowalo poprawiona wersje draftu, ale nie udalo sie zapisac tej aktualizacji: ${payload.persistence_warning}`,
            }
          : {
              type: "success",
              text: "AI przygotowalo poprawiona wersje draftu. Bazowa wersja nadal jest dostepna jednym kliknieciem.",
            },
      );
    } catch (error) {
      setMessage({ type: "error", text: getRefinementErrorMessage(error) });
    } finally {
      setRefineLoading(false);
    }
  }

  const canGenerate =
    Boolean(selectedProfileDetail?.payload) &&
    Boolean(selectedJobDetail?.payload) &&
    !selectedProfileLoading &&
    !selectedJobLoading;
  const hasRefinementGuidance = hasAnyRefinementGuidance(refinementGuidance);
  const hasRefinedResumeDraft = Boolean(refinedResumeArtifacts?.refined_resume_draft);
  const refinementStatusLabel = refinementDirty
    ? "Wskazowki zmienione"
    : hasRefinedResumeDraft
      ? "AI draft gotowy"
      : hasRefinementGuidance
        ? "Gotowe do uruchomienia"
        : "Opcjonalne";
  const displayedResumeDraft =
    resumeDraftView === "refined" && refinedResumeArtifacts?.refined_resume_draft
      ? refinedResumeArtifacts.refined_resume_draft
      : resumeArtifacts?.resume_draft ?? null;
  const currentResumeDraftRecordId = resumeArtifacts?.resume_draft_record_id ?? null;
  const activeMatchResult = activeMatchSession.matchResult;
  const activeMatchingHandoff = activeMatchSession.matchingHandoff;
  const matchSource = activeMatchSession.source;
  const selectedHistoryPreview = historyPreviewId ? historyPreviewCache[historyPreviewId] ?? null : null;
  const selectedHistoryPreviewMatchResult = selectedHistoryPreview?.payload ?? null;
  const selectedHistoryPreviewStats = summarizeRequirementStatuses(selectedHistoryPreviewMatchResult);
  const selectedHistoryStrengthsPreview = buildPreviewList(selectedHistoryPreviewMatchResult?.strengths);
  const selectedHistoryGapsPreview = buildPreviewList(selectedHistoryPreviewMatchResult?.gaps);
  const matchingDebugEnvelope = {
    request_body: developerDebugState.lastMatchingRequestBody,
    response_body: developerDebugState.lastMatchingResponseBody,
  };
  const resumeDebugEnvelope = {
    matching_handoff: developerDebugState.lastResumeMatchingHandoff,
    request_body: developerDebugState.lastResumeRequestBody,
    response_body: developerDebugState.lastResumeResponseBody,
    request_body_unavailable_reason: developerDebugState.lastResumeRequestBodyUnavailableReason,
  };

  return (
    <section className="tab-content">
      <div className="section-header tab-header">
        <div>
          <h2>Przygotowanie CV</h2>
          <p className="section-copy">
            Przygotuj dopasowanie dla wybranego profilu i oferty, a nastepnie wygeneruj roboczy draft CV.
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
            disabled={lookupLoading || matchLoading || generateLoading || refineLoading}
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
                disabled={lookupLoading || matchLoading || generateLoading || refineLoading}
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
                disabled={lookupLoading || matchLoading || generateLoading || refineLoading}
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
              disabled={!canGenerate || matchLoading || generateLoading || refineLoading}
            >
              {matchLoading ? "Przygotowywanie..." : "Przygotuj dopasowanie do CV"}
            </button>
            <button
              type="button"
              className="primary-button resume-primary-action"
              onClick={handleGenerateClick}
              disabled={!canGenerate || matchLoading || generateLoading || refineLoading}
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

        <details className="raw-json-toggle debug-panel">
          <summary>Debug (developerskie)</summary>
          <div className="debug-panel-body">
            <div className="actions debug-action-row">
              <button
              type="button"
              className="ghost-button"
              onClick={handleAnalyzeDebugClick}
              disabled={!canGenerate || matchLoading || generateLoading || refineLoading}
            >
                {matchLoading ? "Przygotowywanie..." : "Uruchom matching debug"}
              </button>
            </div>

            <p className="helper-text">
              matching_handoff:{" "}
              {describeResumeMatchingHandoff(
                developerDebugState.lastResumeMatchingHandoff,
                developerDebugState.lastResumeRequestBodyUnavailableReason,
              )}
            </p>

            <RawJsonPanel summary="Raw JSON matching" value={matchingDebugEnvelope} />

            <RawJsonPanel
              summary="Raw JSON resume"
              value={resumeDebugEnvelope}
              helperText={developerDebugState.lastResumeRequestBodyUnavailableReason}
            />
          </div>
        </details>

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
                  className={`history-item${
                    (matchSource?.type === "snapshot" || matchSource?.type === "saved") && matchSource?.id === item.id
                      ? " active"
                      : ""
                  }`}
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

        <div className="section-header" style={{ marginTop: "20px" }}>
          <div>
            <h3>Zapisane drafty CV</h3>
            <p className="section-copy">
              Wroc do wczesniej wygenerowanych draftow bez ponownego uruchamiania generacji.
            </p>
          </div>
        </div>

        {resumeDraftHistoryError ? <div className="message error">{resumeDraftHistoryError}</div> : null}

        {resumeDraftHistoryLoading ? (
          <p className="placeholder">Ladowanie zapisanych draftow...</p>
        ) : !selectedProfileId || !selectedJobId ? (
          <p className="placeholder">Wybierz profil i oferte, aby zobaczyc zapisane drafty.</p>
        ) : resumeDraftHistory.length > 0 ? (
          <div className="history-list-wrapper">
            <div className="history-list">
              {resumeDraftHistory.map((item) => (
                <div
                  key={item.id}
                  className={`history-item${currentResumeDraftRecordId === item.id ? " active" : ""}`}
                >
                  <div>
                    <span className="history-title">Draft #{item.id}</span>
                    <span className="history-company">
                      {item.target_job_title || "Brak tytulu"} · {item.target_company_name || "Brak firmy"}
                    </span>
                    <span className="history-meta">
                      {item.has_refined_version ? "AI-refined dostepny" : "Tylko bazowy draft"}
                    </span>
                    <span className="history-meta history-meta-secondary">
                      Zapisano: {formatSavedAt(item.saved_at)} · Aktualizacja: {formatSavedAt(item.updated_at)}
                    </span>
                  </div>
                  <div className="history-item-actions">
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() => void handleSavedResumeDraftOpen(item.id)}
                      disabled={resumeDraftLoadingId === item.id}
                    >
                      {resumeDraftLoadingId === item.id ? "Ladowanie..." : "Otworz"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="placeholder">Brak zapisanych draftow dla tej pary.</p>
        )}

        <div className="resume-info-note" role="note" aria-label="Informacja o liscie motywacyjnym">
          Na tym etapie dostepne jest generowanie CV. List motywacyjny zostanie dodany pozniej.
        </div>

      </section>

      <div className="document-results-grid">
        <section className="section-card scroll-panel">
          <div className="section-header">
            <div>
              <h3>Podglad CV</h3>
              <p className="section-copy">
                {hasRefinedResumeDraft && resumeDraftView === "refined"
                  ? "Czytelny podglad draftu po opcjonalnym AI refinement."
                  : "Czytelny podglad wygenerowanego draftu CV."}
              </p>
              {currentResumeDraftRecordId ? (
                <p className="helper-text">
                  Aktywny zapisany draft #{currentResumeDraftRecordId}
                  {resumeArtifacts?.resume_draft_saved_at ? ` · zapisano ${formatSavedAt(resumeArtifacts.resume_draft_saved_at)}` : ""}
                </p>
              ) : null}
            </div>
          </div>

          {hasRefinedResumeDraft ? (
            <div className="resume-version-toolbar">
              <div>
                <h4>Wersja podgladu</h4>
                <p className="section-copy">
                  {resumeDraftView === "refined"
                    ? "Ogladasz AI poprawiona wersje. Bazowy draft nadal jest dostepny obok."
                    : "Ogladasz bazowy draft. AI poprawiona wersja jest dostepna jednym kliknieciem."}
                </p>
              </div>
              <div className="resume-version-switcher" role="group" aria-label="Wersja podgladu draftu">
                <button
                  type="button"
                  className={`resume-version-button${resumeDraftView === "base" ? " active" : ""}`}
                  onClick={() => setResumeDraftView("base")}
                >
                  Bazowy draft
                </button>
                <button
                  type="button"
                  className={`resume-version-button${resumeDraftView === "refined" ? " active" : ""}`}
                  onClick={() => setResumeDraftView("refined")}
                >
                  AI poprawiony draft
                </button>
              </div>
            </div>
          ) : null}

          <div className="scroll-panel-body document-panel-body">
            {displayedResumeDraft ? (
              <ResumeDraftDetails resumeDraft={displayedResumeDraft} />
            ) : (
              <p className="placeholder">
                Wybierz zapisany profil i oferte, a potem wygeneruj nowy draft CV albo otworz zapisany draft dla tej pary.
              </p>
            )}
          </div>

          {resumeArtifacts?.resume_draft ? (
            <details className="resume-refinement-panel">
              <summary className="resume-refinement-summary">
                <div>
                  <strong>Popraw draft CV (AI)</strong>
                  <p>
                    Opcjonalnie dopracuj gotowy draft bez generowania CV od nowa. Bazowa wersja zawsze pozostaje do dyspozycji.
                  </p>
                </div>
                <span className="section-count-badge">{refinementStatusLabel}</span>
              </summary>

              <div className="resume-refinement-body">
                <p className="helper-text">
                  Wpisz kilka prostych wskazowek, a AI przygotuje dodatkowa wersje draftu na bazie juz wygenerowanego CV.
                </p>

                {refinementDirty && hasRefinedResumeDraft ? (
                  <div className="message info">
                    Zmieniono wskazowki. Ostatnia AI poprawiona wersja nadal jest widoczna, ale kliknij przycisk ponownie, aby ja odswiezyc.
                  </div>
                ) : null}

                <div className="form-grid resume-form-grid">
                  <TagListInput
                    label="Co warto mocniej wybrzmiec"
                    helperText="Dodaj terminy, ktore warto lepiej wyeksponowac, o ile sa juz uczciwie pokryte w bazowym drafcie."
                    emptyText="Brak dodatkowych terminow do mocniejszego podkreslenia."
                    items={refinementGuidance.must_include_terms}
                    onChange={(items) => handleRefinementGuidanceListChange("must_include_terms", items)}
                    placeholder="np. PLC, embedded, commissioning"
                  />
                  <TagListInput
                    label="Czego nie promowac"
                    helperText="Dodaj obszary, ktore sa prawdziwe, ale nie powinny byc osia tej konkretnej wersji CV."
                    emptyText="Brak terminow do zdeemfatyzowania."
                    items={refinementGuidance.avoid_or_deemphasize_terms}
                    onChange={(items) => handleRefinementGuidanceListChange("avoid_or_deemphasize_terms", items)}
                    placeholder="np. SAP, support, QA"
                  />
                  <TagListInput
                    label="Jakich sformulowan unikac"
                    helperText="Te frazy nie powinny pojawic sie w AI poprawionej wersji draftu."
                    emptyText="Brak zakazanych sformulowan."
                    items={refinementGuidance.forbidden_claims_or_phrases}
                    onChange={(items) => handleRefinementGuidanceListChange("forbidden_claims_or_phrases", items)}
                    placeholder="np. expert, world-class"
                  />
                  <TagListInput
                    label="Jakie skille maja zostac w sekcji skills"
                    helperText="Jesli wpiszesz tu konkretne skille, AI ograniczy finalna sekcje skills do tej listy."
                    emptyText="Brak ograniczen dla sekcji skills."
                    items={refinementGuidance.skills_allowlist}
                    onChange={(items) => handleRefinementGuidanceListChange("skills_allowlist", items)}
                    placeholder="np. PLC, Python, TIA Portal"
                  />
                  <label className="field section-wide-field">
                    <span>Dodatkowe wskazowki</span>
                    <p className="helper-text">
                      Krotko opisz, jaki kierunek poprawek ma przyjac AI, np. bardziej zwiezle, bardziej technicznie albo mocniej pod embedded automation.
                    </p>
                    <textarea
                      className="form-textarea compact-textarea"
                      value={refinementGuidance.additional_instructions}
                      onChange={(event) => handleAdditionalInstructionsChange(event.target.value)}
                      placeholder="np. Skroc summary, zostaw bardziej techniczny ton i skup sie na automatyce przemyslowej."
                      disabled={generateLoading || matchLoading || refineLoading}
                    />
                  </label>
                </div>

                <div className="actions resume-refinement-actions">
                  <button
                    type="button"
                    className="primary-button"
                    onClick={handleRefineClick}
                    disabled={generateLoading || matchLoading || refineLoading || !hasRefinementGuidance}
                  >
                    {refineLoading ? "Przygotowywanie AI poprawki..." : "Popraw draft CV (AI)"}
                  </button>
                </div>

                {!hasRefinementGuidance ? (
                  <p className="helper-text">
                    Dodaj przynajmniej jedna wskazowke, aby uruchomic opcjonalny AI refinement draftu.
                  </p>
                ) : null}
              </div>
            </details>
          ) : null}
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
              <>
                {hasRefinedResumeDraft ? (
                  <p className="helper-text">
                    ChangeReport dotyczy bazowego draftu z /resume/generate. Refinement AI nie przelicza tego raportu.
                  </p>
                ) : null}
                <ChangeReportDetails
                  changeReport={resumeArtifacts.change_report}
                  matchResult={activeMatchResult}
                  matchSource={matchSource}
                  generationMode={resumeArtifacts.generation_mode}
                  fallbackReason={resumeArtifacts.fallback_reason}
                  generationNotes={resumeArtifacts.generation_notes}
                />
              </>
            ) : (
              <p className="placeholder">
                Po wygenerowaniu lub otwarciu draftu tutaj pojawi sie raport zmian i pokrycia wymaganych.
              </p>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
