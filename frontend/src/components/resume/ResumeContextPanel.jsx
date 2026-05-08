import { useState } from "react";

import {
  buildSummaryPreviewItems,
  formatFitClassificationLabel,
  formatFitClassificationMetricLabel,
  formatRecommendationLabel,
  formatRecommendationMetricLabel,
} from "./displayHelpers";

function formatPercent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "brak";
  }
  return `${Math.round(value * 100)}%`;
}

function getInitialVisibleItems(items, showAll, pinnedIds = []) {
  if (showAll || items.length <= 3) {
    return items;
  }

  const visibleItems = items.slice(0, 3);
  const visibleIds = new Set(visibleItems.map((item) => item.id));

  pinnedIds.forEach((pinnedId) => {
    if (!pinnedId || visibleIds.has(pinnedId)) {
      return;
    }

    const pinnedItem = items.find((item) => item.id === pinnedId);
    if (pinnedItem) {
      visibleItems.push(pinnedItem);
      visibleIds.add(pinnedId);
    }
  });

  return visibleItems;
}

/**
 * @param {{
 *   selectedProfileDetail: object | null,
 *   selectedProfileLoading: boolean,
 *   selectedJobDetail: object | null,
 *   selectedJobLoading: boolean,
 *   hasPairSelected: boolean,
 *   activeMatchResult: object | null,
 *   activeMatchSourceLabel: string,
 *   activeMatchSourceId?: number | null,
 *   matchSourceMeta?: string | null,
 *   selectedHistoryPreview: object | null,
 *   selectedHistoryPreviewMatchResult: object | null,
 *   selectedHistoryPreviewStats: {matched: number, partial: number, missing: number, notVerifiable: number},
 *   selectedHistoryStrengthsPreview: string[],
 *   selectedHistoryGapsPreview: string[],
 *   matchHistory: object[],
 *   historyLoading: boolean,
 *   historyError: string | null,
 *   historyPreviewId: number | null,
 *   historyPreviewLoadingId: number | null,
 *   onHistoryPreviewToggle: (id: number) => void,
 *   resumeDraftHistory: object[],
 *   resumeDraftHistoryLoading: boolean,
 *   resumeDraftHistoryError: string | null,
 *   currentResumeDraftRecordId: number | null,
 *   resumeDraftLoadingId: number | null,
 *   onSavedResumeDraftOpen: (id: number) => void,
 *   canGoToDocument: boolean,
 *   onGoToDocument?: (() => void) | null,
 *   formatSavedAt: (savedAt: string) => string,
 * }} props
 * @returns {JSX.Element}
 */
