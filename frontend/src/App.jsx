/**
 * Top-level tab shell for the local Resume Tailoring Agent frontend.
 */

import { useState } from "react";

import CandidateProfileTab from "./CandidateProfileTab";
import DocumentCvTab from "./DocumentCvTab";
import JobOffersTab from "./JobOffersTab";
import ResumeTab from "./ResumeTab";

const TAB_DEFINITIONS = [
  { id: "jobs", label: "Oferty pracy" },
  { id: "profile", label: "Profil kandydata" },
  { id: "resume", label: "Przygotowanie CV" },
  { id: "document", label: "Dokument CV" },
];

/**
 * Render the shared shell with lightweight frontend tabs.
 *
 * @returns {JSX.Element} Root application view.
 */
export default function App() {
  const [activeTab, setActiveTab] = useState("jobs");
  const [jobListRefreshVersion, setJobListRefreshVersion] = useState(0);

  function handleJobSaved() {
    setJobListRefreshVersion((currentValue) => currentValue + 1);
  }

  return (
    <main className="app-shell">
      <section className="panel">
        <header className="app-header">
          <div>
            <h1>Resume Tailoring Agent</h1>
            <p className="subtitle">
              Lokalne narzedzie do pracy z ofertami pracy, profilami kandydatow i ocena dopasowania.
            </p>
          </div>
        </header>

        <nav className="tab-nav" aria-label="Glowne zakladki aplikacji">
          {TAB_DEFINITIONS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`tab-button${activeTab === tab.id ? " active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <section className="tab-panel" hidden={activeTab !== "jobs"}>
          <JobOffersTab onJobSaved={handleJobSaved} />
        </section>

        <section className="tab-panel" hidden={activeTab !== "profile"}>
          <CandidateProfileTab />
        </section>

        <section className="tab-panel" hidden={activeTab !== "resume"}>
          <ResumeTab jobListRefreshVersion={jobListRefreshVersion} />
        </section>

        <section className="tab-panel" hidden={activeTab !== "document"}>
          <DocumentCvTab />
        </section>
      </section>
    </main>
  );
}
