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
import DocumentWorkspace from "./components/document/DocumentWorkspace";
import DraftGenerationStep from "./components/resume/DraftGenerationStep";
import DraftReviewStep from "./components/resume/DraftReviewStep";
import MatchStep from "./components/resume/MatchStep";
import ProfileJobSelectionStep from "./components/resume/ProfileJobSelectionStep";
import ResumeContextPanel from "./components/resume/ResumeContextPanel";
import ResumeDebugPanel from "./components/resume/ResumeDebugPanel";

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
 * Convert refinement errors into a calm, user-facing message that keeps the base draft safe.
 *
 * @param {unknown} error Error-like value thrown by the refinement request.
 * @returns {string} Friendly refinement error message.
 */
function getRefinementErrorMessage(error) {
  const message = getErrorMessage(error);

  if (message.includes("AI CV refinement is unavailable")) {
    return "Nie udało się uruchomić poprawy AI. Bazowy draft nadal jest dostępny.";
  }

  return "Nie udało się przygotować poprawionej wersji CV. Bazowy draft nadal jest dostępny.";
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
    return `Używany jest świeży wynik dopasowania zapisany jako wynik #${matchSource.id}.`;
  }
  if (matchSource?.type === "session_unsaved") {
    return "Używany jest świeży wynik dopasowania z tej sesji, ale nie został zapisany w historii.";
  }
  return "Brak aktywnego wyniku dla tej pary. Sprawdź dopasowanie albo wygeneruj draft CV.";
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

function getResumeWorkflowStage({ hasPairSelected, activeMatchResult, hasDraftArtifacts }) {
  if (hasDraftArtifacts) {
    return "review";
  }
  if (activeMatchResult) {
    return "draft";
  }
  if (hasPairSelected) {
    return "match";
  }
  return "selection";
}

function describeResumeGenerationMode(generationMode) {
  if (generationMode === "openai_structured") {
    return "Generacja AI";
  }
  if (generationMode === "rule_based_fallback") {
    return "Tryb zapasowy";
  }
  return "Brak danych";
}

function buildMatchSourceMeta(matchSource) {
  if (matchSource?.type === "session_unsaved") {
    return "Aktywny wynik pochodzi z bieżącej sesji i nie zastępuje historii zapisanej wcześniej.";
  }
  if (matchSource?.type === "saved") {
    return "Aktywny wynik został załadowany razem z zapisanym draftem.";
  }
  if (matchSource?.type === "snapshot") {
    return "Aktywny wynik został świeżo przeliczony i zapisany w historii.";
  }
  return null;
}

/**
 * Render the tab used for generating a structured CV draft from saved inputs.
 *
 * @returns {JSX.Element} Resume-generation tab content.
 */
