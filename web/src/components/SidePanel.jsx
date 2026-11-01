import { GI_STAR_CONFIDENCE_CLASSES, RENT_BURDEN_QUINTILE_COLORS, quintileForValue } from "../config/mapStyle";

// ADR-001 R6: rent_status / mortgage_status explain why a burden is NULL.
const STATUS_NOTES = {
  few_households: "Too few households in this SA2 (fewer than 100) for a reliable estimate.",
  few_renters: "Too few renting households in this SA2 for a reliable median rent.",
  few_mortgaged: "Too few households with a mortgage in this SA2 for a reliable median repayment.",
  no_median: "ABS could not calculate a median for this SA2.",
};

const QUADRANT_NEIGHBOUR_WORD = { H: "high-burden", L: "low-burden" };

function confidenceLabel(value) {
  return GI_STAR_CONFIDENCE_CLASSES.find((c) => c.value === value)?.label ?? value;
}

function pct(value) {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}

// ADR-004's quintile bands, drawn as five EQUAL-WIDTH segments (each is
// 20% of Perth's 165 valid SA2s by construction) rather than to a 0-based
// value scale -- a value scale would make class 1 (0 to ~0.17) look like
// most of Perth, when it's the same 20% share as every other class
// (ADR-005). The dot sits within its own band, positioned by how far the
// value falls between that band's own lower and upper edge.
function QuintileStrip({ value, breaks }) {
  if (value == null || !breaks) return null;
  const quintile = quintileForValue(value, breaks);
  const bandLower = quintile === 1 ? 0 : breaks[quintile - 2];
  const bandUpper = breaks[quintile - 1];
  const withinBand = bandUpper > bandLower ? (value - bandLower) / (bandUpper - bandLower) : 0.5;
  const clampedWithinBand = Math.min(1, Math.max(0, withinBand));
  const dotPercent = ((quintile - 1 + clampedWithinBand) / RENT_BURDEN_QUINTILE_COLORS.length) * 100;

  return (
    <div className="quintile-strip-wrap">
      <div className="quintile-strip">
        {RENT_BURDEN_QUINTILE_COLORS.map((color) => (
          <span key={color} className="quintile-strip-segment" style={{ backgroundColor: color }} />
        ))}
        <span
          className="quintile-strip-dot"
          style={{ left: `${dotPercent}%` }}
          title={`This SA2: ${value.toFixed(3)} (quintile ${quintile})`}
        />
      </div>
      <div className="quintile-strip-scale">
        {RENT_BURDEN_QUINTILE_COLORS.map((_, i) => (
          <span key={i}>{i + 1}</span>
        ))}
      </div>
    </div>
  );
}

// Plain-language note for a local Moran "spatial outlier" (ADR-002: Gi*
// and local Moran answer different questions -- an SA2 can be a hotspot
// by neighbourhood while being below the Perth median itself, or the
// reverse). quadrant's second letter is the neighbours' side (H/L);
// the first letter (this SA2's own side) is not needed for the sentence.
function spatialOutlierNote(detail, breaks) {
  if (detail.local_moran_class !== "spatial_outlier" || !detail.local_moran_quadrant) return null;
  const quintile = quintileForValue(detail.rent_burden, breaks);
  const neighbourWord = QUADRANT_NEIGHBOUR_WORD[detail.local_moran_quadrant[1]];
  if (quintile == null || !neighbourWord) return null;
  return `This SA2's own burden is in quintile ${quintile}, but it sits inside an area that's mostly ${neighbourWord}.`;
}

export default function SidePanel({ regions, detail, selectedRegionCode, onSelectRegion, quintileBreaks }) {
  return (
    <aside className="side-panel">
      <label htmlFor="sa2-selector" className="sa2-selector-label">
        Find an SA2
      </label>
      <select
        id="sa2-selector"
        className="sa2-selector"
        value={selectedRegionCode ?? ""}
        onChange={(e) => onSelectRegion(e.target.value || null)}
      >
        <option value="">Select an SA2…</option>
        {regions?.map((r) => (
          <option key={r.code} value={r.code}>
            {r.name}
          </option>
        ))}
      </select>

      {!detail && <p className="side-panel-hint">Click an SA2 on the map, or choose one above.</p>}

      {detail && (
        <div className="side-panel-detail">
          <h2>{detail.region_name}</h2>

          <dl>
            <dt>Burden cluster</dt>
            <dd>{confidenceLabel(detail.gi_star_confidence)}</dd>

            <dt>Rent burden</dt>
            <dd>
              {detail.rent_status === "ok" ? detail.rent_burden.toFixed(3) : "—"}
              {detail.rent_status !== "ok" && (
                <span className="side-panel-status-note"> {STATUS_NOTES[detail.rent_status]}</span>
              )}
            </dd>

            <dt>Mortgage burden</dt>
            <dd>
              {detail.mortgage_status === "ok" ? detail.mortgage_burden.toFixed(3) : "—"}
              {detail.mortgage_status !== "ok" && (
                <span className="side-panel-status-note"> {STATUS_NOTES[detail.mortgage_status]}</span>
              )}
            </dd>

            <dt>Households</dt>
            <dd>{detail.households?.toLocaleString() ?? "—"}</dd>

            <dt>Renter share</dt>
            <dd>{pct(detail.renter_share)}</dd>

            <dt>Social housing share</dt>
            <dd>{pct(detail.social_housing_share)}</dd>
          </dl>

          {detail.rent_status === "ok" && (
            <div className="quintile-strip-block">
              <p className="quintile-strip-label">Where this SA2's rent burden sits, among Perth's 165 valid SA2s</p>
              <QuintileStrip value={detail.rent_burden} breaks={quintileBreaks} />
            </div>
          )}

          {spatialOutlierNote(detail, quintileBreaks) && (
            <p className="side-panel-outlier-note">{spatialOutlierNote(detail, quintileBreaks)}</p>
          )}

          <p className="side-panel-limitation">Area-level estimate; likely understates renters' burden.</p>
        </div>
      )}
    </aside>
  );
}
