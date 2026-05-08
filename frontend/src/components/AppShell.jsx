import { useEffect, useState } from "react";

import PageHeader from "./PageHeader";
import SidebarNavigation from "./SidebarNavigation";

const SIDEBAR_COLLAPSED_STORAGE_KEY = "resume-agent:sidebar-collapsed";

function readInitialSidebarCollapsed() {
  if (typeof window === "undefined") {
    return false;
  }
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

/**
 * Render the application shell around the existing tab content.
 *
 * @param {{
 *   tabs: Array<{id: string, label: string, description: string, headerDescription?: string}>,
 *   activeTab: string,
 *   onTabChange: (tabId: string) => void,
 *   backendStatus: "checking" | "online" | "offline",
 *   children: import("react").ReactNode,
 * }} props Component props.
 * @returns {JSX.Element} Shell layout.
 */
export default function AppShell({ tabs, activeTab, onTabChange, backendStatus, children }) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readInitialSidebarCollapsed);
  const activeStep = tabs.find((tab) => tab.id === activeTab) ?? tabs[0];

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(sidebarCollapsed));
    } catch {
      // Sidebar state is a UI preference; the app should keep working without storage.
    }
  }, [sidebarCollapsed]);

  return (
    <main className={`app-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="app-sidebar" aria-label="Proces przygotowania CV">
        <div className="sidebar-top">
          <div className="sidebar-brand">
            <span className="sidebar-brand-kicker app-meta-glow-label">CV Tailoring Agent</span>
            <h1>AI CV Workspace</h1>
            <p>Dopasuj CV do oferty i przygotuj finalny PDF.</p>
          </div>
          <button
            type="button"
            className="sidebar-collapse-button"
            onClick={() => setSidebarCollapsed((currentValue) => !currentValue)}
            aria-label={sidebarCollapsed ? "Rozwiń sidebar" : "Zwiń sidebar"}
            title={sidebarCollapsed ? "Rozwiń sidebar" : "Zwiń sidebar"}
          >
            {sidebarCollapsed ? ">" : "<"}
          </button>
        </div>

        <SidebarNavigation
          tabs={tabs}
          activeTab={activeTab}
          onTabChange={onTabChange}
          collapsed={sidebarCollapsed}
        />
      </aside>

      <div className="app-main">
        <PageHeader activeStep={activeStep} backendStatus={backendStatus} />
        {children}
      </div>
    </main>
  );
}