export default function ResumeContextPanel({
  selectedProfileDetail,
  selectedProfileLoading,
  selectedJobDetail,
  selectedJobLoading,
  hasPairSelected,
  activeMatchResult,
  activeMatchSourceLabel,
  activeMatchSourceId = null,
  matchSourceMeta = null,
  selectedHistoryPreview,
  selectedHistoryPreviewMatchResult,
  selectedHistoryPreviewStats,
  selectedHistoryStrengthsPreview,
  selectedHistoryGapsPreview,
  matchHistory,
  historyLoading,
  historyError,
  historyPreviewId,
  historyPreviewLoadingId,
  onHistoryPreviewToggle,
  resumeDraftHistory,
  resumeDraftHistoryLoading,
  resumeDraftHistoryError,
  currentResumeDraftRecordId,
  resumeDraftLoadingId,
  onSavedResumeDraftOpen,
  canGoToDocument,
  onGoToDocument = null,
  formatSavedAt,
}) {
  const [showAllMatchHistory, setShowAllMatchHistory] = useState(false);
  const [showAllDraftHistory, setShowAllDraftHistory] = useState(false);
  const profile = selectedProfileDetail?.payload?.personal_info ?? null;
  const job = selectedJobDetail?.payload ?? null;
  const pairReady = Boolean(profile && job);
  const activeRecommendationLabel = formatRecommendationMetricLabel(activeMatchResult?.recommendation);
  const activeSummaryPreviewItems = buildSummaryPreviewItems(activeMatchResult?.final_summary);
  const archivalSummaryPreviewItems = buildSummaryPreviewItems(selectedHistoryPreviewMatchResult?.final_summary);
  const visibleMatchHistory = getInitialVisibleItems(
    matchHistory,
    showAllMatchHistory,
    [historyPreviewId, activeMatchSourceId],
  );
  const visibleDraftHistory = getInitialVisibleItems(
    resumeDraftHistory,
    showAllDraftHistory,
    [currentResumeDraftRecordId],
  );

  return (
    <div className="resume-context-panel resume-context-panel-scroll">
      <section className="document-side-section">
        <h4>Aktualna para</h4>
        {selectedProfileLoading || selectedJobLoading ? (
          <p className="placeholder">Ładowanie wybranej pary...</p>
        ) : pairReady ? (
          <div className="resume-context-pair">
            <div className="resume-context-pair-block">
              <span className="metric-label">Profil</span>
              <strong>{profile.full_name || "Brak imienia i nazwiska"}</strong>
              <p className="helper-text">{profile.email || "Brak e-maila"}</p>
            </div>
            <div className="resume-context-pair-block">
              <span className="metric-label">Oferta</span>
              <strong>{job.title || "Brak tytułu"}</strong>
              <p className="helper-text">{job.company_name || "Brak firmy"}</p>
            </div>
          </div>
        ) : (
          <p className="placeholder">Wybierz profil i ofertę, aby rozpocząć workflow.</p>
        )}
      </section>

      <section className="document-side-section">
        <h4>Aktywny wynik dopasowania</h4>
        {activeMatchResult ? (
          <>
            <div className="document-status-list resume-match-status-list">
              <div className="document-status-item">
                <span>Wynik</span>
                <strong>{formatPercent(activeMatchResult.overall_score)}</strong>
              </div>
              <div className="document-status-item">
                <span>Dopasowanie</span>
                <strong>{formatFitClassificationMetricLabel(activeMatchResult.fit_classification)}</strong>
              </div>
              <div className="document-status-item">
                <span>Rekomendacja</span>
                <strong>{activeRecommendationLabel}</strong>
              </div>
            </div>

            {activeSummaryPreviewItems.length > 0 ? (
              <div className="resume-context-verdict">
                <ul className="resume-context-summary-points">
                  {activeSummaryPreviewItems.map((item, index) => (
                    <li key={`${item}-${index}`}>{item}</li>
                  ))}
                </ul>

                {activeMatchResult.final_summary ? (
                  <details className="resume-context-details">
                    <summary className="resume-context-details-summary">Pokaż pełne uzasadnienie</summary>
                    <div className="resume-context-details-body">
                      <p className="detail-text resume-match-summary-copy">{activeMatchResult.final_summary}</p>
                    </div>
                  </details>
                ) : null}
              </div>
            ) : null}

            <p className="helper-text">{matchSourceMeta || activeMatchSourceLabel}</p>
          </>
        ) : (
          <p className="placeholder">
            Brak aktywnego wyniku. Archiwalne wyniki w historii nie zastępują bieżącego dopasowania.
          </p>
        )}
      </section>

      {canGoToDocument ? (
        <section className="document-side-section">
          <h4>Następny krok</h4>
          <p className="helper-text">Draft jest gotowy. Możesz przejść do etapu przygotowania PDF.</p>
          <button
            type="button"
            className="primary-button document-side-action"
            onClick={onGoToDocument ?? undefined}
            disabled={!onGoToDocument}
          >
            Przejdź do PDF
          </button>
        </section>
      ) : null}

      <section className="document-side-section">
        <h4>Historia dopasowań</h4>
        {historyError ? <div className="message error">{historyError}</div> : null}

        {historyLoading ? (
          <p className="placeholder">Ładowanie historii dopasowań...</p>
        ) : matchHistory.length > 0 ? (
          <>
            <div className="resume-context-list">
              {visibleMatchHistory.map((item) => (
                <div
                  key={item.id}
                  className={`resume-context-item${historyPreviewId === item.id || activeMatchSourceId === item.id ? " active" : ""}`}
                >
                  <div className="resume-context-item-main">
                    <strong className="resume-context-item-title">
                      Wynik #{item.id}
                      {activeMatchSourceId === item.id ? (
                        <span className="resume-context-current-tag">Aktywny</span>
                      ) : null}
                    </strong>
                    <span className="resume-context-item-meta">
                      {formatPercent(item.overall_score)} · {formatFitClassificationLabel(item.fit_classification)}
                    </span>
                    <span className="resume-context-item-meta">
                      Rekomendacja: {formatRecommendationLabel(item.recommendation)}
                    </span>
                    <span className="resume-context-item-meta">Zapisano: {formatSavedAt(item.saved_at)}</span>
                  </div>
                  <div className="resume-context-item-actions">
                    <button
                      type="button"
                      className="ghost-button document-row-action-button"
                      onClick={() => onHistoryPreviewToggle(item.id)}
                      disabled={historyPreviewLoadingId === item.id}
                    >
                      {historyPreviewLoadingId === item.id
                        ? "Ładowanie..."
                        : historyPreviewId === item.id
                          ? "Ukryj"
                          : "Podgląd"}
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {matchHistory.length > 3 ? (
              <button
                type="button"
                className="ghost-button document-row-action-button resume-context-toggle-button"
                onClick={() => setShowAllMatchHistory((currentValue) => !currentValue)}
              >
                {showAllMatchHistory ? "Pokaż mniej" : "Pokaż więcej"}
              </button>
            ) : null}
          </>
        ) : !hasPairSelected ? (
          <p className="placeholder">Wybierz profil i ofertę, aby zobaczyć historię dopasowań.</p>
        ) : (
          <p className="placeholder">Brak zapisanych wyników dla tej pary.</p>
        )}

        {selectedHistoryPreviewMatchResult ? (
          <div className="resume-archival-preview">
            <div className="section-header section-header-inline document-mini-header">
              <div>
                <h4>Archiwalny podgląd #{selectedHistoryPreview?.id}</h4>
                <p className="helper-text">Ten podgląd nie zastępuje aktywnego wyniku używanego do draftu.</p>
              </div>
              <button
                type="button"
                className="ghost-button document-row-action-button"
                onClick={() => onHistoryPreviewToggle(selectedHistoryPreview.id)}
              >
                Zamknij
              </button>
            </div>

            <div className="document-status-list resume-match-status-list">
              <div className="document-status-item">
                <span>Spełnione</span>
                <strong>{selectedHistoryPreviewStats.matched}</strong>
                <small>spełnione</small>
              </div>
              <div className="document-status-item">
                <span>Częściowe</span>
                <strong>{selectedHistoryPreviewStats.partial}</strong>
                <small>częściowe</small>
              </div>
              <div className="document-status-item">
                <span>Braki</span>
                <strong>{selectedHistoryPreviewStats.missing}</strong>
                <small>braki</small>
              </div>
              <div className="document-status-item">
                <span>Nie do weryfikacji</span>
                <strong>{selectedHistoryPreviewStats.notVerifiable}</strong>
                <small>niezweryfikowane</small>
              </div>
            </div>

            {archivalSummaryPreviewItems.length > 0 ? (
              <div className="resume-context-verdict">
                <ul className="resume-context-summary-points">
                  {archivalSummaryPreviewItems.map((item, index) => (
                    <li key={`${item}-${index}`}>{item}</li>
                  ))}
                </ul>

                {selectedHistoryPreviewMatchResult.final_summary ? (
                  <details className="resume-context-details">
                    <summary className="resume-context-details-summary">Pokaż pełne uzasadnienie</summary>
                    <div className="resume-context-details-body">
                      <p className="detail-text resume-match-summary-copy">
                        {selectedHistoryPreviewMatchResult.final_summary}
                      </p>
                    </div>
                  </details>
                ) : null}
              </div>
            ) : null}

            {(selectedHistoryStrengthsPreview.length > 0 || selectedHistoryGapsPreview.length > 0) ? (
              <div className="resume-match-insight-grid">
                <section className="resume-match-insight-card">
                  <h4>Mocne strony</h4>
                  {selectedHistoryStrengthsPreview.length > 0 ? (
                    <ul className="detail-list">
                      {selectedHistoryStrengthsPreview.map((item, index) => (
                        <li key={`${item}-${index}`}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="placeholder">Brak skrótu mocnych stron.</p>
                  )}
                </section>
                <section className="resume-match-insight-card">
                  <h4>Luki</h4>
                  {selectedHistoryGapsPreview.length > 0 ? (
                    <ul className="detail-list">
                      {selectedHistoryGapsPreview.map((item, index) => (
                        <li key={`${item}-${index}`}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="placeholder">Brak skrótu luk.</p>
                  )}
                </section>
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="document-side-section">
        <h4>Zapisane drafty</h4>
        {resumeDraftHistoryError ? <div className="message error">{resumeDraftHistoryError}</div> : null}

        {resumeDraftHistoryLoading ? (
          <p className="placeholder">Ładowanie zapisanych draftów...</p>
        ) : resumeDraftHistory.length > 0 ? (
          <>
            <div className="resume-context-list">
              {visibleDraftHistory.map((item) => (
                <div
                  key={item.id}
                  className={`resume-context-item${currentResumeDraftRecordId === item.id ? " active" : ""}`}
                >
                  <div className="resume-context-item-main">
                    <strong className="resume-context-item-title">Draft #{item.id}</strong>
                    <span className="resume-context-item-meta">
                      {item.target_job_title || "Brak tytułu"} · {item.target_company_name || "Brak firmy"}
                    </span>
                    <span className="resume-context-item-meta">
                      {item.has_refined_version ? "Poprawa AI dostępna" : "Tylko bazowy draft"}
                    </span>
                    <span className="resume-context-item-meta">
                      Zapisano: {formatSavedAt(item.saved_at)}
                    </span>
                  </div>
                  <div className="resume-context-item-actions">
                    <button
                      type="button"
                      className="ghost-button document-row-action-button"
                      onClick={() => onSavedResumeDraftOpen(item.id)}
                      disabled={resumeDraftLoadingId === item.id}
                    >
                      {resumeDraftLoadingId === item.id ? "Ładowanie..." : "Otwórz"}
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {resumeDraftHistory.length > 3 ? (
              <button
                type="button"
                className="ghost-button document-row-action-button resume-context-toggle-button"
                onClick={() => setShowAllDraftHistory((currentValue) => !currentValue)}
              >
                {showAllDraftHistory ? "Pokaż mniej" : "Pokaż więcej"}
              </button>
            ) : null}
          </>
        ) : !hasPairSelected ? (
          <p className="placeholder">Wybierz profil i ofertę, aby zobaczyć zapisane drafty.</p>
        ) : (
          <p className="placeholder">Brak zapisanych draftów dla tej pary.</p>
        )}
      </section>
    </div>
  );
}
