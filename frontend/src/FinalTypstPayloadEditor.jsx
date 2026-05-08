/**
 * Human-friendly editor for the final Typst CV payload.
 */

function getLimit(limitConfig, sectionName, targetKey, hardKey) {
  const section = limitConfig?.[sectionName];
  if (!section || typeof section !== "object") {
    return null;
  }

  const target = typeof section[targetKey] === "number" ? section[targetKey] : null;
  const hard = typeof section[hardKey] === "number" ? section[hardKey] : null;
  if (target === null && hard === null) {
    return null;
  }
  return { target, hard };
}

function getTextLength(value) {
  return String(value ?? "").length;
}

function CharacterCounter({ value, limit, countedValue = null }) {
  const count = getTextLength(countedValue ?? value);
  const exceedsHard = typeof limit?.hard === "number" && count > limit.hard;
  const exceedsTarget = typeof limit?.target === "number" && count > limit.target;
  const className = [
    "char-counter",
    exceedsHard ? "error" : "",
    !exceedsHard && exceedsTarget ? "warning" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <p className={className}>
      {count} znaków
      {exceedsHard ? " · Przekroczony limit dla PDF" : ""}
    </p>
  );
}

function EmptySection({ children }) {
  return <p className="placeholder">{children}</p>;
}

export default function FinalTypstPayloadEditor({
  payload,
  limitConfig,
  sourceLabel,
  onChange,
  onRender,
  onReset,
  onClearAutosave,
  renderLoading,
  autosaveStatus,
}) {
  if (!payload) {
    return <p className="placeholder">Otwórz edytor, aby poprawić finalną wersję CV.</p>;
  }

  const summaryLimit = getLimit(limitConfig, "summary", "target_chars", "hard_chars");
  const thesisLimit = getLimit(limitConfig, "education", "thesis_target_chars", "thesis_hard_chars");
  const experienceBulletLimit = getLimit(limitConfig, "experience", "bullet_target_chars", "bullet_hard_chars");
  const experienceDateLimit = getLimit(limitConfig, "experience", "date_hard_chars", "date_hard_chars");
  const experienceHeaderLimit = getLimit(
    limitConfig,
    "experience",
    "header_left_target_chars",
    "header_left_hard_chars",
  );
  const projectTotalLimit = getLimit(limitConfig, "projects", "entry_total_target_chars", "entry_total_hard_chars");
  const skillLimit = getLimit(limitConfig, "skills", "entry_target_chars", "entry_hard_chars");
  const languageCertificateLimit = getLimit(
    limitConfig,
    "languages_certificates",
    "entry_target_chars",
    "entry_hard_chars",
  );

  const educationEntries = payload.education_entries ?? [];
  const experienceEntries = payload.experience_entries ?? [];
  const projectEntries = payload.project_entries ?? [];
  const skillEntries = payload.skill_entries ?? [];
  const languageCertificateEntries = payload.language_certificate_entries ?? [];

  function updatePayloadField(fieldName, nextValue) {
    onChange({
      ...payload,
      [fieldName]: nextValue,
    });
  }

  function updateEntry(listName, index, fieldName, nextValue) {
    const nextEntries = [...(payload[listName] ?? [])];
    nextEntries[index] = {
      ...nextEntries[index],
      [fieldName]: nextValue,
    };
    onChange({
      ...payload,
      [listName]: nextEntries,
    });
  }

  function updateExperienceBullet(entryIndex, bulletIndex, nextValue) {
    const nextEntries = [...experienceEntries];
    const currentEntry = nextEntries[entryIndex] ?? {};
    const nextBullets = [...(currentEntry.bullets ?? [])];
    nextBullets[bulletIndex] = nextValue;
    nextEntries[entryIndex] = {
      ...currentEntry,
      bullets: nextBullets,
    };
    onChange({
      ...payload,
      experience_entries: nextEntries,
    });
  }

  function updateStringListEntry(listName, index, nextValue) {
    const nextValues = [...(payload[listName] ?? [])];
    nextValues[index] = nextValue;
    onChange({
      ...payload,
      [listName]: nextValues,
    });
  }

  return (
    <div className="final-editor">
      <div className="message info">
        Edycja ręczna zmienia tylko finalny dokument PDF. Nie zmienia profilu kandydata ani zapisanego draftu.
        Zmiany są zapisywane lokalnie w tej przeglądarce.
      </div>

      {autosaveStatus ? (
        <div className={`message ${autosaveStatus.type}`}>{autosaveStatus.text}</div>
      ) : null}

      <div className="manual-editor-source">
        <span className="status-badge success">Źródło edycji</span>
        <p className="helper-text">{sourceLabel}</p>
      </div>

      <section className="final-editor-section">
        <div className="section-header">
          <h4>Podsumowanie</h4>
        </div>
        <label className="field">
          <span>Profil zawodowy</span>
          <textarea
            className="form-textarea compact-textarea"
            value={payload.summary_text ?? ""}
            onChange={(event) => updatePayloadField("summary_text", event.target.value)}
          />
          <CharacterCounter value={payload.summary_text} limit={summaryLimit} />
        </label>
      </section>

      <section className="final-editor-section">
        <div className="section-header">
          <h4>Edukacja</h4>
        </div>
        {educationEntries.length ? (
          <div className="record-list compact-record-list">
            {educationEntries.map((entry, index) => (
              <article className="record-card compact-record-card" key={`education-${index}`}>
                <div className="record-card-header">
                  <div>
                    <h5>{entry.institution || `Edukacja ${index + 1}`}</h5>
                    <p>{[entry.degree, entry.date].filter(Boolean).join(" · ") || "Brak szczegółów"}</p>
                  </div>
                </div>
                <label className="field">
                  <span>Temat pracy / doprecyzowanie</span>
                  <textarea
                    className="form-textarea compact-textarea"
                    value={entry.thesis ?? ""}
                    onChange={(event) => updateEntry("education_entries", index, "thesis", event.target.value)}
                  />
                  <CharacterCounter value={entry.thesis} limit={thesisLimit} />
                </label>
              </article>
            ))}
          </div>
        ) : (
          <EmptySection>Brak wpisów edukacji w danych dokumentu.</EmptySection>
        )}
      </section>

      <section className="final-editor-section">
        <div className="section-header">
          <h4>Doświadczenie</h4>
          <p className="section-copy">
            Firma, stanowisko i data wpływają tylko na finalny dokument. Edytuj wording, język lub literówki świadomie.
          </p>
        </div>
        {experienceEntries.length ? (
          <div className="record-list compact-record-list">
            {experienceEntries.map((entry, entryIndex) => (
              <article className="record-card compact-record-card" key={`experience-${entryIndex}`}>
                <div className="form-grid resume-form-grid">
                  <label className="field">
                    <span>Firma</span>
                    <input
                      type="text"
                      value={entry.company ?? ""}
                      onChange={(event) => updateEntry("experience_entries", entryIndex, "company", event.target.value)}
                    />
                    <CharacterCounter
                      value={entry.company}
                      countedValue={`${entry.company ?? ""} ${entry.role ?? ""}`.trim()}
                      limit={experienceHeaderLimit}
                    />
                  </label>
                  <label className="field">
                    <span>Stanowisko</span>
                    <input
                      type="text"
                      value={entry.role ?? ""}
                      onChange={(event) => updateEntry("experience_entries", entryIndex, "role", event.target.value)}
                    />
                    <CharacterCounter
                      value={entry.role}
                      countedValue={`${entry.company ?? ""} ${entry.role ?? ""}`.trim()}
                      limit={experienceHeaderLimit}
                    />
                  </label>
                  <label className="field section-wide-field">
                    <span>Data</span>
                    <input
                      type="text"
                      value={entry.date ?? ""}
                      onChange={(event) => updateEntry("experience_entries", entryIndex, "date", event.target.value)}
                    />
                    <CharacterCounter value={entry.date} limit={experienceDateLimit} />
                  </label>
                </div>
                <div className="final-editor-list">
                  {(entry.bullets ?? []).length ? (
                    entry.bullets.map((bullet, bulletIndex) => (
                      <label className="field" key={`experience-${entryIndex}-bullet-${bulletIndex}`}>
                        <span>Punkt {bulletIndex + 1}</span>
                        <textarea
                          className="form-textarea compact-textarea"
                          value={bullet ?? ""}
                          onChange={(event) => updateExperienceBullet(entryIndex, bulletIndex, event.target.value)}
                        />
                        <CharacterCounter value={bullet} limit={experienceBulletLimit} />
                      </label>
                    ))
                  ) : (
                    <EmptySection>Brak punktów do edycji w tym wpisie.</EmptySection>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptySection>Brak wpisów doświadczenia w danych dokumentu.</EmptySection>
        )}
      </section>

      <section className="final-editor-section">
        <div className="section-header">
          <h4>Projekty</h4>
          <p className="section-copy">
            Nazwa projektu wpływa tylko na finalny dokument. Edytuj wording, język lub literówki świadomie.
          </p>
        </div>
        {projectEntries.length ? (
          <div className="record-list compact-record-list">
            {projectEntries.map((entry, index) => {
              const countedProjectText = `${entry.name ?? ""} ${entry.description ?? ""}`.trim();
              return (
                <article className="record-card compact-record-card" key={`project-${index}`}>
                  <label className="field">
                    <span>Nazwa projektu</span>
                    <input
                      type="text"
                      value={entry.name ?? ""}
                      onChange={(event) => updateEntry("project_entries", index, "name", event.target.value)}
                    />
                    <CharacterCounter value={entry.name} countedValue={countedProjectText} limit={projectTotalLimit} />
                  </label>
                  <label className="field">
                    <span>Opis projektu</span>
                    <textarea
                      className="form-textarea compact-textarea"
                      value={entry.description ?? ""}
                      onChange={(event) => updateEntry("project_entries", index, "description", event.target.value)}
                    />
                    <CharacterCounter
                      value={entry.description}
                      countedValue={countedProjectText}
                      limit={projectTotalLimit}
                    />
                  </label>
                </article>
              );
            })}
          </div>
        ) : (
          <EmptySection>Brak projektów w danych dokumentu.</EmptySection>
        )}
      </section>

      <section className="final-editor-section">
        <div className="section-header">
          <h4>Umiejętności</h4>
        </div>
        {skillEntries.length ? (
          <div className="final-editor-list">
            {skillEntries.map((item, index) => (
              <label className="field" key={`skill-${index}`}>
                <span>Linia umiejętności {index + 1}</span>
                <input
                  type="text"
                  value={item ?? ""}
                  onChange={(event) => updateStringListEntry("skill_entries", index, event.target.value)}
                />
                <CharacterCounter value={item} limit={skillLimit} />
              </label>
            ))}
          </div>
        ) : (
          <EmptySection>Brak linii umiejętności w danych dokumentu.</EmptySection>
        )}
      </section>

      <section className="final-editor-section">
        <div className="section-header">
          <h4>Języki i certyfikaty</h4>
        </div>
        {languageCertificateEntries.length ? (
          <div className="final-editor-list">
            {languageCertificateEntries.map((item, index) => (
              <label className="field" key={`language-certificate-${index}`}>
                <span>Wpis {index + 1}</span>
                <input
                  type="text"
                  value={item ?? ""}
                  onChange={(event) => updateStringListEntry("language_certificate_entries", index, event.target.value)}
                />
                <CharacterCounter value={item} limit={languageCertificateLimit} />
              </label>
            ))}
          </div>
        ) : (
          <EmptySection>Brak języków lub certyfikatów w danych dokumentu.</EmptySection>
        )}
      </section>

      <div className="manual-editor-actions">
        <button type="button" className="primary-button" onClick={onRender} disabled={renderLoading}>
          {renderLoading ? "Generowanie..." : "Wygeneruj PDF z edycji"}
        </button>
        <button type="button" className="ghost-button" onClick={onReset} disabled={renderLoading}>
          Przywróć wersję AI
        </button>
        <button type="button" className="ghost-button danger-ghost-button" onClick={onClearAutosave} disabled={renderLoading}>
          Wyczyść zapis roboczy
        </button>
      </div>
    </div>
  );
}
