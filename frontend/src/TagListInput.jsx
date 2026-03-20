/**
 * Reusable input for editing short string lists such as roles, tags or keywords.
 */

import { useState } from "react";

/**
 * Normalize a typed list item before adding it to the collection.
 *
 * @param {string} value Raw user input.
 * @returns {string} Trimmed list item.
 */
function normalizeListItem(value) {
  return String(value ?? "").trim();
}

/**
 * Render a compact add-and-remove control for short string lists.
 *
 * @param {{
 *   label: string,
 *   items: string[],
 *   onChange: (items: string[]) => void,
 *   placeholder?: string,
 *   addLabel?: string,
 * }} props Component props.
 * @returns {JSX.Element} Tag-list editor.
 */
export default function TagListInput({
  label,
  items,
  onChange,
  placeholder = "Dodaj wartosc",
  addLabel = "Dodaj",
}) {
  const [draftValue, setDraftValue] = useState("");

  /**
   * Append the current draft value to the list when it is non-empty and new.
   *
   * @returns {void} No return value.
   */
  function handleAddItem() {
    const normalizedItem = normalizeListItem(draftValue);
    if (!normalizedItem) {
      return;
    }

    if (items.includes(normalizedItem)) {
      setDraftValue("");
      return;
    }

    onChange([...items, normalizedItem]);
    setDraftValue("");
  }

  /**
   * Remove one list item by index.
   *
   * @param {number} index Index of the item to remove.
   * @returns {void} No return value.
   */
  function handleRemoveItem(index) {
    onChange(items.filter((_, itemIndex) => itemIndex !== index));
  }

  /**
   * Support quick item creation with the Enter key.
   *
   * @param {import("react").KeyboardEvent<HTMLInputElement>} event Keyboard event from the text input.
   * @returns {void} No return value.
   */
  function handleKeyDown(event) {
    if (event.key === "Enter") {
      event.preventDefault();
      handleAddItem();
    }
  }

  return (
    <div className="field tag-list-field">
      <span>{label}</span>

      <div className="tag-input-row">
        <input
          type="text"
          value={draftValue}
          placeholder={placeholder}
          onChange={(event) => setDraftValue(event.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button type="button" className="ghost-button tag-add-button" onClick={handleAddItem}>
          {addLabel}
        </button>
      </div>

      {items.length > 0 ? (
        <div className="tag-list-output">
          {items.map((item, index) => (
            <div key={`${item}-${index}`} className="tag-list-item">
              <div className="tag-pill">{item}</div>
              <button
                type="button"
                className="tag-pill-remove"
                onClick={() => handleRemoveItem(index)}
                aria-label={`Usun ${item}`}
                title={`Usun ${item}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p className="helper-text">Brak dodanych pozycji.</p>
      )}
    </div>
  );
}
