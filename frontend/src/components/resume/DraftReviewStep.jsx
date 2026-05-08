import { useState } from "react";

import ChangeReportDetails from "../../ChangeReportDetails";
import ResumeDraftDetails from "../../ResumeDraftDetails";
import TagListInput from "../../TagListInput";
import DocumentWorkflowRow from "../document/DocumentWorkflowRow";

/**
 * @param {{
 *   mode?: "active" | "completed" | "locked" | "available" | "editing",
 *   expanded?: boolean,
 *   resumeArtifacts: object | null,
 *   displayedResumeDraft: object | null,
 *   hasRefinedResumeDraft: boolean,
 *   resumeDraftView: "base" | "refined",
 *   onResumeDraftViewChange: (view: "base" | "refined") => void,
 *   currentResumeDraftRecordId: number | null,
 *   formatSavedAt: (savedAt: string) => string,
 *   activeMatchResult: object | null,
 *   matchSource: object | null,
 *   refinementGuidance: {
 *     must_include_terms: string[],
 *     avoid_or_deemphasize_terms: string[],
 *     forbidden_claims_or_phrases: string[],
 *     skills_allowlist: string[],
 *     additional_instructions: string,
 *   },
 *   refineLoading: boolean,
 *   flowIsLoading: boolean,
 *   refinementDirty: boolean,
 *   refinementStatusLabel: string,
 *   hasRefinementGuidance: boolean,
 *   onRefineClick: () => void,
 *   onRefinementGuidanceListChange: (fieldName: "must_include_terms" | "avoid_or_deemphasize_terms" | "forbidden_claims_or_phrases" | "skills_allowlist", nextItems: string[]) => void,
 *   onAdditionalInstructionsChange: (nextValue: string) => void,
 *   onExpand: () => void,
 *   onCollapse: () => void,
 * }} props
 * @returns {JSX.Element}
 */