export default function ResumeTab({ jobListRefreshVersion = 0, onGoToDocument = null }) {
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
  const [expandedWorkflowStep, setExpandedWorkflowStep] = useState(null);
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
    setExpandedWorkflowStep(profileId && selectedJobId ? "match" : "selection");

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
    setExpandedWorkflowStep(selectedProfileId && jobId ? "match" : "selection");

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
            `Draft został otwarty, ale nie udało się załadować powiązanego wyniku dopasowania: ${getErrorMessage(error)}`,
          );
        }
      } else {
        clearMatchState();
      }

      setMessage({
        type: "info",
        text: storedDraft.has_refined_version
          ? "Otworzono zapisany draft CV z dostępną poprawą AI."
          : "Otworzono zapisany draft CV.",
      });
      setExpandedWorkflowStep("review");
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
          `Dopasowanie zostało przeliczone, ale wynik nie został zapisany w historii: ${getErrorMessage(error)}`,
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
          ? "Dopasowanie zostało przeliczone od nowa i zapisane w historii."
          : "Dopasowanie zostało przeliczone od nowa, ale wynik nie został zapisany w historii.",
      });
      setExpandedWorkflowStep("draft");
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
          ? "Debug dopasowania został policzony i zapisany w historii."
          : "Debug dopasowania został policzony, ale wynik nie został zapisany w historii.",
      });
      setExpandedWorkflowStep("draft");
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
              text: `Draft CV został wygenerowany, ale nie został zapisany lokalnie: ${payload.persistence_warning}`,
            }
          : {
              type: "success",
              text: payload.resume_draft_record_id
                ? `Draft CV został wygenerowany i zapisany jako draft #${payload.resume_draft_record_id}.`
                : "Draft CV został wygenerowany.",
            },
      );
      setExpandedWorkflowStep("review");
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
              text: `AI przygotowało poprawioną wersję draftu, ale nie udało się zapisać tej aktualizacji: ${payload.persistence_warning}`,
            }
          : {
              type: "success",
              text: "AI przygotowało poprawioną wersję draftu. Bazowa wersja nadal jest dostępna jednym kliknięciem.",
            },
      );
      setExpandedWorkflowStep("review");
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
    ? "Wskazówki zmienione"
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
  const matchSource = activeMatchSession.source;
  const selectedHistoryPreview = historyPreviewId ? historyPreviewCache[historyPreviewId] ?? null : null;
  const selectedHistoryPreviewMatchResult = selectedHistoryPreview?.payload ?? null;
  const selectedHistoryPreviewStats = summarizeRequirementStatuses(selectedHistoryPreviewMatchResult);
  const selectedHistoryStrengthsPreview = buildPreviewList(selectedHistoryPreviewMatchResult?.strengths);
  const selectedHistoryGapsPreview = buildPreviewList(selectedHistoryPreviewMatchResult?.gaps);
  const activeMatchStrengthsPreview = buildPreviewList(activeMatchResult?.strengths);
  const activeMatchGapsPreview = buildPreviewList(activeMatchResult?.gaps);
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
  const hasPairSelected = Boolean(selectedProfileId && selectedJobId);
  const hasDraftArtifacts = Boolean(resumeArtifacts?.resume_draft);
  const activeMatchSourceId =
    matchSource?.type === "snapshot" || matchSource?.type === "saved"
      ? matchSource.id ?? null
      : null;
  const workflowStage = getResumeWorkflowStage({
    hasPairSelected,
    activeMatchResult,
    hasDraftArtifacts,
  });
  const draftGenerationModeLabel = describeResumeGenerationMode(resumeArtifacts?.generation_mode);
  const matchSourceLabel = describeMatchSource(matchSource);
  const matchSourceMeta = buildMatchSourceMeta(matchSource);
  const flowIsLoading =
    lookupLoading ||
    selectedProfileLoading ||
    selectedJobLoading ||
    matchLoading ||
    generateLoading ||
    refineLoading ||
    Boolean(resumeDraftLoadingId);
  const defaultExpandedStep =
    workflowStage === "selection"
      ? "selection"
      : workflowStage === "match"
        ? "match"
        : workflowStage === "draft"
          ? "draft"
          : "review";
  const canExpandMatch = hasPairSelected;
  const canExpandDraft = Boolean(activeMatchResult || hasDraftArtifacts);
  const canExpandReview = hasDraftArtifacts;
  const effectiveExpandedStep = expandedWorkflowStep === "selection"
    ? "selection"
    : expandedWorkflowStep === "match" && canExpandMatch
      ? "match"
      : expandedWorkflowStep === "draft" && canExpandDraft
        ? "draft"
        : expandedWorkflowStep === "review" && canExpandReview
          ? "review"
          : expandedWorkflowStep === "none"
            ? null
          : defaultExpandedStep;
  const selectionExpanded = effectiveExpandedStep === "selection";
  const matchExpanded = effectiveExpandedStep === "match";
  const draftExpanded = effectiveExpandedStep === "draft";
  const reviewExpanded = effectiveExpandedStep === "review";
  const selectionStepMode = hasPairSelected
    ? selectionExpanded
      ? "editing"
      : "completed"
    : "active";
  const matchStepMode = !hasPairSelected
    ? "locked"
    : matchExpanded
      ? activeMatchResult
        ? "editing"
        : "active"
      : activeMatchResult
        ? "completed"
        : "available";
  const draftStepMode = !hasDraftArtifacts && !activeMatchResult
    ? "locked"
    : draftExpanded
      ? hasDraftArtifacts
        ? "editing"
        : "active"
      : hasDraftArtifacts
        ? "completed"
        : "available";
  const reviewStepMode = !hasDraftArtifacts
    ? "locked"
    : reviewExpanded
      ? "active"
      : "completed";

  return (
    <section className="tab-content resume-tab-content">
      <div className="section-header tab-header">
        <div>
          <h2>Dopasowanie i draft</h2>
          <p className="section-copy">
            Sprawdź dopasowanie wybranego profilu do oferty, a następnie wygeneruj draft CV.
          </p>
        </div>
      </div>

      {message ? <div className={`message ${message.type}`}>{message.text}</div> : null}
      {lookupError ? <div className="message error">{lookupError}</div> : null}
      <DocumentWorkspace
        left={(
          <>
            <section className="document-workflow-panel">
              <div className="document-workflow-list">
                <ProfileJobSelectionStep
                  mode={selectionExpanded ? (hasPairSelected ? "editing" : "active") : selectionStepMode}
                  expanded={selectionExpanded}
                  profiles={profiles}
                  jobs={jobs}
                  selectedProfileId={selectedProfileId}
                  selectedProfileDetail={selectedProfileDetail}
                  selectedProfileLoading={selectedProfileLoading}
                  selectedJobId={selectedJobId}
                  selectedJobDetail={selectedJobDetail}
                  selectedJobLoading={selectedJobLoading}
                  busy={flowIsLoading}
                  onProfileChange={(profileId) => void loadSelectedProfile(profileId)}
                  onJobChange={(jobId) => void loadSelectedJob(jobId)}
                  onRefresh={() => void refreshSelectorData()}
                  onExpand={() => setExpandedWorkflowStep("selection")}
                  onContinue={() => setExpandedWorkflowStep("match")}
                  formatSavedAt={formatSavedAt}
                />

                <MatchStep
                  mode={matchStepMode}
                  expanded={matchExpanded}
                  activeMatchResult={activeMatchResult}
                  matchSourceLabel={matchSourceLabel}
                  sourceMeta={
                    matchSource?.savedAt
                      ? `${matchSourceLabel} · zapisano ${formatSavedAt(matchSource.savedAt)}`
                      : matchSourceMeta ?? matchSourceLabel
                  }
                  strengthsPreview={activeMatchStrengthsPreview}
                  gapsPreview={activeMatchGapsPreview}
                  loading={matchLoading}
                  busy={!canGenerate || matchLoading || generateLoading || refineLoading}
                  errorText={matchLookupError}
                  onAnalyze={() => void handleAnalyzeClick()}
                  onExpand={() => setExpandedWorkflowStep("match")}
                  onContinue={() => setExpandedWorkflowStep("draft")}
                />

                <DraftGenerationStep
                  mode={draftStepMode}
                  expanded={draftExpanded}
                  activeMatchResult={activeMatchResult}
                  resumeArtifacts={resumeArtifacts}
                  hasRefinedResumeDraft={hasRefinedResumeDraft}
                  currentResumeDraftRecordId={currentResumeDraftRecordId}
                  busy={!canGenerate || matchLoading || generateLoading || refineLoading}
                  loading={generateLoading}
                  generationModeLabel={draftGenerationModeLabel}
                  savedAt={resumeArtifacts?.resume_draft_saved_at ? formatSavedAt(resumeArtifacts.resume_draft_saved_at) : null}
                  onGenerate={() => void handleGenerateClick()}
                  onExpand={() => setExpandedWorkflowStep("draft")}
                  onOpenReview={() => setExpandedWorkflowStep("review")}
                />

                <DraftReviewStep
                  mode={reviewStepMode}
                  expanded={reviewExpanded}
                  resumeArtifacts={resumeArtifacts}
                  displayedResumeDraft={displayedResumeDraft}
                  hasRefinedResumeDraft={hasRefinedResumeDraft}
                  resumeDraftView={resumeDraftView}
                  onResumeDraftViewChange={setResumeDraftView}
                  currentResumeDraftRecordId={currentResumeDraftRecordId}
                  formatSavedAt={formatSavedAt}
                  activeMatchResult={activeMatchResult}
                  matchSource={matchSource}
                  refinementGuidance={refinementGuidance}
                  refineLoading={refineLoading}
                  flowIsLoading={generateLoading || matchLoading || refineLoading}
                  refinementDirty={refinementDirty}
                  refinementStatusLabel={refinementStatusLabel}
                  hasRefinementGuidance={hasRefinementGuidance}
                  onRefineClick={() => void handleRefineClick()}
                  onRefinementGuidanceListChange={handleRefinementGuidanceListChange}
                  onAdditionalInstructionsChange={handleAdditionalInstructionsChange}
                  onExpand={() => setExpandedWorkflowStep("review")}
                  onCollapse={() => setExpandedWorkflowStep("none")}
                />
              </div>
            </section>

            <ResumeDebugPanel
              canGenerate={canGenerate}
              busy={matchLoading || generateLoading || refineLoading}
              onAnalyzeDebug={() => void handleAnalyzeDebugClick()}
              lastResumeMatchingHandoff={developerDebugState.lastResumeMatchingHandoff}
              lastResumeRequestBodyUnavailableReason={developerDebugState.lastResumeRequestBodyUnavailableReason}
              matchingDebugEnvelope={matchingDebugEnvelope}
              resumeDebugEnvelope={resumeDebugEnvelope}
            />

            <div className="resume-inline-note" role="note" aria-label="Informacja o liscie motywacyjnym">
              Na tym etapie dostępne jest generowanie CV. List motywacyjny zostanie dodany później.
            </div>
          </>
        )}
        right={(
          <ResumeContextPanel
            selectedProfileDetail={selectedProfileDetail}
            selectedProfileLoading={selectedProfileLoading}
            selectedJobDetail={selectedJobDetail}
            selectedJobLoading={selectedJobLoading}
            hasPairSelected={hasPairSelected}
            activeMatchResult={activeMatchResult}
            activeMatchSourceLabel={matchSourceLabel}
            activeMatchSourceId={activeMatchSourceId}
            matchSourceMeta={matchSourceMeta}
            selectedHistoryPreview={selectedHistoryPreview}
            selectedHistoryPreviewMatchResult={selectedHistoryPreviewMatchResult}
            selectedHistoryPreviewStats={selectedHistoryPreviewStats}
            selectedHistoryStrengthsPreview={selectedHistoryStrengthsPreview}
            selectedHistoryGapsPreview={selectedHistoryGapsPreview}
            matchHistory={matchHistory}
            historyLoading={historyLoading}
            historyError={historyError}
            historyPreviewId={historyPreviewId}
            historyPreviewLoadingId={historyPreviewLoadingId}
            onHistoryPreviewToggle={(id) => void handleHistoryPreviewToggle(id)}
            resumeDraftHistory={resumeDraftHistory}
            resumeDraftHistoryLoading={resumeDraftHistoryLoading}
            resumeDraftHistoryError={resumeDraftHistoryError}
            currentResumeDraftRecordId={currentResumeDraftRecordId}
            resumeDraftLoadingId={resumeDraftLoadingId}
            onSavedResumeDraftOpen={(id) => void handleSavedResumeDraftOpen(id)}
            canGoToDocument={hasDraftArtifacts}
            onGoToDocument={onGoToDocument}
            formatSavedAt={formatSavedAt}
          />
        )}
      />
    </section>
  );
}
