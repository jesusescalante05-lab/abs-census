// ADR-002: "Global Moran's I is reported on the About page." Everything
// here is read from run_metadata.json -- no number is retyped by hand, so
// this page can't drift from the run that produced the data on screen.
export default function AboutPage({ metadata, onClose }) {
  return (
    <div className="about-page" role="dialog" aria-modal="true" aria-labelledby="about-heading">
      <button type="button" className="about-close" onClick={onClose} aria-label="Close">
        ×
      </button>
      <h1 id="about-heading">About the Perth Housing Stress Explorer</h1>

      <p>
        This map shows <strong>rent burden</strong> — the ratio of median weekly rent to median weekly
        household income — across the 185 SA2 areas of Greater Perth, from the 2021 Census. It is an
        area-level proxy, not a count of households in housing stress: see the limitations below.
      </p>

      <h2>Is burden clustered?</h2>
      <p>
        Global Moran's I = <strong>{metadata.global_moran_i.toFixed(4)}</strong> (z ={" "}
        {metadata.global_moran_z_sim.toFixed(2)}, p = {metadata.global_moran_p_sim}), from{" "}
        {metadata.permutations.toLocaleString()} permutations. A positive value well above zero means
        rent burden is more spatially clustered across Perth than chance alone would produce.
      </p>

      <h2>Limitations</h2>
      <ul>
        <li>Rent burden compares renting households' rent to all households' income, so it likely understates renters' own burden.</li>
        <li>It describes typical costs in an area, not how many households are in stress.</li>
        <li>Capped social housing rents lower median rent in areas with a lot of it.</li>
        <li>Small counts are perturbed by the ABS for confidentiality and can be unreliable.</li>
        <li>2021 only; the 2021 Census was held during COVID-19 conditions.</li>
        <li>Island parts of multipart SA2s (e.g. Rottnest Island) show the value of the whole SA2, not the island itself.</li>
      </ul>

      <h2>Run details</h2>
      <dl className="about-run-details">
        <dt>Run</dt>
        <dd>#{metadata.run_id}</dd>
        <dt>Code commit</dt>
        <dd>
          <code>{metadata.code_commit.slice(0, 12)}</code>
        </dd>
        <dt>Run at</dt>
        <dd>{new Date(metadata.run_at).toLocaleString()}</dd>
        <dt>Libraries</dt>
        <dd>
          libpysal {metadata.libpysal_version}, esda {metadata.esda_version}
        </dd>
      </dl>

      <h2>Attribution</h2>
      <p className="about-attribution">{metadata.abs_attribution}</p>
    </div>
  );
}
