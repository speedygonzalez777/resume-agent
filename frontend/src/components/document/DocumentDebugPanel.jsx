import RawJsonPanel from "../../RawJsonPanel";

export default function DocumentDebugPanel({
  prepareResponse,
  renderResponse,
  analysisResponse,
  fitResponse,
  improvedRenderResponse,
  manualRenderResponse,
}) {
  const hasTechnicalData = Boolean(
    prepareResponse ||
      renderResponse ||
      analysisResponse ||
      fitResponse ||
      improvedRenderResponse ||
      manualRenderResponse,
  );

  return (
    <section className="document-work-card document-debug-card">
      <details className="document-advanced-details">
        <summary>
          <span>Szczegóły techniczne</span>
          <span className="document-debug-hint">Debug, JSON i dane Typst</span>
        </summary>

        <div className="document-debug-stack">
          {!hasTechnicalData ? (
            <p className="placeholder">
              Dane techniczne pojawią się po przygotowaniu lub wygenerowaniu PDF.
            </p>
          ) : null}

          {prepareResponse?.typst_payload ? (
            <RawJsonPanel summary="Typst payload" value={prepareResponse.typst_payload} />
          ) : null}

          {prepareResponse?.prepare_debug ? (
            <RawJsonPanel
              summary="Debug przygotowania dokumentu"
              value={prepareResponse.prepare_debug}
            />
          ) : null}

          {renderResponse?.layout_metrics ? (
            <RawJsonPanel
              summary="Metryki layoutu: pierwszy PDF"
              value={renderResponse.layout_metrics}
            />
          ) : null}

          {analysisResponse ? (
            <RawJsonPanel summary="Analiza jakości PDF" value={analysisResponse} />
          ) : null}

          {fitResponse?.typst_payload ? (
            <RawJsonPanel
              summary="Typst payload po dopasowaniu"
              value={fitResponse.typst_payload}
            />
          ) : null}

          {fitResponse?.patch ? (
            <RawJsonPanel summary="Patch dopasowania do strony" value={fitResponse.patch} />
          ) : null}

          {fitResponse?.fit_debug ? (
            <RawJsonPanel summary="Debug dopasowania do strony" value={fitResponse.fit_debug} />
          ) : null}

          {improvedRenderResponse?.layout_metrics ? (
            <RawJsonPanel
              summary="Metryki layoutu: PDF po dopasowaniu"
              value={improvedRenderResponse.layout_metrics}
            />
          ) : null}

          {manualRenderResponse?.layout_metrics ? (
            <RawJsonPanel
              summary="Metryki layoutu: finalny PDF"
              value={manualRenderResponse.layout_metrics}
            />
          ) : null}
        </div>
      </details>
    </section>
  );
}
