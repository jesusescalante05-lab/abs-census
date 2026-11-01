import {
  GI_STAR_CONFIDENCE_CLASSES,
  QUINTILE_LEGEND_NOTE,
  buildQuintileLegendEntries,
} from "../config/mapStyle";

// Renders whichever map is active, reading its swatches from mapStyle.js
// (ADR-003) so the legend can never list a colour or label the map isn't
// actually using. For the confidence map, also drops any class this run
// has zero SA2s in (e.g. "conflicting" in run 2, ADR-002/ADR-005) --
// mapStyle.js keeps the full seven-class set for the map's paint
// expression and for future runs, but a legend entry nothing on the map
// uses would be misleading.
export default function Legend({ activeLayer, quintileBreaks, presentConfidenceClasses }) {
  const entries =
    activeLayer === "quintile" && quintileBreaks
      ? buildQuintileLegendEntries(quintileBreaks)
      : GI_STAR_CONFIDENCE_CLASSES.filter(
          (c) => !presentConfidenceClasses || presentConfidenceClasses.has(c.value),
        );

  return (
    <div className="legend">
      <h2>{activeLayer === "quintile" ? "Burden level (quintiles)" : "Burden clusters"}</h2>
      <ul>
        {entries.map((entry) => (
          <li key={entry.label}>
            <span className={entry.hatch ? "legend-swatch legend-swatch--hatch" : "legend-swatch"} style={{ backgroundColor: entry.color }} />
            {entry.label}
          </li>
        ))}
      </ul>
      {activeLayer === "quintile" && <p className="legend-note">{QUINTILE_LEGEND_NOTE}</p>}
    </div>
  );
}
