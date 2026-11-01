// Toggle between the two maps defined in ADR-003: the primary confidence
// map (where burden clusters) and the secondary quintile map (how high
// burden is in each SA2). A native radiogroup, not a custom widget, so
// it is keyboard- and screen-reader-accessible for free.
const OPTIONS = [
  { value: "confidence", label: "Burden clusters" },
  { value: "quintile", label: "Burden level" },
];

export default function LayerSwitch({ activeLayer, onChange }) {
  return (
    <fieldset className="layer-switch">
      <legend>Map shows</legend>
      {OPTIONS.map((opt) => (
        <label key={opt.value}>
          <input
            type="radio"
            name="active-layer"
            value={opt.value}
            checked={activeLayer === opt.value}
            onChange={() => onChange(opt.value)}
          />
          {opt.label}
        </label>
      ))}
    </fieldset>
  );
}
