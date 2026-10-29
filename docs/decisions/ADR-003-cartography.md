# ADR-003: Cartography and display

**Product:** Perth Housing Stress Explorer
**Status:** Accepted
**Date:** 2026-11-04
**Phase:** 4 (Cartography)
**Depends on:** ADR-001 (indicator), ADR-002 (hotspot confidence classes)

## Context

A first QGIS draft coloured whole SA2s by `gi_star_confidence`. Large, mostly rural SA2s dominated
the map: the *possible* hotspot area (Pinjarra and the Peel coast) appeared several times larger than
the *robust* Mandurah cluster, and Bullsbrook (a possible coldspot) was the most visible blue area.
The least certain results were the most visible. Rottnest Island, part of the Fremantle SA2, also
appeared as a low-burden area.

A test in QGIS that coloured only residential mesh blocks fixed the area bias: the robust Mandurah
cluster became the dominant feature. Rottnest remained coloured because it is a single Residential
mesh block (MB 50077840000, 19.19 km²), which is correct ABS data.

## Decision

### Maps

| Map | Variable | Classes |
|---|---|---|
| Primary | `gi_star_confidence` (ADR-002) | Seven confidence classes |
| Secondary | `rent_burden` (ADR-001) | Quintiles across valid Greater Perth SA2s; 0.30 shown as a reference only |

### Display geometry (display only; statistics stay at SA2 level)

1. **Residential mask.** Analysed SA2s (`rent_status = 'ok'`) are drawn using only their 2021
   mesh blocks with category `Residential`.
2. **Mainland rule.** Only mesh blocks inside the **largest polygon part** of their SA2 are drawn.
   This is the same largest-part rule used for KNN weights in ADR-002. It removes island parts
   (for example Rottnest Island) without naming them.
3. **Attribute join, not spatial intersection.** Mesh blocks nest exactly within SA2s, so they are
   matched by `SA2_CODE21 = region_code`. This avoids boundary slivers.
4. **Dissolve.** The selected mesh blocks are dissolved into **one display shape per SA2**.
5. **Not analysed SA2s** are drawn at **full extent with a hatch**, so "no data for this area"
   stays visible even where an SA2 has few or no residential mesh blocks.
6. **SA2 outlines** are drawn on top with no fill, in thin light grey (`#c8c8c8`, 0.2 mm), so areas
   remain recognisable.

### Colours and labels (primary map)

| Class | Colour | Legend label |
|---|---|---|
| `robust_hotspot` | `#b2182b` | Part of a high-burden area |
| `possible_hotspot` | `#ef8a62` | Possibly part of a high-burden area |
| `not_significant` | `#f2f2f2` | No significant pattern |
| `possible_coldspot` | `#67a9cf` | Possibly part of a low-burden area |
| `robust_coldspot` | `#2166ac` | Part of a low-burden area |
| `conflicting` | `#999999` | Result depends on method |
| `not_analysed` | `#bdbdbd` with hatch | Not analysed (too few households) |

- A red–blue diverging palette (ColorBrewer RdBu) shows direction; dark and light shades show
  confidence. The palette remains distinguishable for common forms of colour blindness.
- Labels follow ADR-002: a hotspot is *part of a high-burden area*, never "high stress".
- Map labels are shown only for `robust_hotspot` and `robust_coldspot` SA2s.
- Basemap: light grey, no satellite imagery.
- A zoomed view of Mandurah–Peel is provided (inset in print layouts; a "zoom to cluster" control
  on the web map).

### Secondary map

- Sequential palette ColorBrewer YlOrRd, five classes, starting from a light colour rather than
  white so the lowest class is not read as "no data".
- Legend note: classes show relative ranking within Perth.

### Pipeline

- 2021 mesh block boundaries for Greater Perth are added to the scripted pipeline: download entry in
  `data/sources.csv`, loaded into PostGIS with their category and SA2 code. Storage design (new
  table or new level in `geo.region`) is decided in the implementation plan.
- The display geometry is produced by SQL, not by manual QGIS steps.
- The QGIS style is saved as `qgis/styles/hotspots_confidence.qml` and committed.

## Alternatives considered

| Option | Decision | Reason |
|---|---|---|
| Colour whole SA2s | Rejected | Area bias: large rural SA2s with uncertain results dominate |
| Remove Rottnest manually | Rejected | Not reproducible; would not handle other islands |
| Drop residential mesh blocks above an area limit | Rejected | Arbitrary threshold |
| Dwelling-density mask using mesh block counts | Deferred | Needs another dataset; reconsider if the residential mask proves insufficient |
| Spatial intersection with SA2 polygons | Rejected | Unnecessary: mesh blocks nest in SA2s; an attribute join is exact |
| Mask not-analysed SA2s too | Rejected | Their hatch would largely disappear, hiding where data is missing |

## Limitations

1. The mask is cosmetic: statistics are computed for whole SA2s, including their non-residential land.
2. "Residential" is the ABS classification by main land use; residential mesh blocks can contain some
   non-residential land, and some dwellings are in other categories.
3. Island parts are not coloured, but they remain part of their SA2's statistics (ADR-001
   limitation 6).

## Validation checks for implementation

- One display shape per analysed SA2 that has at least one residential mesh block on its largest part.
- No display shape intersects Rottnest Island (MB 50077840000 excluded).
- Every display shape lies within its SA2.
- All 20 not-analysed SA2s are present at full extent.
- Class counts per `gi_star_confidence` match ADR-002 for every SA2 that has a display shape; any
  analysed SA2 without residential mesh blocks is listed by name.
