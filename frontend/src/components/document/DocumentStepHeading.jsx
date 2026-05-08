/**
 * Compact one-line heading for a workflow step card.
 *
 * @param {{
 *   stepLabel: string,
 *   title: string,
 * }} props Component props.
 * @returns {JSX.Element} Step heading.
 */
export default function DocumentStepHeading({ stepLabel, title }) {
  return (
    <h3 className="document-step-heading">
      <span className="document-step-index">{stepLabel}</span>
      <span className="document-step-separator" aria-hidden="true">
        —
      </span>
      <span className="document-step-title">{title}</span>
    </h3>
  );
}
