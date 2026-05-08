/**
 * Sticky PDF preview, version switcher, metrics and artifact downloads.
 */

import {
  buildTypstArtifactDownloadUrl,
  buildTypstArtifactPreviewUrl,
} from "../../api";
import DocumentMetricsSummary from "./DocumentMetricsSummary";
import DocumentVersionSwitcher from "./DocumentVersionSwitcher";

function formatBytes(sizeBytes) {
  if (typeof sizeBytes !== "number") {
    return "brak danych";
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function ArtifactDownloadLink({ artifact, renderId, artifactType, label }) {
  if (!artifact || !renderId) {
    return null;
  }

  const downloadUrl = buildTypstArtifactDownloadUrl(renderId, artifactType);

  return (
    <a className="ghost-button document-download-link" href={downloadUrl} download={artifact.filename}>
      <span>{label}</span>
      <small>{formatBytes(artifact.size_bytes)}</small>
    </a>
  );
}

/**
 * @param {{
 *   versions: Array<{id: string, label: string, renderResponse: object | null, emptyText: string}>,
 *   activeVersion: string,
 *   recommendedVersion?: string,
 *   workflowStage?: string,
 *   onVersionChange: (versionId: string) => void,
 * }} props Component props.
 * @returns {JSX.Element} PDF preview panel.
 */
export default function PdfPreviewPanel({
  versions,
  activeVersion,
  recommendedVersion = "base",
  workflowStage = "select-draft",
  onVersionChange,
}) {
  const selectedVersion = versions.find((version) => version.id === activeVersion) ?? versions[0];
  const renderResponse = selectedVersion?.renderResponse ?? null;
  const pdfUrl = renderResponse?.render_id
    ? buildTypstArtifactPreviewUrl(renderResponse.render_id, "pdf")
    : null;
  const warnings = Array.isArray(renderResponse?.warnings) ? renderResponse.warnings : [];
  const hasAnyPdf = versions.some((version) => Boolean(version.renderResponse));
  const emptyText = workflowStage === "select-draft"
    ? "Wybierz draft CV, aby przygotować podgląd PDF."
    : selectedVersion?.emptyText ?? "Ta wersja nie została jeszcze wygenerowana.";

  return (
    <section className="document-preview-panel">
      <div className="section-header">
        <div>
          <h3>Podgląd PDF</h3>
          <p className="section-copy">
            {hasAnyPdf ? `Aktualna wersja: ${selectedVersion.label}.` : "PDF pojawi się tutaj po przygotowaniu dokumentu."}
          </p>
        </div>
      </div>

      <DocumentVersionSwitcher
        versions={versions}
        activeVersion={activeVersion}
        recommendedVersion={recommendedVersion}
        onVersionChange={onVersionChange}
      />

      {pdfUrl ? (
        <div className="pdf-preview-shell document-sticky-preview">
          <iframe
            className="pdf-preview-frame"
            src={pdfUrl}
            title={`Podgląd PDF CV - ${selectedVersion.label}`}
          />
          <div className="pdf-preview-actions">
            <a className="ghost-button" href={pdfUrl} target="_blank" rel="noreferrer">
              Otwórz PDF w nowej karcie
            </a>
          </div>
        </div>
      ) : (
        <div className="document-preview-empty">
          <h4>{selectedVersion?.label ?? "PDF"}</h4>
          <p className="placeholder">{emptyText}</p>
        </div>
      )}

      <div className="document-side-section">
        <h4>Status dokumentu</h4>
        <DocumentMetricsSummary metrics={renderResponse?.layout_metrics} warnings={warnings} />
        {warnings.length > 0 ? (
          <div className="message warning document-warning-list">{warnings.join(" ")}</div>
        ) : null}
      </div>

      {renderResponse ? (
        <div className="document-side-section">
          <h4>Pobieranie</h4>
          <div className="document-download-list">
            <ArtifactDownloadLink
              artifact={renderResponse.pdf_artifact}
              renderId={renderResponse.render_id}
              artifactType="pdf"
              label="Pobierz PDF"
            />
            <ArtifactDownloadLink
              artifact={renderResponse.typ_source_artifact}
              renderId={renderResponse.render_id}
              artifactType="typ"
              label="Pobierz .typ"
            />
          </div>
        </div>
      ) : null}
    </section>
  );
}
