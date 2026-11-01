import { useEffect, useRef } from "react";
// maplibre-gl 6.x ships only named exports (no default) -- a namespace
// import keeps every maplibregl.* call below unchanged.
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import {
  buildConfidenceColorExpression,
  buildQuintileColorExpression,
  LABELLED_CONFIDENCE_CLASSES,
  SA2_OUTLINE_STYLE,
} from "../config/mapStyle";
import { dataUrl } from "../data/useSa2Data";

// pmtiles.Protocol registers the `pmtiles://` URL scheme with MapLibre so
// it can read a local .pmtiles file directly (HTTP range requests), with
// no separate tile server. Registered once at module load, not per-mount.
let protocolRegistered = false;
function ensurePmtilesProtocol() {
  if (protocolRegistered) return;
  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  protocolRegistered = true;
}

// A small diagonal-hatch tile for not_analysed / no-quintile SA2s,
// generated at runtime rather than shipping a separate image asset.
// map.addImage() only accepts HTMLImageElement, ImageBitmap, ImageData,
// or {width, height, data} -- not a bare HTMLCanvasElement -- so this
// returns the canvas's ImageData, not the canvas itself.
function createHatchImageData(size = 8, color = "#9e9e9e") {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, size);
  ctx.lineTo(size, 0);
  ctx.stroke();
  return ctx.getImageData(0, 0, size, size);
}

const PERTH_CENTER = [115.86, -31.95];
const PERTH_INITIAL_ZOOM = 9;

export default function MapView({ activeLayer, selectedRegionCode, onSelectRegion, onMapReady }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);

  // Create the map once.
  useEffect(() => {
    ensurePmtilesProtocol();

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: "https://tiles.openfreemap.org/styles/positron",
      center: PERTH_CENTER,
      zoom: PERTH_INITIAL_ZOOM,
    });
    mapRef.current = map;
    onMapReady?.(map);

    map.on("load", () => {
      map.addImage("not-analysed-hatch", createHatchImageData());

      map.addSource("sa2-display", {
        type: "vector",
        url: `pmtiles://${dataUrl("sa2_display.pmtiles")}`,
      });
      map.addSource("sa2-outline", {
        type: "vector",
        url: `pmtiles://${dataUrl("sa2_outline.pmtiles")}`,
      });
      map.addSource("sa2-points", {
        type: "geojson",
        data: dataUrl("sa2_points.geojson"),
      });

      // Choropleth fill (colour expression swapped by the activeLayer effect below).
      map.addLayer({
        id: "sa2-display-fill",
        type: "fill",
        source: "sa2-display",
        "source-layer": "sa2_display",
        paint: {
          "fill-color": buildConfidenceColorExpression(),
          "fill-opacity": 0.85,
        },
      });

      // Hatch overlay for not_analysed / no-quintile SA2s, on top of the
      // base fill above.
      map.addLayer({
        id: "sa2-display-hatch",
        type: "fill",
        source: "sa2-display",
        "source-layer": "sa2_display",
        filter: ["==", ["get", "display_type"], "full_extent"],
        paint: { "fill-pattern": "not-analysed-hatch" },
      });

      // Thin SA2 outline (ADR-003: #c8c8c8, visual only -- drawn from the
      // full-extent outline layer, not the display/mask layer).
      map.addLayer({
        id: "sa2-outline-line",
        type: "line",
        source: "sa2-outline",
        "source-layer": "sa2_outline",
        paint: {
          "line-color": SA2_OUTLINE_STYLE.color,
          "line-width": SA2_OUTLINE_STYLE.widthPx,
        },
      });

      // Invisible full-extent hit layer for click/hover: the visible
      // display-fill layer has real gaps (non-residential land), so using
      // it for click detection would miss clicks there. This layer covers
      // each SA2's *full* boundary instead.
      map.addLayer({
        id: "sa2-outline-fill-hit",
        type: "fill",
        source: "sa2-outline",
        "source-layer": "sa2_outline",
        paint: { "fill-opacity": 0 },
      });

      // Selected-SA2 highlight outline.
      map.addLayer({
        id: "sa2-selected-outline",
        type: "line",
        source: "sa2-outline",
        "source-layer": "sa2_outline",
        filter: ["==", ["get", "region_code"], ""],
        paint: { "line-color": "#222222", "line-width": 2 },
      });

      // Labels: robust_hotspot / robust_coldspot SA2 names only (ADR-003).
      // text-allow-overlap/text-ignore-placement are left false (MapLibre's
      // default) explicitly, rather than relied on implicitly, so this
      // layer stays collision-aware against the basemap's own place
      // labels (e.g. "Mandurah") -- a label here is dropped rather than
      // forced on top of one already placed (ADR-005).
      map.addLayer({
        id: "sa2-labels",
        type: "symbol",
        source: "sa2-points",
        filter: ["in", ["get", "gi_star_confidence"], ["literal", LABELLED_CONFIDENCE_CLASSES]],
        layout: {
          "text-field": ["get", "region_name"],
          "text-font": ["Noto Sans Bold"],
          "text-size": 11,
          "text-anchor": "center",
          "text-allow-overlap": false,
          "text-ignore-placement": false,
        },
        paint: {
          "text-color": "#1a1a1a",
          "text-halo-color": "#ffffff",
          "text-halo-width": 1.5,
        },
      });

      map.on("mouseenter", "sa2-outline-fill-hit", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "sa2-outline-fill-hit", () => {
        map.getCanvas().style.cursor = "";
      });
      map.on("click", "sa2-outline-fill-hit", (e) => {
        const feature = e.features?.[0];
        if (feature) onSelectRegion?.(feature.properties.region_code);
      });
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- map created once; see effects below for prop-driven updates
  }, []);

  // Swap the fill colour expression when the active layer changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const applyPaint = () => {
      if (!map.getLayer("sa2-display-fill")) return;
      const expr = activeLayer === "quintile" ? buildQuintileColorExpression() : buildConfidenceColorExpression();
      map.setPaintProperty("sa2-display-fill", "fill-color", expr);
      map.setFilter(
        "sa2-display-hatch",
        activeLayer === "quintile"
          ? ["==", ["get", "rent_burden_quintile"], null]
          : ["==", ["get", "display_type"], "full_extent"],
      );
    };
    if (map.isStyleLoaded()) applyPaint();
    else map.once("load", applyPaint);
  }, [activeLayer]);

  // Highlight the selected SA2.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const applyFilter = () => {
      if (!map.getLayer("sa2-selected-outline")) return;
      map.setFilter("sa2-selected-outline", ["==", ["get", "region_code"], selectedRegionCode ?? ""]);
    };
    if (map.isStyleLoaded()) applyFilter();
    else map.once("load", applyFilter);
  }, [selectedRegionCode]);

  return <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />;
}
