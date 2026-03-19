/**
 * Top-level tab shell for the local Resume Tailoring Agent frontend.
 */

import { useState } from "react";

import CandidateProfileTab from "./CandidateProfileTab";
import JobOffersTab from "./JobOffersTab";
import MatchingTab from "./MatchingTab";
import ResumeTab from "./ResumeTab";

const TAB_DEFINITIONS = [
  { id: "jobs", label: "Oferty pracy" },
  { id: "profile", label: "Profil kandydata" },
  { id: "matching", label: "Matching" },
  { id: "resume", label: "CV i list motywacyjny" },
];

/**
 * Render the shared shell with lightweight frontend tabs.
 *
 * @returns {JSX.Element} Root application view.
 */
export default function App() {
  const [activeTab, setActiveTab] = useState("jobs");

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
          <JobOffersTab />
        </section>

        <section className="tab-panel" hidden={activeTab !== "profile"}>
          <CandidateProfileTab />
        </section>

        <section className="tab-panel" hidden={activeTab !== "matching"}>
          <MatchingTab />
        </section>

        <section className="tab-panel" hidden={activeTab !== "resume"}>
          <ResumeTab />
        </section>
      </section>
    </main>
  );
}
