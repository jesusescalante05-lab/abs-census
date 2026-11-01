# ADR-002: Hotspot analysis method

**Product:** Perth Housing Stress Explorer
**Status:** Accepted
**Date:** 2026-10-29
**Phase:** 3 (Spatial statistics)
**Depends on:** ADR-001 (indicator, `rent_burden`, 165 valid SA2s)

## Context

ADR-001 defines `rent_burden` for 185 Greater Perth SA2s, 165 of them valid (`rent_status = 'ok'`).
A choropleth shows where burden is high, but not whether high values cluster more than chance would
produce. This ADR records how clustering is tested, how results are classified, and how they are
displayed.

## Decision

### Units and inputs

- Units: the **165** SA2s with `rent_status = 'ok'` in `analysis.housing_stress_sa2`.
- Variable: `rent_burden`.
- Excluded SA2s (ADR-001 rule R2) take no part in the weights or the statistics.

### Spatial weights

| Role | Definition | Reason |
|---|---|---|
| Primary | **Queen contiguity** (shared edge or corner), row-standardised | Standard for areal data; neighbours are defined by shared boundaries |
| Sensitivity | **k-nearest neighbours, k = 6**, row-standardised | Tests whether results depend on the neighbour definition |

KNN distances are computed in **GDA2020 / MGA zone 50 (EPSG:7850)**, from a **representative point of each SA2’s main populated part (see Amendment 1)**, so offshore parts (for example Rottnest Island) do not displace
an SA2's location.

### Statistics

| Statistic | Question | Implementation |
|---|---|---|
| Global Moran's I | Is burden clustered across Perth at all? | `esda.Moran`, 9,999 permutations |
| Getis-Ord Gi\* | Is this SA2's **neighbourhood** high or low? | `esda.G_Local(star=True)`, 9,999 permutations |
| Local Moran's I | Is this SA2 **similar to or different from** its neighbours? | `esda.Moran_Local`, 9,999 permutations |

- **Permutations: 9,999.** The smallest possible p-value is 1 / (permutations + 1). With 999, that
  floor (0.001) is above the strictest multiple-testing bar for 165 tests (0.05 / 165 ≈ 0.0003), so
  significance could be impossible regardless of the data.
- **Seed: 12345**, fixed for reproducibility (global seed for `Moran`, which has no `seed`
  argument; explicit `seed` for the local statistics).

### Multiple-testing correction

- **Benjamini–Hochberg step-up FDR, α = 0.05**, via `esda.fdr` (esda 2.10.0), applied separately to
  each statistic and each weights definition.
- Verified from the installed source code: the function returns the cutoff k·α/n at the largest
  rank k whose p-value is below it, and returns α/n only when no p-value meets the condition.
  The function's docstring describes this fallback the other way round; the code is authoritative.

### Confidence classes (Gi\*, used for the map)

| Class | Rule |
|---|---|
| `robust_hotspot` | Gi\* hotspot under **both** queen and KNN |
| `possible_hotspot` | Gi\* hotspot under **one** weights definition only |
| `robust_coldspot` | Gi\* coldspot under both |
| `possible_coldspot` | Gi\* coldspot under one only |
| `conflicting` | Hotspot under one, coldspot under the other (none in run 1; treated as not significant and flagged) |
| `not_significant` | Otherwise |
| `not_analysed` | `rent_status <> 'ok'` (ADR-001) |

### Display

- The map shows the **Gi\* confidence class**. Hotspots and coldspots are described as
  *"part of a high-burden area"* or *"part of a low-burden area"*, never as the SA2's own burden level.
- The side panel shows the SA2's own `rent_burden` and its **local Moran quadrant**, so cases such as
  a low-burden SA2 inside a high-burden area (spatial outlier) are explained.
- Global Moran's I is reported on the About page.

## Amendment 1: main populated part (bug fix)

**Date:** 2026-11-04

**What was wrong.** KNN points used a representative point of each SA2's largest polygon part by
area. For Fremantle, the largest part is Rottnest Island (19.18 km²), larger than any mainland part
(the largest is 6.70 km²). Fremantle's KNN point was therefore about 18 km offshore. This affected
Fremantle's own KNN neighbours and any SA2 for which Fremantle was among the six nearest.

**Why this is a fix, not a method change.** The rule's stated purpose was that offshore parts must not
displace an SA2's location. The implementation did not meet that purpose. The correction follows from
that stated intent and was decided before the corrected results were seen.

**New rule.** An SA2's *main populated part* is the polygon part containing the most 2021 Residential
mesh blocks; if no part contains any, the largest part by area (EPSG:7850). It is computed once, in
`analysis.sa2_main_part`, and used by both the KNN weights and the display geometry (ADR-003).

**Runs.** Run 1 is kept in `analysis.hotspot_runs` but is superseded by run 2. Queen-based results are
not affected, because queen contiguity does not use points.

