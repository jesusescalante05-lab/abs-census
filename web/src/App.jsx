import { useMemo, useState } from "react";
import MapView from "./components/MapView";
import LayerSwitch from "./components/LayerSwitch";
import Legend from "./components/Legend";
import SidePanel from "./components/SidePanel";
import ZoomToClusterButton from "./components/ZoomToClusterButton";
import AboutPage from "./components/AboutPage";
import { useSa2Data } from "./data/useSa2Data";

export default function App() {
  const { detailsByCode, metadata, regions, loading, error } = useSa2Data();
  const [activeLayer, setActiveLayer] = useState("confidence");
  const [selectedRegionCode, setSelectedRegionCode] = useState(null);
  const [map, setMap] = useState(null);
  const [showAbout, setShowAbout] = useState(false);

  const regionsByCode = useMemo(() => {
    if (!regions) return null;
    return new Map(regions.map((r) => [r.code, r]));
  }, [regions]);

  // Which confidence classes actually occur in this run's data (ADR-005):
  // the legend should not list a class like "conflicting" that this run
  // has zero of, even though mapStyle.js keeps all seven for the map's
  // paint expression and for future runs that might have one.
  const presentConfidenceClasses = useMemo(() => {
    if (!detailsByCode) return null;
    return new Set([...detailsByCode.values()].map((d) => d.gi_star_confidence));
  }, [detailsByCode]);

  // Shared by map clicks and the SA2 selector: selecting a region also
  // flies the map to it, so the two ways of picking an SA2 (plan
  // Section 6) stay in sync.
  function selectRegion(code) {
    setSelectedRegionCode(code);
    const region = code && regionsByCode?.get(code);
    if (region && map) {
      map.flyTo({ center: region.coordinates, zoom: Math.max(map.getZoom(), 11), duration: 800 });
    }
  }

  if (error) {
    return <div className="app-error">Could not load map data: {String(error.message ?? error)}</div>;
  }

  return (
    <div className="app">
      <MapView
        activeLayer={activeLayer}
        selectedRegionCode={selectedRegionCode}
        onSelectRegion={selectRegion}
        onMapReady={setMap}
      />

      <header className="app-header">
        <h1>Perth Housing Stress Explorer</h1>
        <LayerSwitch activeLayer={activeLayer} onChange={setActiveLayer} />
        <button type="button" className="about-button" onClick={() => setShowAbout(true)}>
          About
        </button>
      </header>

      {!loading && (
        <SidePanel
          regions={regions}
          detail={selectedRegionCode ? detailsByCode.get(selectedRegionCode) : null}
          selectedRegionCode={selectedRegionCode}
          onSelectRegion={selectRegion}
          quintileBreaks={metadata.rent_burden_quintile_breaks}
        />
      )}

      {!loading && (
        <div className="map-controls-bottom-left">
          <ZoomToClusterButton map={map} bbox={metadata.robust_hotspot_bbox_4326} />
          <Legend
            activeLayer={activeLayer}
            quintileBreaks={metadata.rent_burden_quintile_breaks}
            presentConfidenceClasses={presentConfidenceClasses}
          />
        </div>
      )}

      {showAbout && !loading && <AboutPage metadata={metadata} onClose={() => setShowAbout(false)} />}
    </div>
  );
}
