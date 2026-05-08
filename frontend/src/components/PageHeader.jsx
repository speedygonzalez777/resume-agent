/**
 * Map backend health state to a short label for the global indicator.
 *
 * @param {"checking" | "online" | "offline" | undefined} backendStatus Current backend status.
 * @returns {string} User-facing status label.
 */
function getBackendStatusLabel(backendStatus) {
  if (backendStatus === "online") {
    return "Backend działa";
  }
  if (backendStatus === "offline") {
    return "Brak połączenia z backendem";
  }
  return "Sprawdzanie backendu";
}

/**
 * Render the contextual header for the active process step.
 *
 * @param {{
 *   activeStep: {label: string, description: string, headerDescription?: string},
 *   backendStatus: "checking" | "online" | "offline",
 * }} props Component props.
 * @returns {JSX.Element} Page header.
 */
export default function PageHeader({ activeStep, backendStatus }) {
  const backendStatusLabel = getBackendStatusLabel(backendStatus);

  return (
    <header className="app-header">
      <div className="page-header-content">
        <span className="page-header-badge app-meta-glow-label">Etap procesu</span>
        <h2>{activeStep.label}</h2>
        <p className="subtitle">{activeStep.headerDescription ?? activeStep.description}</p>
      </div>

      <div
        className={`backend-status ${backendStatus ?? "checking"}`}
        role="status"
        aria-live="polite"
        aria-label={backendStatusLabel}
        title={backendStatusLabel}
      >
        <span className="backend-status-dot" aria-hidden="true" />
        <span className="backend-status-label">{backendStatusLabel}</span>
      </div>
    </header>
  );
}
