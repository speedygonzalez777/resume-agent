import DocumentWorkflowRow from "../document/DocumentWorkflowRow";

function buildProfileLabel(profileDetail) {
  const profile = profileDetail?.payload?.personal_info;
  if (!profile) {
    return "Brak profilu";
  }
  return profile.full_name || profile.email || "Wybrany profil";
}

function buildJobLabel(jobDetail) {
  const job = jobDetail?.payload;
  if (!job) {
    return "Brak oferty";
  }
  return job.title || "Wybrana oferta";
}

/**
 * @param {{
 *   mode?: "active" | "completed" | "locked" | "available" | "editing",
 *   expanded?: boolean,
 *   profiles: object[],
 *   jobs: object[],
 *   selectedProfileId: number | null,
 *   selectedProfileDetail: object | null,
 *   selectedProfileLoading: boolean,
 *   selectedJobId: number | null,
 *   selectedJobDetail: object | null,
 *   selectedJobLoading: boolean,
 *   busy: boolean,
 *   onProfileChange: (profileId: number | null) => void,
 *   onJobChange: (jobId: number | null) => void,
 *   onRefresh: () => void,
 *   onExpand: () => void,
 *   onContinue: () => void,
 *   formatSavedAt: (savedAt: string) => string,
 * }} props
 * @returns {JSX.Element}
 */
export default function ProfileJobSelectionStep({
  mode = "active",
  expanded = false,
  profiles,
  jobs,
  selectedProfileId,
  selectedProfileDetail,
  selectedProfileLoading,
  selectedJobId,
  selectedJobDetail,
  selectedJobLoading,
  busy,
  onProfileChange,
  onJobChange,
  onRefresh,
  onExpand,
  onContinue,
  formatSavedAt,
}) {
  const pairReady = Boolean(selectedProfileId && selectedJobId);
  const selectedProfile = selectedProfileDetail?.payload?.personal_info ?? null;
  const selectedJob = selectedJobDetail?.payload ?? null;

  const summary = pairReady ? (
    <div className="document-row-summary-list">
      <span>{buildProfileLabel(selectedProfileDetail)}</span>
      <span>{buildJobLabel(selectedJobDetail)}</span>
      <span>{selectedJob?.company_name || "Brak firmy"}</span>
    </div>
  ) : null;

  const actions = pairReady && !expanded ? (
    <button type="button" className="ghost-button document-row-action-button" onClick={onExpand}>
      Zmień
    </button>
  ) : null;

  return (
    <DocumentWorkflowRow
      status={mode}
      expanded={expanded}
      stepLabel="Krok 1"
      title="Profil i oferta"
      summary={summary}
      note={!pairReady ? "Wybierz zapisany profil i ofertę." : null}
      actions={actions}
      body={(
        <div className="document-workflow-form">
          <div className="form-grid resume-form-grid">
            <label className="field">
              <span>Zapisany profil</span>
              <select
                className="select-input"
                value={selectedProfileId ?? ""}
                onChange={(event) => onProfileChange(Number.parseInt(event.target.value, 10) || null)}
                disabled={busy}
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
                onChange={(event) => onJobChange(Number.parseInt(event.target.value, 10) || null)}
                disabled={busy}
              >
                <option value="">Wybierz ofertę</option>
                {jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.title} - {job.company_name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {(selectedProfileId || selectedJobId) ? (
            <div className="resume-selection-preview-grid">
              <article className="resume-selection-preview-card">
                <span className="metric-label">Profil</span>
                {selectedProfileLoading ? (
                  <p className="helper-text">Ładowanie profilu...</p>
                ) : selectedProfile ? (
                  <>
                    <strong>{selectedProfile.full_name || "Brak imienia i nazwiska"}</strong>
                    <p className="helper-text">{selectedProfile.email || "Brak e-maila"}</p>
                    <p className="helper-text">
                      {selectedProfile.location || "Brak lokalizacji"}
                      {selectedProfileDetail?.saved_at ? ` · zapisano ${formatSavedAt(selectedProfileDetail.saved_at)}` : ""}
                    </p>
                  </>
                ) : (
                  <p className="helper-text">Wybierz zapisany profil.</p>
                )}
              </article>

              <article className="resume-selection-preview-card">
                <span className="metric-label">Oferta</span>
                {selectedJobLoading ? (
                  <p className="helper-text">Ładowanie oferty...</p>
                ) : selectedJob ? (
                  <>
                    <strong>{selectedJob.title || "Brak tytułu"}</strong>
                    <p className="helper-text">{selectedJob.company_name || "Brak firmy"}</p>
                    <p className="helper-text">
                      {selectedJob.location || "Brak lokalizacji"}
                      {selectedJobDetail?.saved_at ? ` · zapisano ${formatSavedAt(selectedJobDetail.saved_at)}` : ""}
                    </p>
                  </>
                ) : (
                  <p className="helper-text">Wybierz zapisaną ofertę.</p>
                )}
              </article>
            </div>
          ) : null}

          <div className="document-row-toolbar">
            <button
              type="button"
              className="ghost-button document-row-action-button"
              onClick={onRefresh}
              disabled={busy}
            >
              Odśwież listy
            </button>
            {pairReady ? (
              <button
                type="button"
                className="primary-button document-row-action-button"
                onClick={onContinue}
                disabled={busy}
              >
                Przejdź do dopasowania
              </button>
            ) : null}
          </div>
        </div>
      )}
    />
  );
}
