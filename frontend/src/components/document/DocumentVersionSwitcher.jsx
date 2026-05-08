/**
 * Compact version switcher for generated PDF variants.
 */

/**
 * @param {{
 *   versions: Array<{id: string, label: string, renderResponse: object | null}>,
 *   activeVersion: string,
 *   recommendedVersion?: string,
 *   onVersionChange: (versionId: string) => void,
 * }} props Component props.
 * @returns {JSX.Element} Version switcher.
 */
export default function DocumentVersionSwitcher({ versions, activeVersion, recommendedVersion = "base", onVersionChange }) {
  return (
    <div className="document-version-switcher" role="group" aria-label="Wersja PDF">
      {versions.map((version) => {
        const isActive = activeVersion === version.id;
        const isAvailable = Boolean(version.renderResponse);
        const isRecommended = recommendedVersion === version.id;

        return (
          <button
            key={version.id}
            type="button"
            className={`document-version-button${isActive ? " active" : ""}${isRecommended ? " recommended" : ""}`}
            onClick={() => onVersionChange(version.id)}
            disabled={!isAvailable}
            title={isAvailable ? `${version.label}${isRecommended ? " - rekomendowana" : ""}` : "Ta wersja nie została jeszcze wygenerowana"}
          >
            <span>{version.label}</span>
            <span className={`document-version-dot${isAvailable ? " available" : ""}`} aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}
