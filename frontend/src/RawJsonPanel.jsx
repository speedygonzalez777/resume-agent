/**
 * Reusable raw JSON preview with a local copy-to-clipboard action.
 */

import { useEffect, useRef, useState } from "react";

/**
 * Convert a JSON-like value into the exact text shown inside the panel.
 *
 * @param {unknown} value JSON-like value to render.
 * @returns {string} Pretty-printed JSON text.
 */
function stringifyRawJson(value) {
  return JSON.stringify(value, null, 2);
}

/**
 * Render one collapsible raw JSON panel with its own copy feedback.
 *
 * @param {{
 *   summary: string,
 *   value: unknown,
 *   helperText?: string | null,
 *   className?: string
 * }} props Component props.
 * @returns {JSX.Element} Collapsible raw JSON panel.
 */
export default function RawJsonPanel({ summary, value, helperText = null, className = "raw-json-toggle" }) {
  const [copyFeedback, setCopyFeedback] = useState(null);
  const feedbackTimeoutRef = useRef(null);
  const jsonText = stringifyRawJson(value);

  useEffect(() => {
    return () => {
      if (feedbackTimeoutRef.current) {
        window.clearTimeout(feedbackTimeoutRef.current);
      }
    };
  }, []);

  /**
   * Copy the exact rendered JSON text and show local inline feedback.
   *
   * @returns {Promise<void>} Promise resolved after the clipboard attempt.
   */
  async function handleCopyJson() {
    try {
      await navigator.clipboard.writeText(jsonText);
      setCopyFeedback("Skopiowano");
      if (feedbackTimeoutRef.current) {
        window.clearTimeout(feedbackTimeoutRef.current);
      }
      feedbackTimeoutRef.current = window.setTimeout(() => {
        setCopyFeedback(null);
        feedbackTimeoutRef.current = null;
      }, 1800);
    } catch {
      setCopyFeedback("Nie udalo sie skopiowac");
    }
  }

  return (
    <details className={className}>
      <summary>{summary}</summary>
      {helperText ? <p className="helper-text raw-json-note">{helperText}</p> : null}
      <div className="actions raw-json-toolbar">
        <button type="button" className="ghost-button" onClick={() => void handleCopyJson()}>
          Kopiuj JSON
        </button>
        {copyFeedback ? <span className="helper-text">{copyFeedback}</span> : null}
      </div>
      <pre>{jsonText}</pre>
    </details>
  );
}
