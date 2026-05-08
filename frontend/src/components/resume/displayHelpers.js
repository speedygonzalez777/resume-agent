export function formatRecommendationLabel(value, emptyLabel = "brak rekomendacji") {
  if (value === "generate") {
    return "Generuj";
  }
  if (value === "generate_with_caution") {
    return "Generuj ostrożnie";
  }
  if (value === "do_not_recommend") {
    return "Nie rekomenduj";
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return emptyLabel;
}

export function formatFitClassificationLabel(value, emptyLabel = "brak klasyfikacji") {
  if (value === "high") {
    return "wysokie";
  }
  if (value === "medium") {
    return "średnie";
  }
  if (value === "low") {
    return "niskie";
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return emptyLabel;
}

export function formatFitClassificationMetricLabel(value, emptyLabel = "Brak") {
  if (value === "high") {
    return "Wysokie";
  }
  if (value === "medium") {
    return "Średnie";
  }
  if (value === "low") {
    return "Niskie";
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return emptyLabel;
}

export function formatRequirementStatusLabel(value, emptyLabel = "brak statusu") {
  if (value === "matched") {
    return "spełnione";
  }
  if (value === "partial") {
    return "częściowe";
  }
  if (value === "missing") {
    return "brak";
  }
  if (value === "not_verifiable") {
    return "nie do weryfikacji";
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return emptyLabel;
}

export function getRecommendationTone(value) {
  if (value === "generate") {
    return "success";
  }
  if (value === "generate_with_caution") {
    return "warning";
  }
  return "danger";
}

export function formatRecommendationMetricLabel(value, emptyLabel = "Brak") {
  if (value === "generate") {
    return "Generuj";
  }
  if (value === "generate_with_caution") {
    return "Ostrożnie";
  }
  if (value === "do_not_recommend") {
    return "Nie generuj";
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return emptyLabel;
}

export function buildSummaryPreviewItems(summary, limit = 3) {
  if (typeof summary !== "string" || !summary.trim()) {
    return [];
  }

  const normalizedSummary = summary.trim();
  const bulletItems = normalizedSummary
    .split(/\n+/)
    .map((item) => item.replace(/^[-*•]\s*/, "").trim())
    .filter(Boolean);

  if (bulletItems.length > 1) {
    return bulletItems.slice(0, limit);
  }

  const sentenceItems = normalizedSummary
    .replace(/\s+/g, " ")
    .split(/(?<=[.!?])\s+/)
    .map((item) => item.trim())
    .filter(Boolean);

  if (sentenceItems.length > 1) {
    return sentenceItems.slice(0, limit);
  }

  return [normalizedSummary];
}
