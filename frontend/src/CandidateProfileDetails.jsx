/**
 * Structured presentation of a stored CandidateProfile with helper raw JSON preview.
 */

/**
 * Build compact profile summary items for the top metadata grid.
 *
 * @param {object} profile Stored CandidateProfile payload.
 * @returns {Array<{label: string, value: string}>} Summary items for the detail header.
 */
function buildProfileSummaryItems(profile) {
  return [
    { label: "Email", value: profile?.personal_info?.email || "brak" },
    { label: "Telefon", value: profile?.personal_info?.phone || "brak" },
    { label: "Lokalizacja", value: profile?.personal_info?.location || "brak" },
    { label: "Role docelowe", value: String(Array.isArray(profile?.target_roles) ? profile.target_roles.length : 0) },
    {
      label: "Doswiadczenie",
      value: String(Array.isArray(profile?.experience_entries) ? profile.experience_entries.length : 0),
    },
    { label: "Projekty", value: String(Array.isArray(profile?.project_entries) ? profile.project_entries.length : 0) },
  ];
}

/**
 * Render a compact date range for experience and education cards.
 *
 * @param {string | null | undefined} startDate Entry start date.
 * @param {string | null | undefined} endDate Entry end date.
 * @param {boolean} isCurrent Whether the entry is still active.
 * @returns {string} Readable date range label.
 */
function formatDateRange(startDate, endDate, isCurrent = false) {
  const normalizedStart = startDate || "brak daty";
  const normalizedEnd = isCurrent ? "obecnie" : endDate || "brak daty";
  return `${normalizedStart} - ${normalizedEnd}`;
}

/**
 * Render one reusable chip list or a placeholder when the list is empty.
 *
 * @param {{items: string[], emptyLabel: string}} props Component props.
 * @returns {JSX.Element} Chip group or placeholder.
 */
function ChipList({ items, emptyLabel }) {
  return items.length > 0 ? (
    <div className="chip-row">
      {items.map((item, index) => (
        <span key={`${item}-${index}`} className="chip accent">
          {item}
        </span>
      ))}
    </div>
  ) : (
    <p className="placeholder">{emptyLabel}</p>
  );
}

/**
 * Render the structured detail view of a stored CandidateProfile.
 *
 * @param {{profile: object}} props Component props.
 * @returns {JSX.Element} Structured CandidateProfile detail section.
 */