export default function DraftReviewStep({
  mode = "locked",
  expanded = false,
  resumeArtifacts,
  displayedResumeDraft,
  hasRefinedResumeDraft,
  resumeDraftView,
  onResumeDraftViewChange,
  currentResumeDraftRecordId,
  formatSavedAt,
  activeMatchResult,
  matchSource,
  refinementGuidance,
  refineLoading,
  flowIsLoading,
  refinementDirty,
  refinementStatusLabel,
  hasRefinementGuidance,
  onRefineClick,
  onRefinementGuidanceListChange,
  onAdditionalInstructionsChange,
  onExpand,
  onCollapse,
}) {
  const [reviewTab, setReviewTab] = useState("draft");
  const isLocked = mode === "locked";

  const summary = !isLocked ? (
    <div className="document-row-summary-list">
      <span>{currentResumeDraftRecordId ? `Draft #${currentResumeDraftRecordId}` : "Draft gotowy"}</span>
      <span>Raport zmian dostępny</span>
      <span>{hasRefinedResumeDraft ? "AI poprawa gotowa" : "Poprawa AI opcjonalna"}</span>
    </div>
  ) : null;

  const actions = !isLocked && !expanded ? (
    <button type="button" className="ghost-button document-row-action-button" onClick={onExpand}>
      Otwórz
    </button>
  ) : null;

  const savedAtLabel = resumeArtifacts?.resume_draft_saved_at
    ? formatSavedAt(resumeArtifacts.resume_draft_saved_at)
    : null;

  return (
    <DocumentWorkflowRow
      status={mode}
      expanded={!isLocked && expanded}
      stepLabel="Krok 4"
      title="Podgląd i raport"
      summary={summary}
      note={isLocked ? "Najpierw wygeneruj albo otwórz draft CV." : null}
      actions={actions}
      body={(
        <div className="document-workflow-form resume-review-shell">
          <div className="resume-review-toolbar">
            <div className="resume-review-toolbar-main">
              <div className="resume-version-switcher" role="group" aria-label="Widok kroku podglądu draftu">
                <button
                  type="button"
                  className={`resume-version-button${reviewTab === "draft" ? " active" : ""}`}
                  onClick={() => setReviewTab("draft")}
                >
                  Draft CV
                </button>
                <button
                  type="button"
                  className={`resume-version-button${reviewTab === "report" ? " active" : ""}`}
                  onClick={() => setReviewTab("report")}
                >
                  Raport zmian
                </button>
              </div>

              {reviewTab === "draft" && hasRefinedResumeDraft ? (
                <div className="resume-version-switcher" role="group" aria-label="Wersja podglądu draftu">
                  <button
                    type="button"
                    className={`resume-version-button${resumeDraftView === "base" ? " active" : ""}`}
                    onClick={() => onResumeDraftViewChange("base")}
                  >
                    Bazowy draft
                  </button>
                  <button
                    type="button"
                    className={`resume-version-button${resumeDraftView === "refined" ? " active" : ""}`}
                    onClick={() => onResumeDraftViewChange("refined")}
                  >
                    AI poprawiony draft
                  </button>
                </div>
              ) : null}
            </div>

            <button
              type="button"
              className="ghost-button document-row-action-button"
              onClick={onCollapse}
            >
              Zwiń podgląd
            </button>
          </div>

          {currentResumeDraftRecordId || savedAtLabel ? (
            <p className="helper-text">
              {currentResumeDraftRecordId ? `Aktywny zapisany draft #${currentResumeDraftRecordId}` : "Aktywny draft z bieżącej sesji"}
              {savedAtLabel ? ` · zapisano ${savedAtLabel}` : ""}
            </p>
          ) : null}

          <div className="resume-review-content-scroll">
            {reviewTab === "draft" ? (
              <>
                {displayedResumeDraft ? (
                  <ResumeDraftDetails resumeDraft={displayedResumeDraft} />
                ) : (
                  <p className="placeholder">Brak draftu do pokazania.</p>
                )}

                {resumeArtifacts?.resume_draft ? (
                  <details className="resume-refinement-panel">
                    <summary className="resume-refinement-summary">
                      <div>
                        <strong>Popraw draft CV (AI)</strong>
                        <p>
                          Opcjonalnie dopracuj gotowy draft bez generowania CV od nowa. Bazowa wersja zawsze pozostaje do dyspozycji.
                        </p>
                      </div>
                      <span className="section-count-badge">{refinementStatusLabel}</span>
                    </summary>

                    <div className="resume-refinement-body">
                      <p className="helper-text">
                        Wpisz kilka prostych wskazówek, a AI przygotuje dodatkową wersję draftu na bazie już wygenerowanego CV.
                      </p>

                      {refinementDirty && hasRefinedResumeDraft ? (
                        <div className="message info">
                          Zmieniono wskazówki. Ostatnia poprawiona wersja AI nadal jest widoczna, ale kliknij przycisk ponownie, aby ją odświeżyć.
                        </div>
                      ) : null}

                      <div className="form-grid resume-form-grid">
                        <TagListInput
                          label="Co warto mocniej pokazać"
                          helperText="Dodaj terminy, które warto lepiej wyeksponować, o ile są już uczciwie pokryte w bazowym drafcie."
                          emptyText="Brak dodatkowych terminów do mocniejszego podkreślenia."
                          items={refinementGuidance.must_include_terms}
                          onChange={(items) => onRefinementGuidanceListChange("must_include_terms", items)}
                          placeholder="np. PLC, embedded, commissioning"
                        />
                        <TagListInput
                          label="Czego nie promować"
                          helperText="Dodaj obszary, które są prawdziwe, ale nie powinny być osią tej konkretnej wersji CV."
                          emptyText="Brak terminów do osłabienia."
                          items={refinementGuidance.avoid_or_deemphasize_terms}
                          onChange={(items) => onRefinementGuidanceListChange("avoid_or_deemphasize_terms", items)}
                          placeholder="np. SAP, support, QA"
                        />
                        <TagListInput
                          label="Jakich sformułowań unikać"
                          helperText="Te frazy nie powinny pojawić się w poprawionej wersji draftu."
                          emptyText="Brak zakazanych sformułowań."
                          items={refinementGuidance.forbidden_claims_or_phrases}
                          onChange={(items) => onRefinementGuidanceListChange("forbidden_claims_or_phrases", items)}
                          placeholder="np. expert, world-class"
                        />
                        <TagListInput
                          label="Jakie skille mają zostać w sekcji skills"
                          helperText="Jeśli wpiszesz tu konkretne skille, AI ograniczy finalną sekcję skills do tej listy."
                          emptyText="Brak ograniczeń dla sekcji skills."
                          items={refinementGuidance.skills_allowlist}
                          onChange={(items) => onRefinementGuidanceListChange("skills_allowlist", items)}
                          placeholder="np. PLC, Python, TIA Portal"
                        />
                        <label className="field section-wide-field">
                          <span>Dodatkowe wskazówki</span>
                          <p className="helper-text">
                            Krótko opisz kierunek poprawek, np. bardziej zwięźle, bardziej technicznie albo mocniej pod embedded automation.
                          </p>
                          <textarea
                            className="form-textarea compact-textarea"
                            value={refinementGuidance.additional_instructions}
                            onChange={(event) => onAdditionalInstructionsChange(event.target.value)}
                            placeholder="np. Skróć summary, zostaw bardziej techniczny ton i skup się na automatyce przemysłowej."
                            disabled={flowIsLoading}
                          />
                        </label>
                      </div>

                      <div className="actions resume-refinement-actions">
                        <button
                          type="button"
                          className="primary-button"
                          onClick={onRefineClick}
                          disabled={flowIsLoading || !hasRefinementGuidance}
                        >
                          {refineLoading ? "Przygotowywanie poprawy AI..." : "Popraw draft CV z AI"}
                        </button>
                      </div>

                      {!hasRefinementGuidance ? (
                        <p className="helper-text">
                          Dodaj przynajmniej jedną wskazówkę, aby uruchomić opcjonalną poprawę AI.
                        </p>
                      ) : null}
                    </div>
                  </details>
                ) : null}
              </>
            ) : (
              <>
                {hasRefinedResumeDraft ? (
                  <p className="helper-text">
                    Raport zmian dotyczy bazowego draftu. Poprawa AI nie przelicza tego raportu.
                  </p>
                ) : null}

                {resumeArtifacts?.change_report ? (
                  <ChangeReportDetails
                    changeReport={resumeArtifacts.change_report}
                    matchResult={activeMatchResult}
                    matchSource={matchSource}
                    generationMode={resumeArtifacts.generation_mode}
                    fallbackReason={resumeArtifacts.fallback_reason}
                    generationNotes={resumeArtifacts.generation_notes}
                  />
                ) : (
                  <p className="placeholder">Brak raportu zmian do pokazania.</p>
                )}
              </>
            )}
          </div>
        </div>
      )}
    />
  );
}
