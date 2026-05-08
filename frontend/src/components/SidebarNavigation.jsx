/**
 * Render the left process navigation while preserving the existing tab state.
 *
 * @param {{
 *   tabs: Array<{id: string, label: string, description: string, headerDescription?: string}>,
 *   activeTab: string,
 *   onTabChange: (tabId: string) => void,
 *   collapsed?: boolean,
 * }} props Component props.
 * @returns {JSX.Element} Sidebar navigation.
 */
export default function SidebarNavigation({ tabs, activeTab, onTabChange, collapsed = false }) {
  return (
    <nav className={`sidebar-nav${collapsed ? " collapsed" : ""}`} aria-label="Etapy procesu">
      {tabs.map((tab, index) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            type="button"
            className={`sidebar-nav-item${isActive ? " active" : ""}`}
            onClick={() => onTabChange(tab.id)}
            aria-current={isActive ? "page" : undefined}
            aria-label={collapsed ? tab.label : undefined}
            title={collapsed ? tab.label : undefined}
          >
            <span className="step-number">{index + 1}</span>
            <span className="step-copy">
              <strong>{tab.label}</strong>
              <span>{tab.description}</span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}