export default function CandidateProfileDetails({ profile }) {
  const summaryItems = buildProfileSummaryItems(profile);
  const targetRoles = Array.isArray(profile?.target_roles) ? profile.target_roles : [];
  const experienceEntries = Array.isArray(profile?.experience_entries) ? profile.experience_entries : [];
  const projectEntries = Array.isArray(profile?.project_entries) ? profile.project_entries : [];
  const skillEntries = Array.isArray(profile?.skill_entries) ? profile.skill_entries : [];
  const educationEntries = Array.isArray(profile?.education_entries) ? profile.education_entries : [];
  const languageEntries = Array.isArray(profile?.language_entries) ? profile.language_entries : [];
  const certificateEntries = Array.isArray(profile?.certificate_entries) ? profile.certificate_entries : [];
  const immutableRules = profile?.immutable_rules ?? {};

  return (
    <div className="profile-details">
      <header className="detail-header">
        <div>
          <h3 className="detail-title">{profile.personal_info?.full_name || "Brak imienia i nazwiska"}</h3>
          <p className="detail-company">{profile.personal_info?.email || "Brak emaila"}</p>
        </div>
        {targetRoles.length > 0 ? (
          <div className="chip-row">
            {targetRoles.map((role, index) => (
              <span key={`${role}-${index}`} className="chip muted">
                {role}
              </span>
            ))}
          </div>
        ) : null}
      </header>

      <dl className="detail-main-grid">
        {summaryItems.map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>

      <section className="detail-section">
        <h4>Podsumowanie zawodowe</h4>
        <p className="detail-text">{profile.professional_summary_base || "Brak podsumowania zawodowego."}</p>
      </section>

      <section className="detail-section">
        <h4>Doswiadczenie zawodowe</h4>
        {experienceEntries.length > 0 ? (
          <div className="record-list">
            {experienceEntries.map((entry) => (
              <article key={entry.id} className="record-card compact-record-card">
                <div className="record-card-header">
                  <div>
                    <h4>{entry.position_title}</h4>
                    <p>{entry.company_name}</p>
                  </div>
                  <span className="chip muted">{formatDateRange(entry.start_date, entry.end_date, entry.is_current)}</span>
                </div>

                <p className="helper-text">{entry.location || "Brak lokalizacji"}</p>

                <div className="detail-section compact-detail-section">
                  <h5>Obowiazki</h5>
                  {entry.responsibilities.length > 0 ? (
                    <ul className="detail-list">
                      {entry.responsibilities.map((item, index) => (
                        <li key={`${item}-${index}`}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="placeholder">Brak zapisanych obowiazkow.</p>
                  )}
                </div>

                <div className="detail-section compact-detail-section">
                  <h5>Osiągnięcia</h5>
                  {entry.achievements.length > 0 ? (
                    <ul className="detail-list">
                      {entry.achievements.map((item, index) => (
                        <li key={`${item}-${index}`}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="placeholder">Brak zapisanych osiągnięć.</p>
                  )}
                </div>

                <ChipList items={entry.technologies_used} emptyLabel="Brak technologii." />
                <ChipList items={entry.keywords} emptyLabel="Brak slow kluczowych." />
              </article>
            ))}
          </div>
        ) : (
          <p className="placeholder">Brak zapisanych doswiadczen zawodowych.</p>
        )}
      </section>

      <section className="detail-section">
        <h4>Projekty</h4>
        {projectEntries.length > 0 ? (
          <div className="record-list">
            {projectEntries.map((entry) => (
              <article key={entry.id} className="record-card compact-record-card">
                <div className="record-card-header">
                  <div>
                    <h4>{entry.project_name}</h4>
                    <p>{entry.role}</p>
                  </div>
                  {entry.link ? (
                    <a className="detail-link" href={entry.link} target="_blank" rel="noreferrer">
                      Otworz link
                    </a>
                  ) : null}
                </div>

                <p className="detail-text">{entry.description || "Brak opisu projektu."}</p>

                <div className="detail-section compact-detail-section">
                  <h5>Rezultaty</h5>
                  {entry.outcomes.length > 0 ? (
                    <ul className="detail-list">
                      {entry.outcomes.map((item, index) => (
                        <li key={`${item}-${index}`}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="placeholder">Brak zapisanych rezultatow.</p>
                  )}
                </div>

                <ChipList items={entry.technologies_used} emptyLabel="Brak technologii." />
                <ChipList items={entry.keywords} emptyLabel="Brak slow kluczowych." />
              </article>
            ))}
          </div>
        ) : (
          <p className="placeholder">Brak zapisanych projektow.</p>
        )}
      </section>

      <div className="result-columns">
        <section className="detail-section">
          <h4>Umiejetnosci</h4>
          {skillEntries.length > 0 ? (
            <div className="record-list compact-record-list">
              {skillEntries.map((entry, index) => (
                <article key={`skill-${index}`} className="record-card compact-record-card skill-card">
                  <div className="record-card-header">
                    <div>
                      <h4>{entry.name || `Umiejetnosc ${index + 1}`}</h4>
                      <p>{entry.category || "Brak kategorii"}</p>
                    </div>
                    {entry.level ? <span className="chip muted">{entry.level}</span> : null}
                  </div>

                  <dl className="detail-grid skill-meta-grid">
                    <div>
                      <dt>Kategoria</dt>
                      <dd>{entry.category || "Brak kategorii"}</dd>
                    </div>
                    <div>
                      <dt>Poziom</dt>
                      <dd>{entry.level || "Brak poziomu"}</dd>
                    </div>
                    <div>
                      <dt>Lata doswiadczenia</dt>
                      <dd>{entry.years_of_experience != null ? String(entry.years_of_experience) : "Brak danych"}</dd>
                    </div>
                  </dl>

                  <div className="skill-card-section">
                    <h5>Aliasy</h5>
                    <ChipList items={entry.aliases} emptyLabel="Brak aliasow." />
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <p className="placeholder">Brak zapisanych umiejetnosci.</p>
          )}
        </section>

        <section className="detail-section">
          <h4>Jezyki</h4>
          {languageEntries.length > 0 ? (
            <ul className="detail-list">
              {languageEntries.map((entry, index) => (
                <li key={`language-${index}`}>
                  {entry.language_name} - {entry.proficiency_level}
                </li>
              ))}
            </ul>
          ) : (
            <p className="placeholder">Brak zapisanych jezykow.</p>
          )}

          <h4>Edukacja</h4>
          {educationEntries.length > 0 ? (
            <div className="record-list compact-record-list">
              {educationEntries.map((entry, index) => (
                <article key={`education-${index}`} className="record-card compact-record-card">
                  <h4>{entry.institution_name}</h4>
                  <p className="helper-text">{entry.degree || "Brak stopnia"}</p>
                  <p className="detail-text">{entry.field_of_study || "Brak kierunku"}</p>
                  <p className="helper-text">{formatDateRange(entry.start_date, entry.end_date, entry.is_current)}</p>
                </article>
              ))}
            </div>
          ) : (
            <p className="placeholder">Brak zapisanej edukacji.</p>
          )}
        </section>
      </div>

      <section className="detail-section">
        <h4>Certyfikaty</h4>
        {certificateEntries.length > 0 ? (
          <div className="record-list compact-record-list">
            {certificateEntries.map((entry, index) => (
              <article key={`certificate-${index}`} className="record-card compact-record-card">
                <h4>{entry.certificate_name}</h4>
                <p className="helper-text">{entry.issuer || "Brak wydawcy"}</p>
                <p className="helper-text">{entry.issue_date || "Brak daty"}</p>
                {entry.notes ? <p className="detail-text">{entry.notes}</p> : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="placeholder">Brak zapisanych certyfikatow.</p>
        )}
      </section>

      <details className="raw-json-toggle">
        <summary>Reguly zaawansowane</summary>
        <div className="advanced-preview-grid">
          <div>
            <h4>Zakazane umiejetnosci</h4>
            <ChipList items={Array.isArray(immutableRules.forbidden_skills) ? immutableRules.forbidden_skills : []} emptyLabel="Brak ograniczen." />
          </div>
          <div>
            <h4>Zakazane stwierdzenia</h4>
            <ChipList items={Array.isArray(immutableRules.forbidden_claims) ? immutableRules.forbidden_claims : []} emptyLabel="Brak ograniczen." />
          </div>
          <div>
            <h4>Zakazane certyfikaty</h4>
            <ChipList items={Array.isArray(immutableRules.forbidden_certificates) ? immutableRules.forbidden_certificates : []} emptyLabel="Brak ograniczen." />
          </div>
          <div>
            <h4>Zasady edycji</h4>
            {Array.isArray(immutableRules.editing_rules) && immutableRules.editing_rules.length > 0 ? (
              <ul className="detail-list">
                {immutableRules.editing_rules.map((rule, index) => (
                  <li key={`${rule}-${index}`}>{rule}</li>
                ))}
              </ul>
            ) : (
              <p className="placeholder">Brak dodatkowych zasad.</p>
            )}
          </div>
        </div>
      </details>

      <details className="raw-json-toggle">
        <summary>Raw JSON zapisanego profilu</summary>
        <pre>{JSON.stringify(profile, null, 2)}</pre>
      </details>
    </div>
  );
}
