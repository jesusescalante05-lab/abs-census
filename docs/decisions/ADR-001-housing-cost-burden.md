# ADR-001: Housing cost burden indicator

**Product:** Perth Housing Stress Explorer
**Status:** Accepted
**Date:** 2026-10-22
**Phase:** 1 (Define the indicator)

## Context

The product maps housing stress across Greater Perth. The standard Australian definition is the
30/40 rule: a household in the lowest 40% of incomes that spends more than 30% of its income on
housing. The 2021 General Community Profile DataPacks do not contain a household-level
"housing cost ≥ 30% of income" variable (checked by searching `census.variable`), so the
indicator must be an area-level proxy built from the variables that exist.

## Decision

### Scope

- Census year: **2021**
- Geography: **SA2**, filtered by `geo.region.parent_gccsa = '5GPER'` (Greater Perth, **185 SA2s**)
- 2016 comparison is out of scope for version 1

### Indicators

Always filter on `table_id` **and** `short_code`: short codes such as `Total_Total` repeat across tables.

| Indicator | Formula | Source |
|---|---|---|
| `households` | `Total_Total` | G37 |
| `renting` | `R_Tot_Total` | G37 |
| `mortgaged` | `O_MTG_Total` | G37 |
| `rent_burden` | `Median_rent_weekly / Median_tot_hhd_inc_weekly` | G02 |
| `mortgage_burden` | `(Median_mortgage_repay_monthly × 12 / 52) / Median_tot_hhd_inc_weekly` | G02 |
| `renter_share` | `R_Tot_Total / (Total_Total − Ten_type_NS_Total)` | G37 |
| `social_housing_share` | `(R_ST_h_auth_Total + R_Com_Hp_Total) / R_Tot_Total` | G37 |

`rent_burden` and `mortgage_burden` are the primary map indicators. The others are context, shown
in the side panel.

### Data quality rules

| Rule | Description | Reason |
|---|---|---|
| R1 | A median of 0 is treated as NULL | ABS reports 0 when a median cannot be calculated; it is not a real value |
| R2 | All indicators are NULL when `households < 100` | Natural break in the data: 20 SA2s have 0–16 households, the next has 112 |
| R3 | `rent_burden` is NULL when `renting < 30` | A median from very few renters is unstable |
| R4 | `mortgage_burden` is NULL when `mortgaged < 30` | Same reason, for mortgages |
| R5 | Every division uses `NULLIF(denominator, 0)` | No division-by-zero errors |
| R6 | Each primary indicator has its own status column explaining any NULL: `rent_status` (`ok`, `few_households`, `few_renters`, `no_median`) and `mortgage_status` (`ok`, `few_households`, `few_mortgaged`, `no_median`) | One row can have a valid rent burden and a missing mortgage burden (for example, Osborne Park Industrial); a single status cannot explain both, and a NULL median must be explained too |

Expected effect: **165 SA2s** with a valid `rent_burden`; **20 SA2s** marked `few_households`
(industrial estates, national parks, Perth Airport, Kings Park). At least one further SA2
(Osborne Park Industrial, 6 mortgaged households) has no `mortgage_burden`.

### Classification and display

- Map classes: **quintiles** across valid Greater Perth SA2s (relative burden within Perth).
- **0.30 is a reference line only**, in the legend and charts. It is not used as a stress threshold,
  because the ratio understates renters' burden (see limitations).
- SA2s with `“the displayed indicator’s status is not ok”` are drawn in neutral grey, labelled with the reason.

### Spatial statistics (input to Phase 3)

- Hotspot analysis runs on the 165 valid SA2s only; excluded SA2s are removed from the spatial weights.
- Neighbours: queen contiguity. SA2s left without neighbours after exclusion are reported and handled
  explicitly, not silently dropped.

## Limitations

1. **Mismatched populations.** Median rent is calculated for renting households, median income for
   all households (including owners, who tend to earn more). The ratio therefore likely
   **understates** renters' burden.
2. **Area-level proxy.** It describes typical costs and incomes in an area, not how many households
   are in stress. Conclusions about individual households cannot be drawn from it.
3. **Social housing.** Public and community housing rents are capped relative to income, which lowers
   median rent in areas with a lot of it. `social_housing_share` is shown alongside to flag this.
4. **ABS perturbation.** Each table is perturbed independently, so small counts are unreliable and
   tables do not always agree for tiny areas (for example, national parks with 0 households but a
   median rent). Rules R2–R4 limit this.
5. **Single year.** 2021 only. The 2021 Census was held during COVID-19 conditions.

## Alternatives considered

| Option | Decision | Reason |
|---|---|---|
| Count of households paying ≥ 30% of income | Rejected for v1 | Not available in the GCP DataPacks |
| Absolute 0.30 threshold as "stress" | Rejected | Ratio understates burden; only 6 SA2s reach 0.30, mostly non-residential |
| Composite index | Deferred | Harder to explain and defend; reconsider after v1 |
| ABS TableBuilder affordability variables | Upgrade path for v2 | Closer to the 30/40 rule; needs a scripted or documented manual download |

## Validation checks for Phase 2

The `analysis.housing_stress_sa2` view must pass these checks:

- Returns exactly **185** rows (all Greater Perth SA2s, including excluded ones with a `data_status`).
- **165** rows with `rent_status = 'ok'` and a non-NULL `rent_burden`.
- Every NULL `rent_burden` has `rent_status <> 'ok'`; every NULL `mortgage_burden` has `mortgage_status <> 'ok'`.
- The count of `mortgage_status = 'ok'` is reported, not asserted (measured: 164 on 2021 data; the one exclusion beyond the 20  `few_households` SA2s is Osborne Park Industrial, `few_mortgaged`).
- Spot values match the Phase 1 exploration: Mandurah `rent_burden` = 0.300,
  Mosman Park – Peppermint Grove = 0.135.
- No `rent_burden` or `mortgage_burden` equals 0.
- Every row has geometry (non-NULL `geom`).
