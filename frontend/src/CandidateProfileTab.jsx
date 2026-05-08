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

  const [previewProfileId, setPreviewProfileId] = useState(null);
  const [previewProfileDetail, setPreviewProfileDetail] = useState(null);
  const [previewProfileLoading, setPreviewProfileLoading] = useState(false);
  const [previewProfileError, setPreviewProfileError] = useState(null);
  const [editLoading, setEditLoading] = useState(false);
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
  async function previewStoredProfile(profileId) {
    setPreviewProfileId(profileId);
    setPreviewProfileDetail(null);
    setPreviewProfileError(null);
    setPreviewProfileLoading(true);

    try {
      const payload = await getCandidateProfileDetail(profileId);
      setPreviewProfileDetail(payload);
    } catch (error) {
      setPreviewProfileError(getErrorMessage(error));
    } finally {
      setPreviewProfileLoading(false);
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
  function clearPreviewProfile() {
    setPreviewProfileId(null);
    setPreviewProfileDetail(null);
    setPreviewProfileError(null);
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
    setEditLoading(true);

    try {
      const storedProfile = await getCandidateProfileDetail(profileId);
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
        text: `Edytujesz istniejący profil ID ${storedProfile.id}. Zapis zaktualizuje ten sam rekord.`,
      });
    } catch (error) {
      setMessage({ type: "error", text: `Nie udało się włączyć edycji profilu. ${getErrorMessage(error)}` });
    } finally {
      setEditLoading(false);
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
      text: "Edycja została anulowana. Formularz wrócił do trybu tworzenia nowego profilu.",
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
      await previewStoredProfile(storedProfile.id);
      setHasUnsavedChanges(false);
      setLastSavedProfileId(storedProfile.id);
      setMessage({
        type: "success",
        text: editingProfile
          ? `Profil ID ${storedProfile.id} został zaktualizowany. Historia i szczegóły pokazują już nowe dane.`
          : `Profil został zapisany. Wszystkie zmiany w formularzu są już zapisane. ID: ${storedProfile.id}.`,
      });
    } catch (error) {
      setMessage({
        type: "error",
        text: editingProfile
          ? `Nie udało się zaktualizować profilu. ${getErrorMessage(error)}`
          : `Nie udało się zapisać profilu. ${getErrorMessage(error)}`,
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

      if (previewProfileId === profileId) {
        if (remainingProfiles.length > 0) {
          await previewStoredProfile(remainingProfiles[0].id);
        } else {
          clearPreviewProfile();
        }
      }

      setMessage({
        type: "success",
        text: "Profil został usunięty z historii.",
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
          <h2>Profil</h2>
          <p className="section-copy">Uzupełnij profil kandydata i zapisz go do dalszej analizy.</p>
        </div>
      </div>

      {message ? <div className={`message ${message.type}`}>{message.text}</div> : null}

      <div className="profile-tab-layout">
        <section className="section-card profile-form-panel">
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

        <aside className="profile-sidebar">
          <section className="section-card profile-sidebar-card">
            <div className="section-header section-header-inline">
              <div>
                <h3>Zapisane profile</h3>
                <p className="section-copy">Wybierz, co chcesz podejrzeć po prawej albo załadować do edycji.</p>
              </div>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void refreshProfileHistory()}
                disabled={historyLoading || editLoading || saveLoading || deletingProfileId !== null}
              >
                {historyLoading ? "Odświeżanie..." : "Odśwież listę"}
              </button>
            </div>

            {historyError ? <div className="message error">{historyError}</div> : null}

            {historyLoading ? (
              <p className="placeholder">Ładowanie zapisanych profili...</p>
            ) : profileHistory.length > 0 ? (
              <div className="profile-history-list">
                {profileHistory.map((profile) => {
                  const isPreviewed = previewProfileId === profile.id;
                  const isEditing = editingProfile?.id === profile.id;

                  return (
                    <article
                      key={profile.id}
                      className={`record-card compact-record-card profile-history-card${
                        isPreviewed || isEditing ? " active-record-card" : ""
                      }`}
                    >
                      <div className="record-card-header profile-history-card-header">
                        <div>
                          <h4>{profile.full_name}</h4>
                          <p>{profile.email || "Brak adresu email"}</p>
                        </div>

                        <div className="profile-history-badges">
                          {isPreviewed ? <span className="section-count-badge profile-preview-badge">Podgląd</span> : null}
                          {isEditing ? <span className="section-count-badge profile-editing-badge">Edytujesz</span> : null}
                        </div>
                      </div>

                      <p className="history-meta">Zapisano: {formatSavedAt(profile.saved_at)}</p>

                      <div className="record-card-actions profile-history-actions">
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => void previewStoredProfile(profile.id)}
                          disabled={previewProfileLoading || editLoading || deletingProfileId === profile.id}
                        >
                          Podgląd
                        </button>
                        <button
                          type="button"
                          className="ghost-button history-edit-button"
                          onClick={() => void handleEditProfileClick(profile.id)}
                          disabled={previewProfileLoading || editLoading || deletingProfileId === profile.id || saveLoading}
                        >
                          Edytuj
                        </button>
                        <button
                          type="button"
                          className="history-delete-button"
                          onClick={() => void handleDeleteProfileClick(profile.id)}
                          disabled={editLoading || deletingProfileId === profile.id || saveLoading}
                        >
                          {deletingProfileId === profile.id ? "Usuwanie..." : "Usuń"}
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <p className="placeholder">Brak zapisanych profili. Pierwszy rekord pojawi się po zapisie.</p>
            )}
          </section>

          <section className="section-card profile-sidebar-card">
            <div className="section-header">
              <div>
                <h3>Podgląd wybranego profilu</h3>
                <p className="section-copy">Podgląd nie zmienia danych w formularzu po lewej stronie.</p>
              </div>
            </div>

            <div className="profile-preview-body">
              {previewProfileLoading ? <p className="placeholder">Ładowanie szczegółów profilu...</p> : null}
              {previewProfileError ? <div className="message error">{previewProfileError}</div> : null}

              {previewProfileDetail?.payload ? (
                <>
                  <dl className="detail-grid record-meta-grid">
                    <div>
                      <dt>ID</dt>
                      <dd>{previewProfileDetail.id}</dd>
                    </div>
                    <div>
                      <dt>Zapisano</dt>
                      <dd>{formatSavedAt(previewProfileDetail.saved_at)}</dd>
                    </div>
                  </dl>

                  <div className="profile-preview-content">
                    <CandidateProfileDetails profile={previewProfileDetail.payload} />
                  </div>
                </>
              ) : !previewProfileLoading ? (
                <p className="placeholder">Kliknij „Podgląd”, aby zobaczyć profil bez ładowania go do formularza.</p>
              ) : null}
            </div>
          </section>
        </aside>
      </div>
    </section>
  );
}
