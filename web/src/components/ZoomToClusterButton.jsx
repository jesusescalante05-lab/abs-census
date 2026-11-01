// ADR-003: "a zoom to cluster control on the web map" -- flies to the
// robust-hotspot bounding box recorded in run_metadata.json at export
// time, not a hardcoded Mandurah-Peel extent, so it stays correct if a
// future run finds hotspots somewhere else.
export default function ZoomToClusterButton({ map, bbox }) {
  if (!bbox) return null;

  const handleClick = () => {
    if (!map) return;
    const [west, south, east, north] = bbox;
    map.fitBounds(
      [
        [west, south],
        [east, north],
      ],
      { padding: 40, duration: 1000 },
    );
  };

  return (
    <button type="button" className="zoom-to-cluster" onClick={handleClick}>
      Zoom to robust hotspot cluster
    </button>
  );
}
