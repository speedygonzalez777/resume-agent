/**
 * Compact workflow row with optional expandable body.
 */

import DocumentStepHeading from "./DocumentStepHeading";

function getStatusMarker(status) {
  if (status === "completed") {
    return "✓";
  }
  if (status === "active" || status === "editing") {
    return "●";
  }
  return "○";
}

/**
 * @param {{
 *   status?: "active" | "completed" | "locked" | "available" | "editing",
 *   stepLabel: string,
 *   title: string,
 *   summary?: import("react").ReactNode,
 *   note?: import("react").ReactNode,
 *   actions?: import("react").ReactNode,
 *   body?: import("react").ReactNode,
 *   expanded?: boolean,
 * }} props Component props.
 * @returns {JSX.Element} Compact workflow row.
 */
export default function DocumentWorkflowRow({
  status = "available",
  stepLabel,
  title,
  summary = null,
  note = null,
  actions = null,
  body = null,
  expanded = false,
}) {
  return (
    <section className={`document-workflow-row document-workflow-row-${status}${expanded ? " is-expanded" : ""}`}>
      <div className="document-workflow-row-head">
        <span className="document-workflow-row-indicator" aria-hidden="true">
          {getStatusMarker(status)}
        </span>

        <div className="document-workflow-row-main">
          <DocumentStepHeading stepLabel={stepLabel} title={title} />
          {summary ? <div className="document-workflow-row-summary">{summary}</div> : null}
          {!summary && note ? <p className="document-workflow-row-note">{note}</p> : null}
        </div>

        {actions ? <div className="document-workflow-row-actions">{actions}</div> : null}
      </div>

      {expanded && body ? <div className="document-workflow-row-body">{body}</div> : null}
    </section>
  );
}
