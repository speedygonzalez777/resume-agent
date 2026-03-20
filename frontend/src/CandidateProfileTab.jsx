/**
 * Candidate-profile tab with a sectioned form, profile history and readable profile details.
 */

import { useEffect, useState } from "react";

import {
  deleteCandidateProfile,
  getCandidateProfileDetail,
  listCandidateProfiles,
  saveCandidateProfile,
  updateCandidateProfile,
} from "./api";
import CandidateProfileDetails from "./CandidateProfileDetails";
import CandidateProfileForm, {
  buildCandidateProfilePayload,
  createCandidateProfileFormStateFromProfile,
  createEmptyCandidateProfileFormState,
} from "./CandidateProfileForm";

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
 * Build a short human-readable label for the profile currently being edited.
 *
 * @param {{id: number, full_name: string, email: string} | null} profile Stored profile metadata.
 * @returns {string} Readable editing label.
 */
function buildEditingProfileLabel(profile) {
  if (!profile) {
    return "";
  }
  return profile.email ? `${profile.full_name} (${profile.email})` : profile.full_name;
}

/**
 * Render the profile-management tab used for storing and selecting CandidateProfile records.
 *
 * @returns {JSX.Element} Candidate-profile tab content.
 */
export default function CandidateProfileTab() {
  const [formValue, setFormValue] = useState(createEmptyCandidateProfileFormState());
  const [message, setMessage] = useState(null);
  const [saveLoading, setSaveLoading] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [lastSavedProfileId, setLastSavedProfileId] = useState(null);

  const [profileHistory, setProfileHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);

  const [selectedProfileId, setSelectedProfileId] = useState(null);
  const [selectedProfileDetail, setSelectedProfileDetail] = useState(null);
  const [selectedProfileLoading, setSelectedProfileLoading] = useState(false);
  const [selectedProfileError, setSelectedProfileError] = useState(null);
  const [deletingProfileId, setDeletingProfileId] = useState(null);
  const [editingProfile, setEditingProfile] = useState(null);

  const isEditMode = editingProfile !== null;

  /**
   * Refresh the stored candidate profile list from the backend.
   *
   * @returns {Promise<object[] | null>} Loaded list items or null when the refresh fails.
   */
  async function refreshProfileHistory() {
    setHistoryLoading(true);
    setHistoryError(null);

    try {
      const payload = await listCandidateProfiles();
      setProfileHistory(payload);
      return payload;
    } catch (error) {
      setHistoryError(getErrorMessage(error));
      return null;
    } finally {
      setHistoryLoading(false);
    }
  }

  /**
   * Load the full detail of one stored candidate profile selected from history.
   *
   * @param {number} profileId Database identifier of the stored candidate profile.
   * @returns {Promise<void>} Promise resolved after the detail panel state is updated.
   */
  async function selectStoredProfile(profileId) {
    setSelectedProfileId(profileId);
    setSelectedProfileDetail(null);
    setSelectedProfileError(null);
    setSelectedProfileLoading(true);

    try {
      const payload = await getCandidateProfileDetail(profileId);
      setSelectedProfileDetail(payload);
    } catch (error) {
      setSelectedProfileError(getErrorMessage(error));
    } finally {
      setSelectedProfileLoading(false);
    }
  }

  useEffect(() => {
    void refreshProfileHistory();
  }, []);

  /**
   * Clear the currently selected profile detail panel.
   *
   * @returns {void} No return value.
   */
  function clearSelectedProfile() {
    setSelectedProfileId(null);
    setSelectedProfileDetail(null);
    setSelectedProfileError(null);
  }

  /**
   * Restore the form to the default new-profile mode.
   *
   * @returns {void} No return value.
   */
  function resetFormToCreateMode() {
    setFormValue(createEmptyCandidateProfileFormState());
    setEditingProfile(null);
    setHasUnsavedChanges(false);
    setLastSavedProfileId(null);
  }

  /**
   * Update the controlled profile form and mark the draft as unsaved.
   *
   * @param {object} nextValue Updated form state.
   * @returns {void} No return value.
   */
  function handleFormChange(nextValue) {
    setFormValue(nextValue);
    setHasUnsavedChanges(true);

    if (message !== null) {
      setMessage(null);
    }
  }

  /**
   * Load one stored profile into the form and switch the UI into edit mode.
   *
   * @param {number} profileId Database identifier of the selected stored profile.
   * @returns {Promise<void>} Promise resolved after the edit mode is ready.
   */
  async function handleEditProfileClick(profileId) {
    setMessage(null);
    setSelectedProfileId(profileId);
    setSelectedProfileError(null);
    setSelectedProfileLoading(true);

    try {
      const storedProfile = await getCandidateProfileDetail(profileId);
      setSelectedProfileDetail(storedProfile);
      setFormValue(createCandidateProfileFormStateFromProfile(storedProfile.payload));
      setEditingProfile({
        id: storedProfile.id,
        full_name: storedProfile.full_name,
        email: storedProfile.email,
      });
      setHasUnsavedChanges(false);
      setLastSavedProfileId(null);
      setMessage({
        type: "info",
        text: `Edytujesz istniejacy profil ID ${storedProfile.id}. Zapis zaktualizuje ten sam rekord.`,
      });
    } catch (error) {
      setSelectedProfileError(getErrorMessage(error));
      setMessage({ type: "error", text: `Nie udalo sie wlaczyc edycji profilu. ${getErrorMessage(error)}` });
    } finally {
      setSelectedProfileLoading(false);
    }
  }

  /**
   * Exit edit mode and return the form to creating a new profile.
   *
   * @returns {void} No return value.
   */
  function handleCancelEditClick() {
    resetFormToCreateMode();
    setMessage({
      type: "info",
      text: "Edycja zostala anulowana. Formularz wrocil do trybu tworzenia nowego profilu.",
    });
  }

  /**
   * Save the current form as a CandidateProfile and refresh the profile history.
   *
   * @returns {Promise<void>} Promise resolved after save-related state is updated.
   */
  async function handleSaveProfileClick() {
    setSaveLoading(true);
    setMessage(null);

    try {
      const payload = buildCandidateProfilePayload(formValue);
      const storedProfile = editingProfile
        ? await updateCandidateProfile(editingProfile.id, payload)
        : await saveCandidateProfile(payload);

      if (editingProfile) {
        setEditingProfile({
          id: storedProfile.id,
          full_name: storedProfile.full_name,
          email: storedProfile.email,
        });
        setFormValue(createCandidateProfileFormStateFromProfile(storedProfile.payload));
      }

      await refreshProfileHistory();
      await selectStoredProfile(storedProfile.id);
      setHasUnsavedChanges(false);
      setLastSavedProfileId(storedProfile.id);
      setMessage({
        type: "success",
        text: editingProfile
          ? `Profil ID ${storedProfile.id} zostal zaktualizowany. Historia i szczegoly pokazuja juz nowe dane.`
          : `Profil zostal zapisany. Wszystkie zmiany w formularzu sa juz zapisane. ID: ${storedProfile.id}.`,
      });
    } catch (error) {
      setMessage({
        type: "error",
        text: editingProfile
          ? `Nie udalo sie zaktualizowac profilu. ${getErrorMessage(error)}`
          : `Nie udalo sie zapisac profilu. ${getErrorMessage(error)}`,
      });
    } finally {
      setSaveLoading(false);
    }
  }

  /**
   * Delete one stored profile and keep the history and selection state consistent.
   *
   * @param {number} profileId Database identifier of the profile selected for deletion.
   * @returns {Promise<void>} Promise resolved after history and detail state are refreshed.
   */
  async function handleDeleteProfileClick(profileId) {
    const profileToDelete = profileHistory.find((profile) => profile.id === profileId);
    const label = profileToDelete?.full_name || `profil ${profileId}`;

    if (!window.confirm(`Czy na pewno usunac ${label}?`)) {
      return;
    }

    setDeletingProfileId(profileId);
    setMessage(null);

    try {
      await deleteCandidateProfile(profileId);
      const refreshedProfiles = await refreshProfileHistory();
      const remainingProfiles = Array.isArray(refreshedProfiles) ? refreshedProfiles : [];

      if (editingProfile?.id === profileId) {
        resetFormToCreateMode();
      }

      if (selectedProfileId === profileId) {
        if (remainingProfiles.length > 0) {
          await selectStoredProfile(remainingProfiles[0].id);
        } else {
          clearSelectedProfile();
        }
      }

      setMessage({
        type: "success",
        text: "Profil zostal usuniety z historii.",
      });
    } catch (error) {
      setMessage({ type: "error", text: getErrorMessage(error) });
    } finally {
      setDeletingProfileId(null);
    }
  }

  return (
    <section className="tab-content">
      <div className="section-header tab-header">
        <div>
          <h2>Profil kandydata</h2>
          <p className="section-copy">Uzupelnij profil kandydata i zapisz go do dalszej analizy.</p>
        </div>
      </div>

      {message ? <div className={`message ${message.type}`}>{message.text}</div> : null}

      <div className="workspace-grid">
        <section className="section-card section-wide">
          <CandidateProfileForm
            formValue={formValue}
            onChange={handleFormChange}
            onSave={handleSaveProfileClick}
            saveLoading={saveLoading}
            hasUnsavedChanges={hasUnsavedChanges}
            lastSavedProfileId={lastSavedProfileId}
            isEditMode={isEditMode}
            editingProfileId={editingProfile?.id ?? null}
            editingProfileLabel={buildEditingProfileLabel(editingProfile)}
            onCancelEdit={handleCancelEditClick}
          />
        </section>

        <section className="section-card scroll-panel">
          <div className="section-header section-header-inline">
            <div>
              <h3>Historia profili</h3>
              <p className="section-copy">Zapisane profile. Wybierz rekord, aby zobaczyc szczegoly.</p>
            </div>
            <button type="button" className="ghost-button" onClick={() => void refreshProfileHistory()} disabled={historyLoading || saveLoading || deletingProfileId !== null}>
              {historyLoading ? "Odswiezanie..." : "Odswiez"}
            </button>
          </div>

          <div className="scroll-panel-body history-panel-body">
            {historyError ? <div className="message error">{historyError}</div> : null}

            {historyLoading ? (
              <p className="placeholder">Ladowanie historii profili...</p>
            ) : profileHistory.length > 0 ? (
              <div className="history-list-wrapper">
                <div className="history-list">
                  {profileHistory.map((profile) => (
                    <div key={profile.id} className={`history-item${selectedProfileId === profile.id ? " active" : ""}`}>
                      <button
                        type="button"
                        className="history-select-button"
                        onClick={() => void selectStoredProfile(profile.id)}
                        disabled={selectedProfileLoading || deletingProfileId === profile.id}
                      >
                        <span className="history-title">{profile.full_name}</span>
                        <span className="history-company">{profile.email}</span>
                        <span className="history-meta">Zapisano: {formatSavedAt(profile.saved_at)}</span>
                      </button>
                      <div className="history-item-actions">
                        <button
                          type="button"
                          className="ghost-button history-edit-button"
                          onClick={(event) => {
                            event.stopPropagation();
                            void handleEditProfileClick(profile.id);
                          }}
                          disabled={selectedProfileLoading || deletingProfileId === profile.id || saveLoading}
                        >
                          Edytuj
                        </button>
                        <button
                          type="button"
                          className="history-delete-button"
                          onClick={(event) => {
                            event.stopPropagation();
                            void handleDeleteProfileClick(profile.id);
                          }}
                          disabled={deletingProfileId === profile.id || saveLoading}
                        >
                          {deletingProfileId === profile.id ? "Usuwanie..." : "Usun"}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="placeholder">Brak zapisanych profili. Pierwszy rekord pojawi sie po zapisie.</p>
            )}
          </div>
        </section>

        <section className="section-card scroll-panel">
          <div className="section-header">
            <div>
              <h3>Szczegoly wybranego profilu</h3>
              <p className="section-copy">Podglad danych profilu wybranego z historii.</p>
            </div>
          </div>

          <div className="scroll-panel-body selected-job-panel-body">
            {selectedProfileLoading ? <p className="placeholder">Ladowanie szczegolow profilu...</p> : null}
            {selectedProfileError ? <div className="message error">{selectedProfileError}</div> : null}

            {selectedProfileDetail?.payload ? (
              <>
                <dl className="detail-grid record-meta-grid">
                  <div>
                    <dt>ID</dt>
                    <dd>{selectedProfileDetail.id}</dd>
                  </div>
                  <div>
                    <dt>Zapisano</dt>
                    <dd>{formatSavedAt(selectedProfileDetail.saved_at)}</dd>
                  </div>
                </dl>

                <CandidateProfileDetails profile={selectedProfileDetail.payload} />
              </>
            ) : !selectedProfileLoading ? (
              <p className="placeholder">Wybierz profil z historii, aby zobaczyc jego szczegoly.</p>
            ) : null}
          </div>
        </section>
      </div>
    </section>
  );
}
