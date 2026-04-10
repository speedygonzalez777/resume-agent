/**
 * Sectioned CandidateProfile form used as the main profile entry workflow.
 */

import { useEffect, useState } from "react";

import RawJsonPanel from "./RawJsonPanel";
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
 * Convert a normalized string list into multiline textarea content.
 *
 * @param {unknown[]} values Raw list values.
 * @returns {string} Multiline string used by textarea fields.
 */
function joinLines(values) {
  return normalizeStringList(values).join("\n");
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
 * Resolve the current textarea draft for multiline list fields.
 *
 * @param {unknown} draftValue UI draft stored directly in form state.
 * @param {unknown[]} fallbackItems Backend-shaped list used as a backward-compatible fallback.
 * @returns {string} Current textarea content.
 */
function getLineListDraftValue(draftValue, fallbackItems = []) {
  if (typeof draftValue === "string") {
    return draftValue;
  }
  return joinLines(fallbackItems);
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
    responsibilities_text: "",
    achievements_text: "",
    responsibilities: [],
    achievements: [],
    technologies_used: [],
    keywords: [],
  };
}

/**
 * Clone one experience entry into the frontend form shape used by the editor draft.
 *
 * @param {object} entry Existing experience entry.
 * @returns {object} Safe editable copy of the experience entry.
 */
function cloneExperienceEntry(entry) {
  return {
    id: normalizeString(entry?.id) || createClientId("exp"),
    company_name: normalizeString(entry?.company_name),
    position_title: normalizeString(entry?.position_title),
    start_date: normalizeString(entry?.start_date),
    end_date: normalizeString(entry?.end_date),
    is_current: Boolean(entry?.is_current),
    location: normalizeString(entry?.location),
    responsibilities_text: getLineListDraftValue(entry?.responsibilities_text, entry?.responsibilities),
    achievements_text: getLineListDraftValue(entry?.achievements_text, entry?.achievements),
    responsibilities: normalizeStringList(entry?.responsibilities),
    achievements: normalizeStringList(entry?.achievements),
    technologies_used: normalizeStringList(entry?.technologies_used),
    keywords: normalizeStringList(entry?.keywords),
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
    outcomes_text: "",
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
    soft_skill_entries: [],
    interest_entries: [],
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
      editing_rules_text: "",
      editing_rules: [],
    },
  };
}

/**
 * Hydrate backend profile payload into the richer frontend form state.
 *
 * @param {object} profile Stored CandidateProfile payload.
 * @returns {object} Form state ready for controlled editing in the UI.
 */
