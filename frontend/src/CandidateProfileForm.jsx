/**
 * Sectioned CandidateProfile form used as the main profile entry workflow.
 */

import TagListInput from "./TagListInput";

const UI_ENTRY_ID_FIELD = "__ui_id";

/**
 * Create a stable client-side identifier for form records that require an ID.
 *
 * @param {string} prefix Prefix describing the record type.
 * @returns {string} Generated identifier stable for the current form entry.
 */
function createClientId(prefix) {
  if (globalThis.crypto?.randomUUID) {
    return `${prefix}_${globalThis.crypto.randomUUID()}`;
  }
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Create a stable frontend-only identifier for repeatable form records.
 *
 * @param {string} prefix Prefix describing the record type.
 * @returns {string} Stable local identifier used only by the UI.
 */
function createUiEntryId(prefix) {
  return createClientId(prefix);
}

/**
 * Resolve a stable React key for one repeatable form record.
 *
 * @param {object} entry Current record draft.
 * @param {string} fallbackPrefix Prefix used when no explicit local ID exists.
 * @param {number} index Entry index used only as a final fallback.
 * @returns {string} Stable key for React rendering.
 */
function getCollectionEntryKey(entry, fallbackPrefix, index) {
  return entry?.id ?? entry?.[UI_ENTRY_ID_FIELD] ?? `${fallbackPrefix}_${index}`;
}

/**
 * Trim a free-text value and always return a string.
 *
 * @param {unknown} value Raw field value.
 * @returns {string} Trimmed string.
 */
function normalizeString(value) {
  return String(value ?? "").trim();
}

/**
 * Convert an optional text field into a trimmed value or null.
 *
 * @param {unknown} value Raw field value.
 * @returns {string | null} Trimmed value or null when empty.
 */
function normalizeOptionalString(value) {
  const normalizedValue = normalizeString(value);
  return normalizedValue || null;
}

/**
 * Normalize a list of short text items and drop empty values.
 *
 * @param {unknown[]} values Raw list values.
 * @returns {string[]} Clean list items.
 */
function normalizeStringList(values) {
  return (Array.isArray(values) ? values : []).map(normalizeString).filter(Boolean);
}

/**
 * Convert textarea content into a trimmed list of lines.
 *
 * @param {string} value Multiline textarea value.
 * @returns {string[]} Parsed list items.
 */
function splitLines(value) {
  return String(value ?? "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

/**
 * Parse a numeric input used for years of experience.
 *
 * @param {string} value Raw input value.
 * @returns {number | null} Parsed number or null when empty or invalid.
 */
function parseYearsOfExperience(value) {
  const normalizedValue = normalizeString(value).replace(",", ".");
  if (!normalizedValue) {
    return null;
  }

  const parsedValue = Number.parseFloat(normalizedValue);
  return Number.isFinite(parsedValue) ? parsedValue : null;
}

/**
 * Create an empty ExperienceEntry draft with an auto-generated stable ID.
 *
 * @returns {object} New experience draft.
 */
function createEmptyExperienceEntry() {
  return {
    id: createClientId("exp"),
    company_name: "",
    position_title: "",
    start_date: "",
    end_date: "",
    is_current: false,
    location: "",
    responsibilities: [],
    achievements: [],
    technologies_used: [],
    keywords: [],
  };
}

/**
 * Create an empty ProjectEntry draft with an auto-generated stable ID.
 *
 * @returns {object} New project draft.
 */
function createEmptyProjectEntry() {
  return {
    id: createClientId("project"),
    project_name: "",
    role: "",
    description: "",
    technologies_used: [],
    outcomes: [],
    keywords: [],
    link: "",
  };
}

/**
 * Create an empty SkillEntry draft.
 *
 * @returns {object} New skill draft.
 */
function createEmptySkillEntry() {
  return {
    [UI_ENTRY_ID_FIELD]: createUiEntryId("skill"),
    name: "",
    category: "",
    level: "",
    years_of_experience: "",
    aliases: [],
    evidence_sources: [],
  };
}

/**
 * Create an empty EducationEntry draft.
 *
 * @returns {object} New education draft.
 */
function createEmptyEducationEntry() {
  return {
    [UI_ENTRY_ID_FIELD]: createUiEntryId("education"),
    institution_name: "",
    degree: "",
    field_of_study: "",
    start_date: "",
    end_date: "",
    is_current: false,
  };
}

/**
 * Create an empty LanguageEntry draft.
 *
 * @returns {object} New language draft.
 */
function createEmptyLanguageEntry() {
  return {
    [UI_ENTRY_ID_FIELD]: createUiEntryId("language"),
    language_name: "",
    proficiency_level: "",
  };
}

/**
 * Create an empty CertificateEntry draft.
 *
 * @returns {object} New certificate draft.
 */
function createEmptyCertificateEntry() {
  return {
    [UI_ENTRY_ID_FIELD]: createUiEntryId("certificate"),
    certificate_name: "",
    issuer: "",
    issue_date: "",
    notes: "",
  };
}

/**
 * Create a new empty CandidateProfile form state.
 *
 * @returns {object} Empty form state matching the backend model shape.
 */
export function createEmptyCandidateProfileFormState() {
  return {
    personal_info: {
      full_name: "",
      email: "",
      phone: "",
      location: "",
      linkedin_url: "",
      github_url: "",
      portfolio_url: "",
    },
    target_roles: [],
    professional_summary_base: "",
    experience_entries: [],
    project_entries: [],
    skill_entries: [],
    education_entries: [],
    language_entries: [],
    certificate_entries: [],
    immutable_rules: {
      forbidden_skills: [],
      forbidden_claims: [],
      forbidden_certificates: [],
      editing_rules: [],
    },
  };
}

/**
 * Check whether an experience draft contains any meaningful user data.
 *
 * @param {object} entry Experience draft.
 * @returns {boolean} True when the entry is effectively empty.
 */
function isEmptyExperienceEntry(entry) {
  return ![
    normalizeString(entry.company_name),
    normalizeString(entry.position_title),
    normalizeString(entry.start_date),
    normalizeString(entry.end_date),
    normalizeString(entry.location),
    ...normalizeStringList(entry.responsibilities),
    ...normalizeStringList(entry.achievements),
    ...normalizeStringList(entry.technologies_used),
    ...normalizeStringList(entry.keywords),
  ].length;
}

/**
 * Check whether a project draft contains any meaningful user data.
 *
 * @param {object} entry Project draft.
 * @returns {boolean} True when the entry is effectively empty.
 */
function isEmptyProjectEntry(entry) {
  return ![
    normalizeString(entry.project_name),
    normalizeString(entry.role),
    normalizeString(entry.description),
    normalizeString(entry.link),
    ...normalizeStringList(entry.technologies_used),
    ...normalizeStringList(entry.outcomes),
    ...normalizeStringList(entry.keywords),
  ].length;
}

/**
 * Check whether a skill draft contains any meaningful user data.
 *
 * @param {object} entry Skill draft.
 * @returns {boolean} True when the entry is effectively empty.
 */
function isEmptySkillEntry(entry) {
  return ![
    normalizeString(entry.name),
    normalizeString(entry.category),
    normalizeString(entry.level),
    normalizeString(entry.years_of_experience),
    ...normalizeStringList(entry.aliases),
    ...normalizeStringList(entry.evidence_sources),
  ].length;
}

/**
 * Check whether an education draft contains any meaningful user data.
 *
 * @param {object} entry Education draft.
 * @returns {boolean} True when the entry is effectively empty.
 */
function isEmptyEducationEntry(entry) {
  return ![
    normalizeString(entry.institution_name),
    normalizeString(entry.degree),
    normalizeString(entry.field_of_study),
    normalizeString(entry.start_date),
    normalizeString(entry.end_date),
  ].length;
}

/**
 * Check whether a language draft contains any meaningful user data.
 *
 * @param {object} entry Language draft.
 * @returns {boolean} True when the entry is effectively empty.
 */
function isEmptyLanguageEntry(entry) {
  return ![normalizeString(entry.language_name), normalizeString(entry.proficiency_level)].length;
}

/**
 * Check whether a certificate draft contains any meaningful user data.
 *
 * @param {object} entry Certificate draft.
 * @returns {boolean} True when the entry is effectively empty.
 */
function isEmptyCertificateEntry(entry) {
  return ![
    normalizeString(entry.certificate_name),
    normalizeString(entry.issuer),
    normalizeString(entry.issue_date),
    normalizeString(entry.notes),
  ].length;
}

/**
 * Serialize the current form state into a backend-ready CandidateProfile payload.
 *
 * @param {object} formState Current profile form state.
 * @returns {object} CandidateProfile payload compatible with `POST /profile/save`.
 */
export function buildCandidateProfilePayload(formState) {
  return {
    personal_info: {
      full_name: normalizeString(formState.personal_info.full_name),
      email: normalizeString(formState.personal_info.email),
      phone: normalizeString(formState.personal_info.phone),
      location: normalizeString(formState.personal_info.location),
      linkedin_url: normalizeOptionalString(formState.personal_info.linkedin_url),
      github_url: normalizeOptionalString(formState.personal_info.github_url),
      portfolio_url: normalizeOptionalString(formState.personal_info.portfolio_url),
    },
    target_roles: normalizeStringList(formState.target_roles),
    professional_summary_base: normalizeString(formState.professional_summary_base),
    experience_entries: formState.experience_entries
      .filter((entry) => !isEmptyExperienceEntry(entry))
      .map((entry) => ({
        id: entry.id,
        company_name: normalizeString(entry.company_name),
        position_title: normalizeString(entry.position_title),
        start_date: normalizeString(entry.start_date),
        end_date: entry.is_current ? null : normalizeOptionalString(entry.end_date),
        is_current: Boolean(entry.is_current),
        location: normalizeString(entry.location),
        responsibilities: normalizeStringList(entry.responsibilities),
        achievements: normalizeStringList(entry.achievements),
        technologies_used: normalizeStringList(entry.technologies_used),
        keywords: normalizeStringList(entry.keywords),
      })),
    project_entries: formState.project_entries
      .filter((entry) => !isEmptyProjectEntry(entry))
      .map((entry) => ({
        id: entry.id,
        project_name: normalizeString(entry.project_name),
        role: normalizeString(entry.role),
        description: normalizeString(entry.description),
        technologies_used: normalizeStringList(entry.technologies_used),
        outcomes: normalizeStringList(entry.outcomes),
        keywords: normalizeStringList(entry.keywords),
        link: normalizeOptionalString(entry.link),
      })),
    skill_entries: formState.skill_entries
      .filter((entry) => !isEmptySkillEntry(entry))
      .map((entry) => ({
        name: normalizeString(entry.name),
        category: normalizeString(entry.category),
        level: normalizeString(entry.level),
        years_of_experience: parseYearsOfExperience(entry.years_of_experience),
        evidence_sources: normalizeStringList(entry.evidence_sources),
        aliases: normalizeStringList(entry.aliases),
      })),
    education_entries: formState.education_entries
      .filter((entry) => !isEmptyEducationEntry(entry))
      .map((entry) => ({
        institution_name: normalizeString(entry.institution_name),
        degree: normalizeString(entry.degree),
        field_of_study: normalizeString(entry.field_of_study),
        start_date: normalizeString(entry.start_date),
        end_date: entry.is_current ? null : normalizeOptionalString(entry.end_date),
        is_current: Boolean(entry.is_current),
      })),
    language_entries: formState.language_entries
      .filter((entry) => !isEmptyLanguageEntry(entry))
      .map((entry) => ({
        language_name: normalizeString(entry.language_name),
        proficiency_level: normalizeString(entry.proficiency_level),
      })),
    certificate_entries: formState.certificate_entries
      .filter((entry) => !isEmptyCertificateEntry(entry))
      .map((entry) => ({
        certificate_name: normalizeString(entry.certificate_name),
        issuer: normalizeString(entry.issuer),
        issue_date: normalizeOptionalString(entry.issue_date),
        notes: normalizeOptionalString(entry.notes),
      })),
    immutable_rules: {
      forbidden_skills: normalizeStringList(formState.immutable_rules.forbidden_skills),
      forbidden_claims: normalizeStringList(formState.immutable_rules.forbidden_claims),
      forbidden_certificates: normalizeStringList(formState.immutable_rules.forbidden_certificates),
      editing_rules: normalizeStringList(formState.immutable_rules.editing_rules),
    },
  };
}

/**
 * Render a reusable collapsible form section with a short summary label.
 *
 * @param {{
 *   title: string,
 *   description: string,
 *   summary?: string,
 *   defaultOpen?: boolean,
 *   children: import("react").ReactNode,
 * }} props Component props.
 * @returns {JSX.Element} Collapsible form section.
 */
function FormSection({ title, description, summary, defaultOpen = false, children }) {
  return (
    <details className="profile-form-section" open={defaultOpen}>
      <summary className="profile-form-summary">
        <div>
          <strong>{title}</strong>
          <p>{description}</p>
        </div>
        {summary ? <span className="section-count-badge">{summary}</span> : null}
      </summary>

      <div className="profile-form-body">{children}</div>
    </details>
  );
}

/**
 * Render a textarea that stores one list item per line.
 *
 * @param {{
 *   label: string,
 *   items: string[],
 *   onChange: (items: string[]) => void,
 *   placeholder?: string,
 *   rows?: number,
 * }} props Component props.
 * @returns {JSX.Element} Multiline list editor.
 */
function LineListField({ label, items, onChange, placeholder = "Kazda linia to osobna pozycja", rows = 4 }) {
  return (
    <label className="field">
      <span>{label}</span>
      <textarea
        className="form-textarea compact-textarea"
        rows={rows}
        placeholder={placeholder}
        value={(Array.isArray(items) ? items : []).join("\n")}
        onChange={(event) => onChange(splitLines(event.target.value))}
      />
    </label>
  );
}

/**
 * Render the sectioned profile form used as the primary data-entry flow.
 *
 * @param {{
 *   formValue: object,
 *   onChange: (nextValue: object) => void,
 *   onSave: () => void,
 *   saveLoading: boolean,
 * }} props Component props.
 * @returns {JSX.Element} Candidate-profile form.
 */
export default function CandidateProfileForm({ formValue, onChange, onSave, saveLoading }) {
  const profilePreview = buildCandidateProfilePayload(formValue);

  /**
   * Update one field inside `personal_info`.
   *
   * @param {string} fieldName Personal info field name.
   * @param {string} value New field value.
   * @returns {void} No return value.
   */
  function updatePersonalInfo(fieldName, value) {
    onChange({
      ...formValue,
      personal_info: {
        ...formValue.personal_info,
        [fieldName]: value,
      },
    });
  }

  /**
   * Update one top-level scalar field.
   *
   * @param {string} fieldName Top-level field name.
   * @param {string | string[]} value New field value.
   * @returns {void} No return value.
   */
  function updateTopLevelField(fieldName, value) {
    onChange({
      ...formValue,
      [fieldName]: value,
    });
  }

  /**
   * Update one field inside a repeatable collection entry.
   *
   * @param {string} collectionName Collection field name.
   * @param {number} index Entry index.
   * @param {string} fieldName Entry field name.
   * @param {unknown} value New field value.
   * @returns {void} No return value.
   */
  function updateCollectionEntry(collectionName, index, fieldName, value) {
    const nextCollection = formValue[collectionName].map((entry, entryIndex) =>
      entryIndex === index
        ? {
            ...entry,
            [fieldName]: value,
          }
        : entry,
    );

    onChange({
      ...formValue,
      [collectionName]: nextCollection,
    });
  }

  /**
   * Append a new draft record to one repeatable collection.
   *
   * @param {string} collectionName Collection field name.
   * @param {() => object} createEntry Factory returning a new draft entry.
   * @returns {void} No return value.
   */
  function addCollectionEntry(collectionName, createEntry) {
    onChange({
      ...formValue,
      [collectionName]: [...formValue[collectionName], createEntry()],
    });
  }

  /**
   * Remove one draft record from a repeatable collection.
   *
   * @param {string} collectionName Collection field name.
   * @param {number} index Entry index to remove.
   * @returns {void} No return value.
   */
  function removeCollectionEntry(collectionName, index) {
    onChange({
      ...formValue,
      [collectionName]: formValue[collectionName].filter((_, entryIndex) => entryIndex !== index),
    });
  }

  /**
   * Update one list field inside `immutable_rules`.
   *
   * @param {string} fieldName Immutable rules field name.
   * @param {string[]} values Updated list values.
   * @returns {void} No return value.
   */
  function updateImmutableRules(fieldName, values) {
    onChange({
      ...formValue,
      immutable_rules: {
        ...formValue.immutable_rules,
        [fieldName]: values,
      },
    });
  }

  return (
    <div className="profile-form-stack">
      <div className="section-header section-header-inline">
        <div>
          <h3>Formularz profilu</h3>
          <p className="section-copy">Uzupelnij profil kandydata i zapisz go do dalszej analizy.</p>
        </div>
        <button type="button" className="primary-button" onClick={onSave} disabled={saveLoading}>
          {saveLoading ? "Zapisywanie..." : "Zapisz profil"}
        </button>
      </div>

      <FormSection title="Dane podstawowe" description="Najwazniejsze dane kontaktowe i linki." defaultOpen>
        <div className="form-grid">
          <label className="field">
            <span>Imie i nazwisko</span>
            <input
              type="text"
              value={formValue.personal_info.full_name}
              onChange={(event) => updatePersonalInfo("full_name", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={formValue.personal_info.email}
              onChange={(event) => updatePersonalInfo("email", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Telefon</span>
            <input
              type="text"
              value={formValue.personal_info.phone}
              onChange={(event) => updatePersonalInfo("phone", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Lokalizacja</span>
            <input
              type="text"
              value={formValue.personal_info.location}
              onChange={(event) => updatePersonalInfo("location", event.target.value)}
            />
          </label>

          <label className="field">
            <span>LinkedIn</span>
            <input
              type="url"
              value={formValue.personal_info.linkedin_url}
              onChange={(event) => updatePersonalInfo("linkedin_url", event.target.value)}
            />
          </label>

          <label className="field">
            <span>GitHub</span>
            <input
              type="url"
              value={formValue.personal_info.github_url}
              onChange={(event) => updatePersonalInfo("github_url", event.target.value)}
            />
          </label>

          <label className="field section-wide-field">
            <span>Portfolio</span>
            <input
              type="url"
              value={formValue.personal_info.portfolio_url}
              onChange={(event) => updatePersonalInfo("portfolio_url", event.target.value)}
            />
          </label>
        </div>
      </FormSection>

      <FormSection
        title="Role docelowe"
        description="Stanowiska, na ktore chcesz aplikowac."
        summary={`${formValue.target_roles.length} pozycji`}
        defaultOpen
      >
        <TagListInput
          label="Role docelowe"
          items={formValue.target_roles}
          onChange={(items) => updateTopLevelField("target_roles", items)}
          placeholder="Np. Backend Developer"
          addLabel="Dodaj role"
        />
      </FormSection>

      <FormSection title="Podsumowanie zawodowe" description="Krotki opis Twojego profilu zawodowego." defaultOpen>
        <label className="field">
          <span>Podsumowanie</span>
          <textarea
            className="form-textarea"
            rows={5}
            value={formValue.professional_summary_base}
            onChange={(event) => updateTopLevelField("professional_summary_base", event.target.value)}
          />
        </label>
      </FormSection>

      <FormSection
        title="Doswiadczenie zawodowe"
        description="Najwazniejsze miejsca pracy i zakres odpowiedzialnosci."
        summary={`${formValue.experience_entries.length} wpisow`}
        defaultOpen
      >
        <div className="section-toolbar">
          <button type="button" className="ghost-button" onClick={() => addCollectionEntry("experience_entries", createEmptyExperienceEntry)}>
            Dodaj doswiadczenie
          </button>
        </div>

        {formValue.experience_entries.length > 0 ? (
          <div className="record-list">
            {formValue.experience_entries.map((entry, index) => (
              <article key={entry.id} className="record-card">
                <div className="record-card-header">
                  <div>
                    <h4>{entry.position_title || `Doswiadczenie ${index + 1}`}</h4>
                    <p>{entry.company_name || "Nowy wpis"}</p>
                  </div>
                  <button
                    type="button"
                    className="ghost-button danger-ghost-button"
                    onClick={() => removeCollectionEntry("experience_entries", index)}
                  >
                    Usun
                  </button>
                </div>

                <div className="form-grid">
                  <label className="field">
                    <span>Firma</span>
                    <input
                      type="text"
                      value={entry.company_name}
                      onChange={(event) => updateCollectionEntry("experience_entries", index, "company_name", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Stanowisko</span>
                    <input
                      type="text"
                      value={entry.position_title}
                      onChange={(event) => updateCollectionEntry("experience_entries", index, "position_title", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Data rozpoczecia</span>
                    <input
                      type="date"
                      value={entry.start_date}
                      onChange={(event) => updateCollectionEntry("experience_entries", index, "start_date", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Data zakonczenia</span>
                    <input
                      type="date"
                      value={entry.end_date}
                      disabled={entry.is_current}
                      onChange={(event) => updateCollectionEntry("experience_entries", index, "end_date", event.target.value)}
                    />
                  </label>

                  <label className="field section-wide-field">
                    <span>Lokalizacja</span>
                    <input
                      type="text"
                      value={entry.location}
                      onChange={(event) => updateCollectionEntry("experience_entries", index, "location", event.target.value)}
                    />
                  </label>
                </div>

                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={entry.is_current}
                    onChange={(event) => updateCollectionEntry("experience_entries", index, "is_current", event.target.checked)}
                  />
                  <span>To jest moje obecne stanowisko</span>
                </label>

                <LineListField
                  label="Zakres obowiazkow"
                  items={entry.responsibilities}
                  onChange={(items) => updateCollectionEntry("experience_entries", index, "responsibilities", items)}
                  placeholder="Kazda linia to osobny obowiazek"
                />

                <LineListField
                  label="Osiegniecia"
                  items={entry.achievements}
                  onChange={(items) => updateCollectionEntry("experience_entries", index, "achievements", items)}
                  placeholder="Kazda linia to osobne osiagniecie"
                />

                <div className="form-grid">
                  <TagListInput
                    label="Technologie"
                    items={entry.technologies_used}
                    onChange={(items) => updateCollectionEntry("experience_entries", index, "technologies_used", items)}
                    placeholder="Np. Python"
                    addLabel="Dodaj technologie"
                  />

                  <TagListInput
                    label="Slowa kluczowe"
                    items={entry.keywords}
                    onChange={(items) => updateCollectionEntry("experience_entries", index, "keywords", items)}
                    placeholder="Np. API"
                    addLabel="Dodaj slowo"
                  />
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="placeholder">Dodaj pierwsze doswiadczenie zawodowe.</p>
        )}
      </FormSection>

      <FormSection
        title="Projekty"
        description="Projekty, ktore warto pokazac przy dopasowaniu do oferty."
        summary={`${formValue.project_entries.length} wpisow`}
      >
        <div className="section-toolbar">
          <button type="button" className="ghost-button" onClick={() => addCollectionEntry("project_entries", createEmptyProjectEntry)}>
            Dodaj projekt
          </button>
        </div>

        {formValue.project_entries.length > 0 ? (
          <div className="record-list">
            {formValue.project_entries.map((entry, index) => (
              <article key={entry.id} className="record-card">
                <div className="record-card-header">
                  <div>
                    <h4>{entry.project_name || `Projekt ${index + 1}`}</h4>
                    <p>{entry.role || "Nowy wpis"}</p>
                  </div>
                  <button
                    type="button"
                    className="ghost-button danger-ghost-button"
                    onClick={() => removeCollectionEntry("project_entries", index)}
                  >
                    Usun
                  </button>
                </div>

                <div className="form-grid">
                  <label className="field">
                    <span>Nazwa projektu</span>
                    <input
                      type="text"
                      value={entry.project_name}
                      onChange={(event) => updateCollectionEntry("project_entries", index, "project_name", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Rola</span>
                    <input
                      type="text"
                      value={entry.role}
                      onChange={(event) => updateCollectionEntry("project_entries", index, "role", event.target.value)}
                    />
                  </label>

                  <label className="field section-wide-field">
                    <span>Link</span>
                    <input
                      type="url"
                      value={entry.link}
                      onChange={(event) => updateCollectionEntry("project_entries", index, "link", event.target.value)}
                    />
                  </label>
                </div>

                <label className="field">
                  <span>Opis projektu</span>
                  <textarea
                    className="form-textarea compact-textarea"
                    rows={4}
                    value={entry.description}
                    onChange={(event) => updateCollectionEntry("project_entries", index, "description", event.target.value)}
                  />
                </label>

                <LineListField
                  label="Rezultaty"
                  items={entry.outcomes}
                  onChange={(items) => updateCollectionEntry("project_entries", index, "outcomes", items)}
                  placeholder="Kazda linia to osobny rezultat"
                />

                <div className="form-grid">
                  <TagListInput
                    label="Technologie"
                    items={entry.technologies_used}
                    onChange={(items) => updateCollectionEntry("project_entries", index, "technologies_used", items)}
                    placeholder="Np. React"
                    addLabel="Dodaj technologie"
                  />

                  <TagListInput
                    label="Slowa kluczowe"
                    items={entry.keywords}
                    onChange={(items) => updateCollectionEntry("project_entries", index, "keywords", items)}
                    placeholder="Np. REST API"
                    addLabel="Dodaj slowo"
                  />
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="placeholder">Dodaj projekt, jesli chcesz pokazac dodatkowe potwierdzenie kompetencji.</p>
        )}
      </FormSection>

      <FormSection
        title="Umiejetnosci"
        description="Technologie i kompetencje, ktore chcesz uwzglednic w analizie."
        summary={`${formValue.skill_entries.length} wpisow`}
        defaultOpen
      >
        <div className="section-toolbar">
          <button type="button" className="ghost-button" onClick={() => addCollectionEntry("skill_entries", createEmptySkillEntry)}>
            Dodaj umiejetnosc
          </button>
        </div>

        {formValue.skill_entries.length > 0 ? (
          <div className="record-list">
            {formValue.skill_entries.map((entry, index) => (
              <article key={getCollectionEntryKey(entry, "skill", index)} className="record-card">
                <div className="record-card-header">
                  <div>
                    <h4>{entry.name || `Umiejetnosc ${index + 1}`}</h4>
                    <p>{entry.category || "Nowy wpis"}</p>
                  </div>
                  <button
                    type="button"
                    className="ghost-button danger-ghost-button"
                    onClick={() => removeCollectionEntry("skill_entries", index)}
                  >
                    Usun
                  </button>
                </div>

                <div className="form-grid">
                  <label className="field">
                    <span>Nazwa</span>
                    <input
                      type="text"
                      value={entry.name}
                      onChange={(event) => updateCollectionEntry("skill_entries", index, "name", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Kategoria</span>
                    <input
                      type="text"
                      value={entry.category}
                      onChange={(event) => updateCollectionEntry("skill_entries", index, "category", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Poziom</span>
                    <input
                      type="text"
                      value={entry.level}
                      onChange={(event) => updateCollectionEntry("skill_entries", index, "level", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Lata doswiadczenia</span>
                    <input
                      type="number"
                      min="0"
                      step="0.5"
                      value={entry.years_of_experience}
                      onChange={(event) => updateCollectionEntry("skill_entries", index, "years_of_experience", event.target.value)}
                    />
                  </label>
                </div>

                <div className="form-grid">
                  <TagListInput
                    label="Aliasy"
                    items={entry.aliases}
                    onChange={(items) => updateCollectionEntry("skill_entries", index, "aliases", items)}
                    placeholder="Np. JS"
                    addLabel="Dodaj alias"
                  />

                  <TagListInput
                    label="Zrodla potwierdzenia"
                    items={entry.evidence_sources}
                    onChange={(items) => updateCollectionEntry("skill_entries", index, "evidence_sources", items)}
                    placeholder="Np. exp_123"
                    addLabel="Dodaj zrodlo"
                  />
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="placeholder">Dodaj umiejetnosci, ktore warto brac pod uwage w matchingu.</p>
        )}
      </FormSection>

      <FormSection
        title="Edukacja"
        description="Szkoly, uczelnie i kierunki studiow."
        summary={`${formValue.education_entries.length} wpisow`}
      >
        <div className="section-toolbar">
          <button type="button" className="ghost-button" onClick={() => addCollectionEntry("education_entries", createEmptyEducationEntry)}>
            Dodaj edukacje
          </button>
        </div>

        {formValue.education_entries.length > 0 ? (
          <div className="record-list">
            {formValue.education_entries.map((entry, index) => (
              <article key={getCollectionEntryKey(entry, "education", index)} className="record-card">
                <div className="record-card-header">
                  <div>
                    <h4>{entry.institution_name || `Edukacja ${index + 1}`}</h4>
                    <p>{entry.degree || "Nowy wpis"}</p>
                  </div>
                  <button
                    type="button"
                    className="ghost-button danger-ghost-button"
                    onClick={() => removeCollectionEntry("education_entries", index)}
                  >
                    Usun
                  </button>
                </div>

                <div className="form-grid">
                  <label className="field">
                    <span>Instytucja</span>
                    <input
                      type="text"
                      value={entry.institution_name}
                      onChange={(event) => updateCollectionEntry("education_entries", index, "institution_name", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Stopien</span>
                    <input
                      type="text"
                      value={entry.degree}
                      onChange={(event) => updateCollectionEntry("education_entries", index, "degree", event.target.value)}
                    />
                  </label>

                  <label className="field section-wide-field">
                    <span>Kierunek</span>
                    <input
                      type="text"
                      value={entry.field_of_study}
                      onChange={(event) => updateCollectionEntry("education_entries", index, "field_of_study", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Data rozpoczecia</span>
                    <input
                      type="date"
                      value={entry.start_date}
                      onChange={(event) => updateCollectionEntry("education_entries", index, "start_date", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Data zakonczenia</span>
                    <input
                      type="date"
                      value={entry.end_date}
                      disabled={entry.is_current}
                      onChange={(event) => updateCollectionEntry("education_entries", index, "end_date", event.target.value)}
                    />
                  </label>
                </div>

                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={entry.is_current}
                    onChange={(event) => updateCollectionEntry("education_entries", index, "is_current", event.target.checked)}
                  />
                  <span>Nauka nadal trwa</span>
                </label>
              </article>
            ))}
          </div>
        ) : (
          <p className="placeholder">Dodaj edukacje, jesli chcesz uwzglednic ja w analizie i CV.</p>
        )}
      </FormSection>

      <FormSection title="Jezyki" description="Jezyki obce i poziom ich znajomosci." summary={`${formValue.language_entries.length} wpisow`}>
        <div className="section-toolbar">
          <button type="button" className="ghost-button" onClick={() => addCollectionEntry("language_entries", createEmptyLanguageEntry)}>
            Dodaj jezyk
          </button>
        </div>

        {formValue.language_entries.length > 0 ? (
          <div className="record-list compact-record-list">
            {formValue.language_entries.map((entry, index) => (
              <article key={getCollectionEntryKey(entry, "language", index)} className="record-card compact-record-card">
                <div className="record-card-header">
                  <div>
                    <h4>{entry.language_name || `Jezyk ${index + 1}`}</h4>
                    <p>{entry.proficiency_level || "Nowy wpis"}</p>
                  </div>
                  <button
                    type="button"
                    className="ghost-button danger-ghost-button"
                    onClick={() => removeCollectionEntry("language_entries", index)}
                  >
                    Usun
                  </button>
                </div>

                <div className="form-grid">
                  <label className="field">
                    <span>Jezyk</span>
                    <input
                      type="text"
                      value={entry.language_name}
                      onChange={(event) => updateCollectionEntry("language_entries", index, "language_name", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Poziom</span>
                    <input
                      type="text"
                      value={entry.proficiency_level}
                      onChange={(event) => updateCollectionEntry("language_entries", index, "proficiency_level", event.target.value)}
                    />
                  </label>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="placeholder">Dodaj jezyki, ktore chcesz pokazac w profilu.</p>
        )}
      </FormSection>

      <FormSection
        title="Certyfikaty"
        description="Certyfikaty, szkolenia i kursy warte pokazania."
        summary={`${formValue.certificate_entries.length} wpisow`}
      >
        <div className="section-toolbar">
          <button type="button" className="ghost-button" onClick={() => addCollectionEntry("certificate_entries", createEmptyCertificateEntry)}>
            Dodaj certyfikat
          </button>
        </div>

        {formValue.certificate_entries.length > 0 ? (
          <div className="record-list compact-record-list">
            {formValue.certificate_entries.map((entry, index) => (
              <article key={getCollectionEntryKey(entry, "certificate", index)} className="record-card compact-record-card">
                <div className="record-card-header">
                  <div>
                    <h4>{entry.certificate_name || `Certyfikat ${index + 1}`}</h4>
                    <p>{entry.issuer || "Nowy wpis"}</p>
                  </div>
                  <button
                    type="button"
                    className="ghost-button danger-ghost-button"
                    onClick={() => removeCollectionEntry("certificate_entries", index)}
                  >
                    Usun
                  </button>
                </div>

                <div className="form-grid">
                  <label className="field">
                    <span>Nazwa certyfikatu</span>
                    <input
                      type="text"
                      value={entry.certificate_name}
                      onChange={(event) => updateCollectionEntry("certificate_entries", index, "certificate_name", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Wydawca</span>
                    <input
                      type="text"
                      value={entry.issuer}
                      onChange={(event) => updateCollectionEntry("certificate_entries", index, "issuer", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Data uzyskania</span>
                    <input
                      type="date"
                      value={entry.issue_date}
                      onChange={(event) => updateCollectionEntry("certificate_entries", index, "issue_date", event.target.value)}
                    />
                  </label>
                </div>

                <label className="field">
                  <span>Dodatkowe informacje</span>
                  <textarea
                    className="form-textarea compact-textarea"
                    rows={3}
                    value={entry.notes}
                    onChange={(event) => updateCollectionEntry("certificate_entries", index, "notes", event.target.value)}
                  />
                </label>
              </article>
            ))}
          </div>
        ) : (
          <p className="placeholder">Dodaj certyfikaty i szkolenia, jesli sa istotne dla ofert.</p>
        )}
      </FormSection>

      <FormSection
        title="Reguly zaawansowane"
        description="Dodatkowe ograniczenia, ktorych system ma pilnowac."
        summary="Opcjonalne"
      >
        <div className="advanced-grid">
          <TagListInput
            label="Zakazane umiejetnosci"
            items={formValue.immutable_rules.forbidden_skills}
            onChange={(items) => updateImmutableRules("forbidden_skills", items)}
            placeholder="Np. Java"
            addLabel="Dodaj pozycje"
          />

          <TagListInput
            label="Zakazane stwierdzenia"
            items={formValue.immutable_rules.forbidden_claims}
            onChange={(items) => updateImmutableRules("forbidden_claims", items)}
            placeholder="Np. Senior level"
            addLabel="Dodaj pozycje"
          />

          <TagListInput
            label="Zakazane certyfikaty"
            items={formValue.immutable_rules.forbidden_certificates}
            onChange={(items) => updateImmutableRules("forbidden_certificates", items)}
            placeholder="Np. AWS Solutions Architect"
            addLabel="Dodaj pozycje"
          />

          <LineListField
            label="Zasady edycji"
            items={formValue.immutable_rules.editing_rules}
            onChange={(items) => updateImmutableRules("editing_rules", items)}
            placeholder="Kazda linia to osobna zasada"
            rows={4}
          />
        </div>
      </FormSection>

      <details className="raw-json-toggle profile-json-preview">
        <summary>Podglad danych technicznych</summary>
        <pre>{JSON.stringify(profilePreview, null, 2)}</pre>
      </details>

      <div className="actions section-actions-bottom">
        <button type="button" className="primary-button" onClick={onSave} disabled={saveLoading}>
          {saveLoading ? "Zapisywanie..." : "Zapisz profil"}
        </button>
      </div>
    </div>
  );
}
