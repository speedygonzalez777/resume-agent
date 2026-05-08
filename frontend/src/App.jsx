/**
 * Top-level tab shell for the local Resume Tailoring Agent frontend.
 */

import { useEffect, useState } from "react";

import { checkBackendHealth } from "./api";
import CandidateProfileTab from "./CandidateProfileTab";
import AppShell from "./components/AppShell";
import DocumentCvTab from "./DocumentCvTab";
import JobOffersTab from "./JobOffersTab";
import ResumeTab from "./ResumeTab";

const TAB_DEFINITIONS = [
  {
    id: "jobs",
    label: "Oferta",
    description: "Dodaj ofertę z linku i zapisz ją do historii.",
    headerDescription: "Wczytaj ofertę z linku i zapisz ją do lokalnej historii.",
  },
  {
    id: "profile",
    label: "Profil",
    description: "Uzupełnij dane, doświadczenie i umiejętności.",
    headerDescription: "Uzupełnij profil, który będzie bazą dopasowania CV.",
  },
  {
    id: "resume",
    label: "Dopasowanie i draft",
    description: "Sprawdź dopasowanie i wygeneruj draft CV.",
    headerDescription: "Policz dopasowanie, wygeneruj draft i sprawdź raport zmian.",
  },
  {
    id: "document",
    label: "PDF i edycja",
    description: "Przygotuj PDF, popraw treść i pobierz dokument.",
    headerDescription: "Przygotuj PDF, sprawdź jakość i wykonaj finalną edycję.",
  },
];

/**
 * Render the shared shell with lightweight frontend tabs.
 *
 * @returns {JSX.Element} Root application view.
 */
export default function App() {
  const [activeTab, setActiveTab] = useState("jobs");
  const [jobListRefreshVersion, setJobListRefreshVersion] = useState(0);
  const [backendStatus, setBackendStatus] = useState("checking");

  useEffect(() => {
    let isActive = true;

    async function loadBackendStatus() {
      try {
        const payload = await checkBackendHealth();
        if (isActive) {
          setBackendStatus(payload.status === "ok" ? "online" : "offline");
        }
      } catch (_error) {
        if (isActive) {
          setBackendStatus("offline");
        }
      }
    }

    void loadBackendStatus();

    return () => {
      isActive = false;
    };
  }, []);

  function handleJobSaved() {
    setJobListRefreshVersion((currentValue) => currentValue + 1);
  }

  return (
    <AppShell
      tabs={TAB_DEFINITIONS}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      backendStatus={backendStatus}
    >
      <section className="panel">
        <section className="tab-panel" hidden={activeTab !== "jobs"}>
          <JobOffersTab onJobSaved={handleJobSaved} />
        </section>

        <section className="tab-panel" hidden={activeTab !== "profile"}>
          <CandidateProfileTab />
        </section>

        <section className="tab-panel" hidden={activeTab !== "resume"}>
          <ResumeTab
            jobListRefreshVersion={jobListRefreshVersion}
            onGoToDocument={() => setActiveTab("document")}
          />
        </section>

        <section className="tab-panel" hidden={activeTab !== "document"}>
          <DocumentCvTab />
        </section>
      </section>
    </AppShell>
  );
}
