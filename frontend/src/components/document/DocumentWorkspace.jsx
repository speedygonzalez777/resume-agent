/**
 * Two-column workspace for the final PDF document flow.
 */

/**
 * @param {{left: import("react").ReactNode, right: import("react").ReactNode}} props Component props.
 * @returns {JSX.Element} Document workspace layout.
 */
export default function DocumentWorkspace({ left, right }) {
  return (
    <div className="document-workspace">
      <div className="document-workspace-main">{left}</div>
      <aside className="document-workspace-side">{right}</aside>
    </div>
  );
}
