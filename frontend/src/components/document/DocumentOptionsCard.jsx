/**
 * Compact options row for language, photo and consent settings.
 */

import DocumentWorkflowRow from "./DocumentWorkflowRow";

/**
 * @param {{
 *   mode?: "active" | "completed" | "locked" | "available" | "editing",
 *   expanded?: boolean,
 *   documentOptions: {language: string, includePhoto: boolean, consentMode: string, customConsentText: string},
 *   uploadedPhoto: object | null,
 *   photoUploadLoading: boolean,
 *   flowIsLoading: boolean,
 *   onOptionChange: (fieldName: string, nextValue: string | boolean) => void,
 *   onPhotoUpload: (file: File | undefined) => void,
 *   onExpand: () => void,
 *   onContinue: () => void,
 * }} props Component props.
 * @returns {JSX.Element} Document options workflow row.
 */
export default function DocumentOptionsCard({
  mode = "available",
  expanded = false,
  documentOptions,
  uploadedPhoto,
  photoUploadLoading,
  flowIsLoading,
  onOptionChange,
  onPhotoUpload,
  onExpand,
  onContinue,
}) {
  const isLocked = mode === "locked";
  const languageLabel = documentOptions.language === "pl" ? "PL" : "EN";
  const photoLabel = documentOptions.includePhoto
    ? uploadedPhoto?.photo_asset_id
      ? "Zdjęcie: tak"
      : "Zdjęcie: brak pliku"
    : "Zdjęcie: nie";
  const consentLabel = {
    default: "Klauzula: domyślna",
    custom: "Klauzula: własna",
    none: "Klauzula: brak",
  }[documentOptions.consentMode] ?? "Klauzula: domyślna";

  function renderControls() {
    return (
      <div className="document-workflow-form">
        <div className="form-grid document-form-grid">
          <label className="field">
            <span>Język</span>
            <select
              className="select-input"
              value={documentOptions.language}
              onChange={(event) => onOptionChange("language", event.target.value)}
              disabled={flowIsLoading}
            >
              <option value="en">EN</option>
              <option value="pl">PL</option>
            </select>
          </label>

          <label className="field">
            <span>Zdjęcie</span>
            <select
              className="select-input"
              value={documentOptions.includePhoto ? "yes" : "no"}
              onChange={(event) => onOptionChange("includePhoto", event.target.value === "yes")}
              disabled={flowIsLoading}
            >
              <option value="no">Nie</option>
              <option value="yes">Tak</option>
            </select>
          </label>

          <label className="field">
            <span>Klauzula</span>
            <select
              className="select-input"
              value={documentOptions.consentMode}
              onChange={(event) => onOptionChange("consentMode", event.target.value)}
              disabled={flowIsLoading}
            >
              <option value="default">Domyślna</option>
              <option value="custom">Własna</option>
              <option value="none">Brak</option>
            </select>
          </label>

          {documentOptions.includePhoto ? (
            <label className="field section-wide-field">
              <span>Wgraj zdjęcie</span>
              <input
                type="file"
                accept=".jpg,.jpeg,.png,image/jpeg,image/png"
                onChange={(event) => onPhotoUpload(event.target.files?.[0])}
                disabled={photoUploadLoading || flowIsLoading}
              />
              <p className="helper-text">Upload jest wymagany tylko dla wariantu ze zdjęciem.</p>
              {uploadedPhoto?.photo_asset_id ? (
                <p className="helper-text">Aktywne zdjęcie: {uploadedPhoto.photo_asset_id}</p>
              ) : null}
            </label>
          ) : null}

          {documentOptions.consentMode === "custom" ? (
            <label className="field section-wide-field">
              <span>Własna klauzula</span>
              <textarea
                className="form-textarea compact-textarea"
                value={documentOptions.customConsentText}
                onChange={(event) => onOptionChange("customConsentText", event.target.value)}
                placeholder="Wpisz treść klauzuli do stopki CV."
                disabled={flowIsLoading}
              />
            </label>
          ) : null}
        </div>

        <div className="document-row-toolbar">
          <button type="button" className="primary-button document-row-action-button" onClick={onContinue}>
            Przejdź do generowania PDF
          </button>
        </div>
      </div>
    );
  }

  const summary = !isLocked ? (
    <div className="document-row-summary-list">
      <span>{languageLabel}</span>
      <span>{photoLabel}</span>
      <span>{consentLabel}</span>
    </div>
  ) : null;

  const actions = !isLocked && !expanded ? (
    <button type="button" className="ghost-button document-row-action-button" onClick={onExpand}>
      Zmień opcje
    </button>
  ) : null;

  return (
    <DocumentWorkflowRow
      status={mode}
      expanded={!isLocked && expanded}
      stepLabel="Krok 2"
      title="Opcje dokumentu"
      summary={summary}
      note={isLocked ? "Najpierw wybierz draft CV." : null}
      actions={actions}
      body={renderControls()}
    />
  );
}
