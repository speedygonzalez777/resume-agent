/**
 * Structured preview of a generated ResumeDraft.
 */

import RawJsonPanel from "./RawJsonPanel";

/**
 * Render a placeholder-friendly string list.
 *
 * @param {string[]} items List of strings to render.
 * @param {string} emptyText Fallback text shown when the list is empty.
 * @returns {JSX.Element} Rendered list or placeholder.
 */
function renderStringList(items, emptyText) {
  return items.length > 0 ? (
    <ul className="detail-list">
      {items.map((item, index) => (
        <li key={`${item}-${index}`}>{item}</li>
      ))}
    </ul>
  ) : (
    <p className="placeholder">{emptyText}</p>
  );
}

/**
 * Render the tailored ResumeDraft in a readable CV-like layout.
 *
 * @param {{resumeDraft: object}} props Component props.
 * @returns {JSX.Element} Structured resume draft preview.
 */
export default function ResumeDraftDetails({ resumeDraft }) {
  const header = resumeDraft?.header ?? {};
  const selectedSkills = Array.isArray(resumeDraft?.selected_skills) ? resumeDraft.selected_skills : [];
  const selectedSoftSkillEntries = Array.isArray(resumeDraft?.selected_soft_skill_entries)
    ? resumeDraft.selected_soft_skill_entries
    : [];
  const selectedInterestEntries = Array.isArray(resumeDraft?.selected_interest_entries)
    ? resumeDraft.selected_interest_entries
    : [];
  const selectedExperienceEntries = Array.isArray(resumeDraft?.selected_experience_entries)
    ? resumeDraft.selected_experience_entries
    : [];
  const selectedProjectEntries = Array.isArray(resumeDraft?.selected_project_entries)
    ? resumeDraft.selected_project_entries
    : [];
  const selectedEducationEntries = Array.isArray(resumeDraft?.selected_education_entries)
    ? resumeDraft.selected_education_entries
    : [];
  const selectedLanguageEntries = Array.isArray(resumeDraft?.selected_language_entries)
    ? resumeDraft.selected_language_entries
    : [];
  const selectedCertificateEntries = Array.isArray(resumeDraft?.selected_certificate_entries)
    ? resumeDraft.selected_certificate_entries
    : [];
  const selectedKeywords = Array.isArray(resumeDraft?.selected_keywords) ? resumeDraft.selected_keywords : [];
  const keywordUsage = Array.isArray(resumeDraft?.keyword_usage) ? resumeDraft.keyword_usage : [];
  const links = Array.isArray(header?.links) ? header.links : [];

  return (
    <div className="resume-draft-details">
      <section className="detail-section resume-preview-header-card">
        <span className="section-eyebrow">Draft CV</span>
        <div className="detail-header">
          <div>
            <h3 className="detail-title">{header.full_name || "Brak imienia i nazwiska"}</h3>
          </div>
        </div>

        <dl className="detail-grid">
          <div>
            <dt>E-mail</dt>
            <dd>{header.email || "brak"}</dd>
          </div>
          <div>
            <dt>Telefon</dt>
            <dd>{header.phone || "brak"}</dd>
          </div>
          <div>
            <dt>Lokalizacja</dt>
            <dd>{header.location || "brak"}</dd>
          </div>
          <div>
            <dt>Linki</dt>
            <dd>{links.length > 0 ? `${links.length} linki` : "brak"}</dd>
          </div>
        </dl>

        {links.length > 0 ? (
          <div className="chip-row">
            {links.map((link) => (
              <a key={link} className="detail-link" href={link} target="_blank" rel="noreferrer">
                {link}
              </a>
            ))}
          </div>
        ) : null}
      </section>

      <section className="detail-section">
        <h4>Podsumowanie</h4>
        <p className="detail-text">{resumeDraft?.professional_summary || "Brak summary do pokazania."}</p>
      </section>

      <section className="detail-section">
        <h4>Kluczowe umiejetnosci</h4>
        {selectedSkills.length > 0 ? (
          <div className="chip-row">
            {selectedSkills.map((skill) => (
              <span key={skill} className="chip accent">
                {skill}
              </span>
            ))}
          </div>
        ) : (
          <p className="placeholder">Brak wybranych umiejetnosci.</p>
        )}
      </section>

      {selectedSoftSkillEntries.length > 0 ? (
        <section className="detail-section">
          <h4>Soft skills</h4>
          <div className="chip-row">
            {selectedSoftSkillEntries.map((skill) => (
              <span key={skill} className="chip muted">
                {skill}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {selectedInterestEntries.length > 0 ? (
        <section className="detail-section">
          <h4>Obszary zainteresowan</h4>
          <div className="chip-row">
            {selectedInterestEntries.map((interest) => (
              <span key={interest} className="chip muted">
                {interest}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      <section className="detail-section">
        <h4>Wybrane doswiadczenia</h4>
        {selectedExperienceEntries.length > 0 ? (
          <div className="record-list compact-record-list">
            {selectedExperienceEntries.map((entry) => (
              <article key={entry.source_experience_id} className="record-card compact-record-card">
                <div className="record-card-header">
                  <div>
                    <h5>{entry.position_title}</h5>
                    <p>
                      {entry.company_name} - {entry.date_range}
                    </p>
                  </div>
                </div>

                {renderStringList(entry.bullet_points || [], "Brak bullet points dla tego wpisu.")}

                {Array.isArray(entry.highlighted_keywords) && entry.highlighted_keywords.length > 0 ? (
                  <div className="detail-section compact-detail-section">
                    <h6>Wyeksponowane keywords</h6>
                    <div className="chip-row">
                      {entry.highlighted_keywords.map((keyword) => (
                        <span key={keyword} className="chip muted">
                          {keyword}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="placeholder">Brak doswiadczen wybranych do tego draftu.</p>
        )}
      </section>

      <section className="detail-section">
        <h4>Wybrane projekty</h4>
        {selectedProjectEntries.length > 0 ? (
          <div className="record-list compact-record-list">
            {selectedProjectEntries.map((entry) => (
              <article key={entry.source_project_id} className="record-card compact-record-card">
                <div className="record-card-header">
                  <div>
                    <h5>{entry.project_name}</h5>
                    <p>{entry.role || "Brak roli projektu"}</p>
                  </div>
                  {entry.link ? (
                    <a className="detail-link" href={entry.link} target="_blank" rel="noreferrer">
                      Project link
                    </a>
                  ) : null}
                </div>

                {renderStringList(entry.bullet_points || [], "Brak bullet points dla tego projektu.")}

                {Array.isArray(entry.highlighted_keywords) && entry.highlighted_keywords.length > 0 ? (
                  <div className="detail-section compact-detail-section">
                    <h6>Wyeksponowane keywords</h6>
                    <div className="chip-row">
                      {entry.highlighted_keywords.map((keyword) => (
                        <span key={keyword} className="chip muted">
                          {keyword}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="placeholder">Brak projektow wybranych do tego draftu.</p>
        )}
      </section>

      <div className="result-columns">
        <section className="detail-section">
          <h4>Edukacja</h4>
          {renderStringList(selectedEducationEntries, "Brak edukacji wybranej do draftu.")}
        </section>

        <section className="detail-section">
          <h4>Jezyki</h4>
          {renderStringList(selectedLanguageEntries, "Brak jezykow wybranych do draftu.")}
        </section>
      </div>

      <div className="result-columns">
        <section className="detail-section">
          <h4>Certyfikaty</h4>
          {renderStringList(selectedCertificateEntries, "Brak certyfikatow wybranych do draftu.")}
        </section>

        <section className="detail-section">
          <h4>Wybrane keywords</h4>
          {selectedKeywords.length > 0 ? (
            <div className="chip-row">
              {selectedKeywords.map((keyword) => (
                <span key={keyword} className="chip muted">
                  {keyword}
                </span>
              ))}
            </div>
          ) : (
            <p className="placeholder">Brak wybranych keywords w draftcie.</p>
          )}
        </section>
      </div>

      <section className="detail-section">
        <h4>Uzyte keywords</h4>
        {keywordUsage.length > 0 ? (
          <div className="chip-row">
            {keywordUsage.map((keyword) => (
              <span key={keyword} className="chip accent">
                {keyword}
              </span>
            ))}
          </div>
        ) : (
          <p className="placeholder">Brak zarejestrowanych keywords w draftcie.</p>
        )}
        <p className="helper-text">
          To pole pomaga szybko sprawdzic, czy AI refinement nie rozmywa keywordow uzytych w dokumencie.
        </p>
      </section>

      <RawJsonPanel summary="Raw JSON ResumeDraft" value={resumeDraft} />
    </div>
  );
}
