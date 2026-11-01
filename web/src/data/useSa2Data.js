import { useEffect, useState } from "react";

// Every data URL is built from import.meta.env.BASE_URL, not a hardcoded
// "/data/..." path, so the app works correctly under a GitHub Pages
// project sub-path (set via VITE_BASE_PATH at build time).
export function dataUrl(filename) {
  return `${import.meta.env.BASE_URL}data/${filename}`;
}

/**
 * Fetches sa2_details.json, run_metadata.json and sa2_points.geojson once
 * on mount. Returns { detailsByCode, metadata, regions, loading, error }:
 * - detailsByCode is a Map keyed by region_code for O(1) side-panel lookups.
 * - regions is the 185 { code, name, coordinates } entries from
 *   sa2_points.geojson, sorted by name, for the SA2 selector (plan
 *   Section 6) -- the points file is already loaded by MapView as a map
 *   source, but the selector needs the full list up front, not just
 *   whatever is in view.
 */
export function useSa2Data() {
  const [state, setState] = useState({
    detailsByCode: null,
    metadata: null,
    regions: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      fetch(dataUrl("sa2_details.json")).then((r) => r.json()),
      fetch(dataUrl("run_metadata.json")).then((r) => r.json()),
      fetch(dataUrl("sa2_points.geojson")).then((r) => r.json()),
    ])
      .then(([details, metadata, points]) => {
        if (cancelled) return;
        const detailsByCode = new Map(details.map((d) => [d.region_code, d]));
        const regions = points.features
          .map((f) => ({
            code: f.properties.region_code,
            name: f.properties.region_name,
            coordinates: f.geometry.coordinates,
          }))
          .sort((a, b) => a.name.localeCompare(b.name));
        setState({ detailsByCode, metadata, regions, loading: false, error: null });
      })
      .catch((error) => {
        if (cancelled) return;
        setState({ detailsByCode: null, metadata: null, regions: null, loading: false, error });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
