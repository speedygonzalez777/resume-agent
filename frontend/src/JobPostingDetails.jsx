/**
 * Structured presentation of a JobPosting with a collapsible raw JSON block.
 */

import RawJsonPanel from "./RawJsonPanel";

const SHORT_DISPLAY_KEYWORD_CANONICAL_MAP = {
  ai: "AI",
  api: "API",
  aws: "AWS",
  bi: "BI",
  cad: "CAD",
  erp: "ERP",
  gcp: "GCP",
  hmi: "HMI",
  mes: "MES",
  ml: "ML",
  plc: "PLC",
  qa: "QA",
  sap: "SAP",
  sql: "SQL",
  ui: "UI",
  ux: "UX",
};
const MAX_VISIBLE_JOB_KEYWORDS = 12;

function normalizeDisplayKeyword(value) {
  return String(value ?? "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[,;: ]+|[,;: ]+$/g, "");
}

function buildDisplayKeywords(values) {
  const nextValues = [];
  const seenKeys = new Set();

  (Array.isArray(values) ? values : []).forEach((value) => {
    const normalizedKeyword = normalizeDisplayKeyword(value).toLowerCase();
    if (!normalizedKeyword) {
      return;
    }

    const isSingleAlphaToken = /^[a-z]+$/.test(normalizedKeyword);
    if (isSingleAlphaToken && normalizedKeyword.length < 4 && !(normalizedKeyword in SHORT_DISPLAY_KEYWORD_CANONICAL_MAP)) {
      return;
    }

    if (seenKeys.has(normalizedKeyword)) {
      return;
    }

    seenKeys.add(normalizedKeyword);
    nextValues.push(SHORT_DISPLAY_KEYWORD_CANONICAL_MAP[normalizedKeyword] ?? normalizeDisplayKeyword(value));
  });

  return nextValues.slice(0, MAX_VISIBLE_JOB_KEYWORDS);
}

/**
 * Split requirement items into must-have and nice-to-have groups.
 *
 * @param {object[]} requirements Raw requirement list from JobPosting.
 * @returns {{mustHave: object[], niceToHave: object[]}} Grouped requirement collections.
 */
function splitRequirementsByType(requirements) {
  return requirements.reduce(
    (groups, requirement) => {
      if (requirement?.requirement_type === "must_have") {
        groups.mustHave.push(requirement);
      } else {
        groups.niceToHave.push(requirement);
      }
      return groups;
    },
    { mustHave: [], niceToHave: [] },
  );
}

/**
 * Build a compact chip list for the most important job metadata.
 *
 * @param {object} jobPosting Structured JobPosting payload.
 * @returns {string[]} Metadata chips rendered near the job title.
 */
function buildJobMetaChips(jobPosting) {
  return [
    jobPosting.work_mode ? `Tryb: ${jobPosting.work_mode}` : null,
    jobPosting.employment_type ? `Umowa: ${jobPosting.employment_type}` : null,
    jobPosting.seniority_level ? `Poziom: ${jobPosting.seniority_level}` : null,
  ].filter(Boolean);
}

/**
 * Render the structured detail view of a selected or parsed JobPosting.
 *
 * @param {{jobPosting: object, rawJsonLabel?: string}} props Component props.
 * @returns {JSX.Element} Structured JobPosting detail section.
 */
export default function JobPostingDetails({ jobPosting, rawJsonLabel = "Raw JSON" }) {
  const responsibilities = Array.isArray(jobPosting?.responsibilities) ? jobPosting.responsibilities : [];
  const requirements = Array.isArray(jobPosting?.requirements) ? jobPosting.requirements : [];
  const keywords = buildDisplayKeywords(jobPosting?.keywords);
  const { mustHave, niceToHave } = splitRequirementsByType(requirements);
  const metaChips = buildJobMetaChips(jobPosting);

  return (
    <div className="job-details">
      <header className="detail-header">
        <div>
          <h3 className="detail-title">{jobPosting.title || "Brak tytulu"}</h3>
          <p className="detail-company">{jobPosting.company_name || "Brak nazwy firmy"}</p>
        </div>
        {metaChips.length > 0 ? (
          <div className="chip-row">
            {metaChips.map((chip) => (
              <span key={chip} className="chip muted">
                {chip}
              </span>
            ))}
          </div>
        ) : null}
      </header>

      <dl className="detail-main-grid">
        <div>
          <dt>Lokalizacja</dt>
          <dd>{jobPosting.location || "brak"}</dd>
        </div>
        <div>
          <dt>Tryb pracy</dt>
          <dd>{jobPosting.work_mode || "brak"}</dd>
        </div>
        <div>
          <dt>Typ zatrudnienia</dt>
          <dd>{jobPosting.employment_type || "brak"}</dd>
        </div>
        <div>
          <dt>Poziom</dt>
          <dd>{jobPosting.seniority_level || "brak"}</dd>
        </div>
      </dl>

      <section className="detail-section">
        <h4>Opis roli</h4>
        <p className="detail-text">{jobPosting.role_summary || "Brak opisu roli."}</p>
      </section>

      <section className="detail-section">
        <h4>Obowiazki</h4>
        {responsibilities.length > 0 ? (
          <ul className="detail-list">
            {responsibilities.map((item, index) => (
              <li key={`${item}-${index}`}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="placeholder">Brak zapisanych obowiazkow.</p>
        )}
      </section>

      <div className="requirement-columns">
        <section className="detail-section">
          <h4>Must-have</h4>
          {mustHave.length > 0 ? (
            <ul className="detail-list">
              {mustHave.map((requirement) => (
                <li key={requirement.id}>{requirement.text}</li>
              ))}
            </ul>
          ) : (
            <p className="placeholder">Brak wymagan typu must-have.</p>
          )}
        </section>

        <section className="detail-section">
          <h4>Nice-to-have</h4>
          {niceToHave.length > 0 ? (
            <ul className="detail-list">
              {niceToHave.map((requirement) => (
                <li key={requirement.id}>{requirement.text}</li>
              ))}
            </ul>
          ) : (
            <p className="placeholder">Brak wymagan typu nice-to-have.</p>
          )}
        </section>
      </div>

      <section className="detail-section">
        <h4>Slowa kluczowe</h4>
        {keywords.length > 0 ? (
          <div className="chip-row">
            {keywords.map((keyword, index) => (
              <span key={`${keyword}-${index}`} className="chip accent">
                {keyword}
              </span>
            ))}
          </div>
        ) : (
          <p className="placeholder">Brak zapisanych slow kluczowych.</p>
        )}
      </section>

      <RawJsonPanel summary={rawJsonLabel} value={jobPosting} />
    </div>
  );
}