**Scope of the bug.** Five analysed SA2s have more than one polygon part: Fremantle (5), Rockingham (6),
Mandurah – South (3), Safety Bay – Shoalwater (3) and Halls Head – Erskine (2). Only for Fremantle did
the old rule pick a different part (Rottnest Island: 1 residential mesh block; mainland part chosen by
the new rule: 131). For the other four, the largest part by area is also the most populated part, so
the old rule gave the right result by coincidence rather than by design.

## Results (run 1, superseded; see Amendment 1)

`run_id = 1`, `code_commit = b82cf28643c9d8cb8bd3bbe98410b29f483c097b`, libpysal 4.15.1, esda 2.10.0.

**Global Moran's I = 0.3625, z = 7.03, p = 0.0001** (the minimum possible): burden is strongly
clustered.

| Class | SA2s |
|---|---|
| Robust hotspot | Mandurah, Greenfields, Mandurah – South, Mandurah – East, Mandurah – North |
| Possible hotspot | Halls Head – Erskine, Falcon – Wannanup, Dawesville – Bouvard, Pinjarra |
| Robust coldspot | Claremont (WA) |
| Possible coldspot | Fremantle, Bicton – Palmyra, Subiaco – Shenton Park, Bullsbrook |

Sensitivity: 8 of 165 SA2s change Gi\* class between queen and KNN. **No SA2 reverses** between
hotspot and coldspot; all changes are between significant and not significant.

## Results (run 2, current)

`run_id = 2`, `code_commit = 596fd7f323b1fcf8e39901d1d3670ae7cc6eb2f5`, libpysal 4.15.1, esda 2.10.0.
Same seed (12345), permutations (9,999) and data as run 1; only the KNN points changed (Amendment 1).

**Global Moran's I = 0.3625, z = 7.03, p = 0.0001**, identical to run 1, as expected.
All queen-based results are identical to run 1.

| Class | SA2s |
|---|---|
| Robust hotspot | Mandurah, Greenfields, Mandurah – South, Mandurah – East, Mandurah – North |
| Possible hotspot | Halls Head – Erskine, Falcon – Wannanup, Dawesville – Bouvard, Pinjarra |
| Robust coldspot | Claremont (WA) |
| Possible coldspot | Subiaco – Shenton Park, Bullsbrook |

**Changes from run 1** (`sql/diagnostics/compare_hotspot_runs.sql`): Fremantle and Bicton – Palmyra
changed from possible coldspot to not significant. Both had been KNN coldspots only because
Fremantle's KNN point was on Rottnest Island. No other SA2 changed.

Sensitivity: 6 of 165 SA2s change Gi\* class between queen and KNN; no SA2 reverses between hotspot
and coldspot.

### Findings to explain in the product

1. **Water gap in Peel.** Queen weights split into two components (162 and 3 SA2s). Dawesville –
   Bouvard, Falcon – Wannanup and Halls Head – Erskine touch only each other: the estuary and the
   Dawesville Channel separate them from Mandurah (closest gap 122 m). Under queen weights their
   neighbourhood is tiny, so they are significant only under KNN. They are shown as possible hotspots,
   with this reason. Fremantle’s run 1 KNN result was also affected by an offshore point; see Amendment 1.

2. **Gi\* and local Moran answer different questions.** Mandurah – North (`rent_burden` 0.188, below
   the Perth median) is a Gi\* hotspot because its neighbourhood is high, and a local Moran spatial
   outlier because it is lower than its neighbours. Claremont (0.222) is the mirror case.
3. **Visual clusters are not always statistical clusters.** The inner-suburb band that appears red in
   the quintile map is not significant after FDR correction.

## Alternatives considered

| Option | Decision | Reason |
|---|---|---|
| 999 permutations | Rejected | p-value floor above the multiple-testing bar for 165 tests |
| No multiple-testing correction | Rejected | About 8 of 165 SA2s would appear significant by chance alone |
| Benjamini–Yekutieli FDR | Not used | Not what `esda.fdr` implements; BH is the verified procedure |
| Changing the neighbour rule after seeing results (for example contiguity with a 200 m tolerance to connect the Peel trio) | **Rejected** | Choosing a method because of its results undermines the test. The water gap is reported instead |
| Single weights definition only | Rejected | Hides how much results depend on the neighbour definition |
| Local Moran as the map layer | Rejected for the map | Quadrants are harder to explain to general audiences; kept in the side panel |

## Limitations

1. Inherits all ADR-001 limitations (area-level proxy, mismatched medians, perturbation, 2021 only).
2. **Modifiable areal unit problem:** results depend on SA2 boundaries; other units (SA1, LGA) could
   show different clusters.
3. Hotspots describe **areas**, not individual households.
4. Significance depends on the neighbour definition for some SA2s; the confidence classes make this
   visible rather than hiding it.

## Implementation (next step)

- Add `gi_star_confidence` (classes above) to `analysis.housing_stress_hotspots_latest`, computed from
  `gi_star_class` and `knn_gi_star_class`, with `not_analysed` for excluded SA2s.
- Validation checks: 185 rows; class counts match run 1 (5 robust hotspots, 4 possible hotspots,
  1 robust coldspot, 2 possible coldspots, 0 conflicting, 20 not analysed, 153 not significant (run 2)).