export function createCandidateProfileFormStateFromProfile(profile) {
  const emptyState = createEmptyCandidateProfileFormState();

  return {
    personal_info: {
      full_name: normalizeString(profile?.personal_info?.full_name),
      email: normalizeString(profile?.personal_info?.email),
      phone: normalizeString(profile?.personal_info?.phone),
      location: normalizeString(profile?.personal_info?.location),
      linkedin_url: normalizeString(profile?.personal_info?.linkedin_url),
      github_url: normalizeString(profile?.personal_info?.github_url),
      portfolio_url: normalizeString(profile?.personal_info?.portfolio_url),
    },
    target_roles: normalizeStringList(profile?.target_roles),
    professional_summary_base: normalizeString(profile?.professional_summary_base),
    soft_skill_entries: normalizeStringList(profile?.soft_skill_entries),
    interest_entries: normalizeStringList(profile?.interest_entries),
    experience_entries: Array.isArray(profile?.experience_entries)
      ? profile.experience_entries.map((entry) => ({
          id: normalizeString(entry?.id) || createClientId("exp"),
          company_name: normalizeString(entry?.company_name),
          position_title: normalizeString(entry?.position_title),
          start_date: normalizeString(entry?.start_date),
          end_date: normalizeString(entry?.end_date),
          is_current: Boolean(entry?.is_current),
          location: normalizeString(entry?.location),
          responsibilities_text: joinLines(entry?.responsibilities),
          achievements_text: joinLines(entry?.achievements),
          responsibilities: normalizeStringList(entry?.responsibilities),
          achievements: normalizeStringList(entry?.achievements),
          technologies_used: normalizeStringList(entry?.technologies_used),
          keywords: normalizeStringList(entry?.keywords),
        }))
      : emptyState.experience_entries,
    project_entries: Array.isArray(profile?.project_entries)
      ? profile.project_entries.map((entry) => ({
          id: normalizeString(entry?.id) || createClientId("project"),
          project_name: normalizeString(entry?.project_name),
          role: normalizeString(entry?.role),
          description: normalizeString(entry?.description),
          outcomes_text: joinLines(entry?.outcomes),
          technologies_used: normalizeStringList(entry?.technologies_used),
          outcomes: normalizeStringList(entry?.outcomes),
          keywords: normalizeStringList(entry?.keywords),
          link: normalizeString(entry?.link),
        }))
      : emptyState.project_entries,
    skill_entries: Array.isArray(profile?.skill_entries)
      ? profile.skill_entries.map((entry) => ({
          [UI_ENTRY_ID_FIELD]: createUiEntryId("skill"),
          name: normalizeString(entry?.name),
          category: normalizeString(entry?.category),
          level: normalizeString(entry?.level),
          years_of_experience: entry?.years_of_experience != null ? String(entry.years_of_experience) : "",
          aliases: normalizeStringList(entry?.aliases),
          evidence_sources: normalizeStringList(entry?.evidence_sources),
        }))
      : emptyState.skill_entries,
    education_entries: Array.isArray(profile?.education_entries)
      ? profile.education_entries.map((entry) => ({
          [UI_ENTRY_ID_FIELD]: createUiEntryId("education"),
          institution_name: normalizeString(entry?.institution_name),
          degree: normalizeString(entry?.degree),
          field_of_study: normalizeString(entry?.field_of_study),
          start_date: normalizeString(entry?.start_date),
          end_date: normalizeString(entry?.end_date),
          is_current: Boolean(entry?.is_current),
        }))
      : emptyState.education_entries,
    language_entries: Array.isArray(profile?.language_entries)
      ? profile.language_entries.map((entry) => ({
          [UI_ENTRY_ID_FIELD]: createUiEntryId("language"),
          language_name: normalizeString(entry?.language_name),
          proficiency_level: normalizeString(entry?.proficiency_level),
        }))
      : emptyState.language_entries,
    certificate_entries: Array.isArray(profile?.certificate_entries)
      ? profile.certificate_entries.map((entry) => ({
          [UI_ENTRY_ID_FIELD]: createUiEntryId("certificate"),
          certificate_name: normalizeString(entry?.certificate_name),
          issuer: normalizeString(entry?.issuer),
          issue_date: normalizeString(entry?.issue_date),
          notes: normalizeString(entry?.notes),
        }))
      : emptyState.certificate_entries,
    immutable_rules: {
      forbidden_skills: normalizeStringList(profile?.immutable_rules?.forbidden_skills),
      forbidden_claims: normalizeStringList(profile?.immutable_rules?.forbidden_claims),
      forbidden_certificates: normalizeStringList(profile?.immutable_rules?.forbidden_certificates),
      editing_rules_text: joinLines(profile?.immutable_rules?.editing_rules),
      editing_rules: normalizeStringList(profile?.immutable_rules?.editing_rules),
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
    ...splitLines(getLineListDraftValue(entry.responsibilities_text, entry.responsibilities)),
    ...splitLines(getLineListDraftValue(entry.achievements_text, entry.achievements)),
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
    ...splitLines(getLineListDraftValue(entry.outcomes_text, entry.outcomes)),
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
    soft_skill_entries: normalizeStringList(formState.soft_skill_entries),
    interest_entries: normalizeStringList(formState.interest_entries),
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
        responsibilities: splitLines(getLineListDraftValue(entry.responsibilities_text, entry.responsibilities)),
        achievements: splitLines(getLineListDraftValue(entry.achievements_text, entry.achievements)),
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
        outcomes: splitLines(getLineListDraftValue(entry.outcomes_text, entry.outcomes)),
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
      editing_rules: splitLines(
        getLineListDraftValue(formState.immutable_rules.editing_rules_text, formState.immutable_rules.editing_rules),
      ),
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
 * Render a compact date range label for repeatable record previews.
 *
 * @param {string | null | undefined} startDate Entry start date.
 * @param {string | null | undefined} endDate Entry end date.
 * @param {boolean} isCurrent Whether the entry is still active.
 * @returns {string} Readable date range.
 */
function formatEntryDateRange(startDate, endDate, isCurrent = false) {
  const normalizedStart = normalizeString(startDate) || "brak daty";
  const normalizedEnd = isCurrent ? "obecnie" : normalizeString(endDate) || "brak daty";
  return `${normalizedStart} - ${normalizedEnd}`;
}

/**
 * Build a readable label used in experience-editing affordances.
 *
 * @param {object} entry Experience entry draft.
 * @param {number} index Entry position used as fallback text.
 * @returns {string} Human-readable label.
 */
function buildExperienceEntryLabel(entry, index) {
  const positionTitle = normalizeString(entry.position_title) || `Doswiadczenie ${index + 1}`;
  const companyName = normalizeString(entry.company_name);
  return companyName ? `${positionTitle} w ${companyName}` : positionTitle;
}

/**
 * Build the current save-status banner shown above the profile form.
 *
 * @param {boolean} hasUnsavedChanges Whether the form has local edits not yet saved.
 * @param {number | null} lastSavedProfileId Last successfully saved profile ID.
 * @param {boolean} hasPendingExperienceDraft Whether one experience draft still needs explicit save or cancel.
 * @returns {{tone: string, text: string}} Save-status payload.
 */
function buildSaveStatus(
  hasUnsavedChanges,
  lastSavedProfileId,
  hasPendingExperienceDraft,
  isEditMode,
  editingProfileId,
  editingProfileLabel,
) {
  const profileContext = editingProfileLabel || `profil ID ${editingProfileId}`;

  if (hasPendingExperienceDraft) {
    return {
      tone: "warning",
      text: "Masz otwarty formularz doświadczenia. Najpierw kliknij \"Zapisz doświadczenie\" lub \"Zapisz zmiany\", albo \"Anuluj\", a dopiero potem zapisz cały profil.",
    };
  }

  if (isEditMode && hasUnsavedChanges) {
    return {
      tone: "warning",
      text: `Edytujesz istniejący ${profileContext}. Masz niezapisane zmiany. Kliknij "Zapisz zmiany", aby zaktualizowac ten rekord, albo "Anuluj edycje", aby wrocic do nowego profilu.`,
    };
  }

  if (isEditMode && lastSavedProfileId === editingProfileId) {
    return {
      tone: "success",
      text: `Edytujesz istniejący ${profileContext}. Ostatnia aktualizacja zostala zapisana w tym samym rekordzie.`,
    };
  }

  if (isEditMode) {
    return {
      tone: "info",
      text: `Edytujesz istniejący ${profileContext}. Kliknij "Zapisz zmiany", aby zaktualizowac ten rekord, albo "Anuluj edycje", aby wrocic do tworzenia nowego profilu.`,
    };
  }

  if (hasUnsavedChanges) {
    return {
      tone: "warning",
      text: "Masz niezapisane zmiany. Wszystkie sekcje profilu, w tym podsumowanie zawodowe, zapisują się dopiero po kliknieciu \"Zapisz profil\".",
    };
  }

  if (lastSavedProfileId != null) {
    return {
      tone: "success",
      text: `Wszystkie zmiany formularza zostaly zapisane. Ostatni zapis ma ID ${lastSavedProfileId}.`,
    };
  }

  return {
    tone: "info",
    text: "Wszystkie sekcje formularza zapisują się jednym przyciskiem: \"Zapisz profil\".",
  };
}

/**
 * Render a textarea that keeps multiline content in form state until save time.
 *
 * @param {{
 *   label: string,
 *   value: string,
 *   onChange: (value: string) => void,
 *   placeholder?: string,
 *   rows?: number,
 * }} props Component props.
 * @returns {JSX.Element} Multiline list editor.
 */
function LineListField({ label, value, onChange, placeholder = "Kazda linia to osobna pozycja", rows = 4 }) {
  return (
    <label className="field">
      <span>{label}</span>
      <textarea
        className="form-textarea compact-textarea"
        rows={rows}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
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
 *   hasUnsavedChanges: boolean,
 *   lastSavedProfileId: number | null,
 *   isEditMode: boolean,
 *   editingProfileId: number | null,
 *   editingProfileLabel: string,
 *   onCancelEdit: () => void,
 * }} props Component props.
 * @returns {JSX.Element} Candidate-profile form.
 */
export default function CandidateProfileForm({
  formValue,
  onChange,
  onSave,
  saveLoading,
  hasUnsavedChanges,
  lastSavedProfileId,
  isEditMode,
  editingProfileId,
  editingProfileLabel,
  onCancelEdit,
}) {
  const profilePreview = buildCandidateProfilePayload(formValue);
  const [experienceDraft, setExperienceDraft] = useState(null);
  const [highlightedExperienceEntryId, setHighlightedExperienceEntryId] = useState(null);
  const isProfileSaveBlockedByExperienceDraft = experienceDraft !== null;
  const saveStatus = buildSaveStatus(
    hasUnsavedChanges,
    lastSavedProfileId,
    isProfileSaveBlockedByExperienceDraft,
    isEditMode,
    editingProfileId,
    editingProfileLabel,
  );

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
   * @param {string | string[]} values Updated field value.
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

  useEffect(() => {
    setExperienceDraft(null);
    setHighlightedExperienceEntryId(null);
  }, [editingProfileId, isEditMode]);

  /**
   * Clear the local experience draft when its source entry disappears from the list.
   *
   * @returns {void} No return value.
   */
  useEffect(() => {
    if (experienceDraft?.mode !== "edit") {
      return;
    }

    const hasSourceEntry = formValue.experience_entries.some((entry) => entry.id === experienceDraft.value.id);
    if (!hasSourceEntry) {
      setExperienceDraft(null);
    }
  }, [experienceDraft, formValue.experience_entries]);

  /**
   * Check whether the current experience draft contains unsaved changes.
   *
   * @returns {boolean} True when discarding the draft would lose user input.
   */
  function hasUnsavedExperienceDraftChanges() {
    if (!experienceDraft) {
      return false;
    }

    if (experienceDraft.mode === "create") {
      return !isEmptyExperienceEntry(experienceDraft.value);
    }

    const originalEntry = formValue.experience_entries.find((entry) => entry.id === experienceDraft.value.id);
    if (!originalEntry) {
      return !isEmptyExperienceEntry(experienceDraft.value);
    }

    return JSON.stringify(cloneExperienceEntry(originalEntry)) !== JSON.stringify(cloneExperienceEntry(experienceDraft.value));
  }

  /**
   * Ask for confirmation before discarding the current experience draft when needed.
   *
   * @returns {boolean} True when it is safe to replace the draft.
   */
  function confirmExperienceDraftDiscard() {
    if (!hasUnsavedExperienceDraftChanges()) {
      return true;
    }

    return window.confirm("Masz niezapisane zmiany w formularzu doświadczenia. Czy chcesz je porzucić?");
  }

  /**
   * Start a new experience draft that is not yet added to the profile list.
   *
   * @returns {void} No return value.
   */
  function handleAddExperienceEntry() {
    if (!confirmExperienceDraftDiscard()) {
      return;
    }

    setExperienceDraft({
      mode: "create",
      value: createEmptyExperienceEntry(),
    });
    setHighlightedExperienceEntryId(null);
  }

  /**
   * Start editing one existing saved experience entry from the list.
   *
   * @param {number} index Entry index to edit.
   * @returns {void} No return value.
   */
  function handleEditExperienceEntry(index) {
    const entry = formValue.experience_entries[index];
    if (!entry) {
      return;
    }

    if (!confirmExperienceDraftDiscard()) {
      return;
    }

    setExperienceDraft({
      mode: "edit",
      sourceEntryId: entry.id,
      value: cloneExperienceEntry(entry),
    });
    setHighlightedExperienceEntryId(entry.id);
  }

  /**
   * Update one field inside the local experience draft.
   *
   * @param {string} fieldName Experience field name.
   * @param {unknown} value New draft value.
   * @returns {void} No return value.
   */
  function updateExperienceDraftField(fieldName, value) {
    setExperienceDraft((currentDraft) =>
      currentDraft
        ? {
            ...currentDraft,
            value: {
              ...currentDraft.value,
              [fieldName]: value,
            },
          }
        : currentDraft,
    );
  }

  /**
   * Save the current experience draft to the profile list and close the editor.
   *
   * @returns {void} No return value.
   */
  function handleSaveExperienceDraft() {
    if (!experienceDraft) {
      return;
    }

    const savedEntry = cloneExperienceEntry(experienceDraft.value);
    const nextExperienceEntries =
      experienceDraft.mode === "edit"
        ? formValue.experience_entries.map((entry) => (entry.id === experienceDraft.sourceEntryId ? savedEntry : entry))
        : [...formValue.experience_entries, savedEntry];

    onChange({
      ...formValue,
      experience_entries: nextExperienceEntries,
    });
    setExperienceDraft(null);
    setHighlightedExperienceEntryId(savedEntry.id);
  }

  /**
   * Discard the local experience draft and return to the list-only state.
   *
   * @returns {void} No return value.
   */
  function handleCancelExperienceDraft() {
    if (!experienceDraft) {
      return;
    }

    setHighlightedExperienceEntryId(experienceDraft.mode === "edit" ? experienceDraft.sourceEntryId : null);
    setExperienceDraft(null);
  }

  /**
   * Remove one experience record after explicit user confirmation.
   *
   * @param {number} index Entry index to remove.
   * @returns {void} No return value.
   */
  function handleRemoveExperienceEntry(index) {
    const entry = formValue.experience_entries[index];
    if (!entry) {
      return;
    }

    const label = buildExperienceEntryLabel(entry, index);
    if (!window.confirm(`Czy na pewno usunac wpis: ${label}?`)) {
      return;
    }

    if (experienceDraft?.mode === "edit" && experienceDraft.sourceEntryId === entry.id) {
      setExperienceDraft(null);
    }

    if (highlightedExperienceEntryId === entry.id) {
      setHighlightedExperienceEntryId(null);
    }

    removeCollectionEntry("experience_entries", index);
  }

  return (
    <div className="profile-form-stack">
      <div className="section-header section-header-inline">
        <div>
          <h3>{isEditMode ? "Edycja profilu" : "Formularz profilu"}</h3>
          <p className="section-copy">
            {isEditMode
              ? `Aktualizujesz istniejacy rekord${editingProfileId != null ? ` o ID ${editingProfileId}` : ""}.`
              : "Uzupelnij profil kandydata i zapisz go do dalszej analizy."}
          </p>
        </div>
        <div className="actions profile-form-header-actions">
          {isEditMode ? (
            <button type="button" className="ghost-button" onClick={onCancelEdit} disabled={saveLoading}>
              Anuluj edycje
            </button>
          ) : null}
          <button
            type="button"
            className="primary-button"
            onClick={onSave}
            disabled={saveLoading || isProfileSaveBlockedByExperienceDraft}
          >
            {saveLoading ? "Zapisywanie..." : isEditMode ? "Zapisz zmiany" : "Zapisz profil"}
          </button>
        </div>
      </div>

      <div className={`message ${saveStatus.tone}`}>{saveStatus.text}</div>

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
          <button type="button" className="ghost-button" onClick={handleAddExperienceEntry}>
            Dodaj doswiadczenie
          </button>
        </div>

        {formValue.experience_entries.length > 0 || experienceDraft ? (
          <div className="record-list">
            {formValue.experience_entries.length > 0 ? (
              <div className="record-list experience-summary-list">
                {formValue.experience_entries.map((entry, index) => {
                  const isActive =
                    highlightedExperienceEntryId === entry.id ||
                    (experienceDraft?.mode === "edit" && experienceDraft.sourceEntryId === entry.id);
                  const responsibilityCount = splitLines(
                    getLineListDraftValue(entry.responsibilities_text, entry.responsibilities),
                  ).length;
                  const achievementsCount = splitLines(
                    getLineListDraftValue(entry.achievements_text, entry.achievements),
                  ).length;

                  return (
                    <article key={entry.id} className={`record-card compact-record-card${isActive ? " active-record-card" : ""}`}>
                      <div className="record-card-header">
                        <div>
                          <h4>{entry.position_title || `Doswiadczenie ${index + 1}`}</h4>
                          <p>{entry.company_name || "Nowy wpis"}</p>
                        </div>

                        <div className="record-card-actions">
                          <button type="button" className="ghost-button" onClick={() => handleEditExperienceEntry(index)}>
                            {experienceDraft?.mode === "edit" && experienceDraft.sourceEntryId === entry.id ? "Edytujesz" : "Edytuj"}
                          </button>
                          <button
                            type="button"
                            className="ghost-button danger-ghost-button"
                            onClick={() => handleRemoveExperienceEntry(index)}
                          >
                            Usun
                          </button>
                        </div>
                      </div>

                      <dl className="detail-grid record-preview-grid">
                        <div>
                          <dt>Zakres dat</dt>
                          <dd>{formatEntryDateRange(entry.start_date, entry.end_date, entry.is_current)}</dd>
                        </div>
                        <div>
                          <dt>Lokalizacja</dt>
                          <dd>{entry.location || "Brak lokalizacji"}</dd>
                        </div>
                        <div>
                          <dt>Obowiazki</dt>
                          <dd>{responsibilityCount > 0 ? `${responsibilityCount} pozycji` : "Brak"}</dd>
                        </div>
                        <div>
                          <dt>Osiągnięcia</dt>
                          <dd>{achievementsCount > 0 ? `${achievementsCount} pozycji` : "Brak"}</dd>
                        </div>
                      </dl>
                    </article>
                  );
                })}
              </div>
            ) : (
              <p className="placeholder">Brak jeszcze zapisanych wpisow doswiadczenia.</p>
            )}

            {experienceDraft ? (
              <article className="record-card record-editor-card">
                <div className="record-card-header">
                  <div>
                    <h4>{experienceDraft.mode === "edit" ? "Edytowane doswiadczenie" : "Nowe doswiadczenie"}</h4>
                    <p>
                      {experienceDraft.mode === "edit"
                        ? buildExperienceEntryLabel(
                            experienceDraft.value,
                            formValue.experience_entries.findIndex((entry) => entry.id === experienceDraft.sourceEntryId),
                          )
                        : "Wypelnij formularz i kliknij \"Zapisz doswiadczenie\", aby dodac wpis do listy."}
                    </p>
                  </div>
                  <span className="section-count-badge">
                    {formatEntryDateRange(
                      experienceDraft.value.start_date,
                      experienceDraft.value.end_date,
                      experienceDraft.value.is_current,
                    )}
                  </span>
                </div>

                <div className="form-grid">
                  <label className="field">
                    <span>Firma</span>
                    <input
                      type="text"
                      value={experienceDraft.value.company_name}
                      onChange={(event) => updateExperienceDraftField("company_name", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Stanowisko</span>
                    <input
                      type="text"
                      value={experienceDraft.value.position_title}
                      onChange={(event) => updateExperienceDraftField("position_title", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Data rozpoczecia</span>
                    <input
                      type="date"
                      value={experienceDraft.value.start_date}
                      onChange={(event) => updateExperienceDraftField("start_date", event.target.value)}
                    />
                  </label>

                  <label className="field">
                    <span>Data zakonczenia</span>
                    <input
                      type="date"
                      value={experienceDraft.value.end_date}
                      disabled={experienceDraft.value.is_current}
                      onChange={(event) => updateExperienceDraftField("end_date", event.target.value)}
                    />
                  </label>

                  <label className="field section-wide-field">
                    <span>Lokalizacja</span>
                    <input
                      type="text"
                      value={experienceDraft.value.location}
                      onChange={(event) => updateExperienceDraftField("location", event.target.value)}
                    />
                  </label>
                </div>

                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={experienceDraft.value.is_current}
                    onChange={(event) => updateExperienceDraftField("is_current", event.target.checked)}
                  />
                  <span>To jest moje obecne stanowisko</span>
                </label>

                <LineListField
                  label="Zakres obowiazkow"
                  value={getLineListDraftValue(
                    experienceDraft.value.responsibilities_text,
                    experienceDraft.value.responsibilities,
                  )}
                  onChange={(value) => updateExperienceDraftField("responsibilities_text", value)}
                  placeholder="Kazda linia to osobny obowiazek"
                />

                <LineListField
                  label="Osiągnięcia"
                  value={getLineListDraftValue(experienceDraft.value.achievements_text, experienceDraft.value.achievements)}
                  onChange={(value) => updateExperienceDraftField("achievements_text", value)}
                  placeholder="Kazda linia to osobne osiągnięcie"
                />

                <div className="form-grid">
                  <TagListInput
                    label="Technologie"
                    items={experienceDraft.value.technologies_used}
                    onChange={(items) => updateExperienceDraftField("technologies_used", items)}
                    placeholder="Np. Python"
                    addLabel="Dodaj technologie"
                  />

                  <TagListInput
                    label="Slowa kluczowe"
                    items={experienceDraft.value.keywords}
                    onChange={(items) => updateExperienceDraftField("keywords", items)}
                    placeholder="Np. API"
                    addLabel="Dodaj slowo"
                  />
                </div>

                <div className="actions experience-editor-actions">
                  <button type="button" className="ghost-button" onClick={handleCancelExperienceDraft}>
                    Anuluj
                  </button>
                  <button type="button" className="primary-button" onClick={handleSaveExperienceDraft}>
                    {experienceDraft.mode === "edit" ? "Zapisz zmiany" : "Zapisz doświadczenie"}
                  </button>
                </div>

                <p className="helper-text">
                  Ten wpis nie trafi do listy doświadczeń ani do zapisu profilu, dopóki nie klikniesz
                  {" "}
                  {experienceDraft.mode === "edit" ? "\"Zapisz zmiany\"" : "\"Zapisz doświadczenie\""}
                  {" "}
                  albo "Anuluj".
                </p>
              </article>
            ) : null}
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
                  value={getLineListDraftValue(entry.outcomes_text, entry.outcomes)}
                  onChange={(value) => updateCollectionEntry("project_entries", index, "outcomes_text", value)}
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
        title="Soft skills"
        description="Jawnie wpisane umiejetnosci miekkie, ktore chcesz pokazac w profilu."
        summary={`${formValue.soft_skill_entries.length} pozycji`}
      >
        <TagListInput
          label="Soft skills"
          items={formValue.soft_skill_entries}
          onChange={(items) => updateTopLevelField("soft_skill_entries", items)}
          placeholder="Np. communication"
          addLabel="Dodaj soft skill"
        />
      </FormSection>

      <FormSection
        title="Obszary zainteresowań"
        description="Tematy, dziedziny i obszary, ktore chcesz jawnie powiazac ze swoim profilem."
        summary={`${formValue.interest_entries.length} pozycji`}
      >
        <TagListInput
          label="Obszary zainteresowań"
          items={formValue.interest_entries}
          onChange={(items) => updateTopLevelField("interest_entries", items)}
          placeholder="Np. automation"
          addLabel="Dodaj obszar"
        />
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
            value={getLineListDraftValue(
              formValue.immutable_rules.editing_rules_text,
              formValue.immutable_rules.editing_rules,
            )}
            onChange={(value) => updateImmutableRules("editing_rules_text", value)}
            placeholder="Kazda linia to osobna zasada"
            rows={4}
          />
        </div>
      </FormSection>

      <RawJsonPanel
        className="raw-json-toggle profile-json-preview"
        summary="Podglad danych technicznych"
        value={profilePreview}
      />

      <div className="actions section-actions-bottom">
        {isEditMode ? (
          <button type="button" className="ghost-button" onClick={onCancelEdit} disabled={saveLoading}>
            Anuluj edycje
          </button>
        ) : null}
        <button
          type="button"
          className="primary-button"
          onClick={onSave}
          disabled={saveLoading || isProfileSaveBlockedByExperienceDraft}
        >
          {saveLoading ? "Zapisywanie..." : isEditMode ? "Zapisz zmiany" : "Zapisz profil"}
        </button>
      </div>
    </div>
  );
}
