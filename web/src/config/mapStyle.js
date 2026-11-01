// Single source of truth for the map's colours, labels, and class
// definitions (ADR-003). No component should hard-code a colour or a
// class label of its own -- everything reads from this module, so the
// map's paint expressions and the Legend's swatches can never drift
// apart into two hand-copied lists.

// ADR-002/003: Gi* confidence classes (primary map), in legend order.
// Wording follows ADR-002/003 exactly: a hotspot is "part of a high-burden
// area", never "high stress".
export const GI_STAR_CONFIDENCE_CLASSES = [
  { value: "robust_hotspot", color: "#b2182b", label: "Part of a high-burden area" },
  { value: "possible_hotspot", color: "#ef8a62", label: "Possibly part of a high-burden area" },
  { value: "not_significant", color: "#f2f2f2", label: "No significant pattern" },
  { value: "possible_coldspot", color: "#67a9cf", label: "Possibly part of a low-burden area" },
  { value: "robust_coldspot", color: "#2166ac", label: "Part of a low-burden area" },
  { value: "conflicting", color: "#999999", label: "Result depends on method" },
  {
    value: "not_analysed",
    color: "#bdbdbd",
    label: "Not analysed (too few households)",
    hatch: true,
  },
];

const NOT_ANALYSED_CLASS = GI_STAR_CONFIDENCE_CLASSES.find((c) => c.value === "not_analysed");
export const NOT_ANALYSED_COLOR = NOT_ANALYSED_CLASS.color;

// ADR-003: rent_burden quintiles (secondary map). ColorBrewer YlOrRd
// 5-class, verified against colorbrewer2.org's published values, light
// (lowest burden) -> dark (highest burden).
export const RENT_BURDEN_QUINTILE_COLORS = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"];

// ADR-003: SA2 outline style. Width is in CSS pixels for screen display
// (ADR-003's 0.2mm figure is for print layouts specifically).
export const SA2_OUTLINE_STYLE = { color: "#c8c8c8", widthPx: 0.75 };

// Labels (ADR-003): only robust_hotspot / robust_coldspot SA2s are labelled.
export const LABELLED_CONFIDENCE_CLASSES = ["robust_hotspot", "robust_coldspot"];

// ADR-003 legend note for the secondary (quintile) map.
export const QUINTILE_LEGEND_NOTE = "Classes show relative ranking within Perth.";

/**
 * MapLibre `match` paint expression for the primary (confidence) map,
 * built from GI_STAR_CONFIDENCE_CLASSES above -- the map's fill colours
 * and the Legend's swatches are driven by the same array, not two lists.
 */
export function buildConfidenceColorExpression() {
  const expr = ["match", ["get", "gi_star_confidence"]];
  for (const c of GI_STAR_CONFIDENCE_CLASSES) expr.push(c.value, c.color);
  expr.push(NOT_ANALYSED_COLOR); // fallback; should never hit if data matches this config
  return expr;
}

/**
 * MapLibre `match` paint expression for the secondary (quintile) map.
 * rent_burden_quintile is 1-5 for analysed SA2s, null for not-analysed
 * ones -- shown as the same not_analysed grey as the primary map.
 */
export function buildQuintileColorExpression() {
  const expr = ["match", ["get", "rent_burden_quintile"]];
  RENT_BURDEN_QUINTILE_COLORS.forEach((color, i) => {
    expr.push(i + 1, color);
  });
  expr.push(NOT_ANALYSED_COLOR); // fallback: null/missing quintile (not analysed)
  return expr;
}

/**
 * Quintile legend entries (colour + label), built from the *actual*
 * breaks in run_metadata.json rather than hand-typed ranges -- so the
 * legend text always matches what the data was classified against.
 * `breaks` is the 5 increasing upper-bound values from
 * run_metadata.json's rent_burden_quintile_breaks.
 */
export function buildQuintileLegendEntries(breaks) {
  return RENT_BURDEN_QUINTILE_COLORS.map((color, i) => {
    const lower = i === 0 ? null : breaks[i - 1];
    const upper = breaks[i];
    const label = lower == null ? `≤ ${upper.toFixed(2)}` : `${lower.toFixed(2)} – ${upper.toFixed(2)}`;
    return { color, label };
  });
}

/**
 * Which 1-5 quintile class a rent_burden value falls into, applying the
 * ADR-004 breaks (the SA2's own value rounded to 3 decimals, same as
 * shown in the UI) client-side. Does not recompute the breaks themselves
 * -- those stay authoritative in run_metadata.json (ADR-004 rejected
 * computing quintiles in the browser); this only looks up which of the
 * five already-decided brackets a known value lands in, for side-panel
 * copy such as "this SA2's own burden is in quintile 3".
 */
export function quintileForValue(value, breaks) {
  if (value == null) return null;
  const rounded = Math.round(value * 1000) / 1000;
  for (let i = 0; i < breaks.length; i++) {
    if (rounded <= breaks[i]) return i + 1;
  }
  return breaks.length;
}
