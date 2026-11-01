import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  GI_STAR_CONFIDENCE_CLASSES,
  RENT_BURDEN_QUINTILE_COLORS,
  buildConfidenceColorExpression,
  buildQuintileColorExpression,
  buildQuintileLegendEntries,
  quintileForValue,
} from "./config/mapStyle";
import { dataUrl } from "./data/useSa2Data";
import LayerSwitch from "./components/LayerSwitch";
import Legend from "./components/Legend";
import SidePanel from "./components/SidePanel";
import ZoomToClusterButton from "./components/ZoomToClusterButton";

// ADR-004's quintile breaks, from the current committed run_metadata.json.
const BREAKS = [0.172, 0.187, 0.199, 0.215, 0.3];

describe("mapStyle (ADR-002/003/004 single source of truth)", () => {
  it("builds one match branch per confidence class, with a fallback", () => {
    const expr = buildConfidenceColorExpression();
    // ["match", get, value1, color1, ..., fallback]
    expect(expr[0]).toBe("match");
    expect((expr.length - 3) / 2).toBe(GI_STAR_CONFIDENCE_CLASSES.length);
  });

  it("builds one match branch per quintile colour, with a fallback", () => {
    const expr = buildQuintileColorExpression();
    expect((expr.length - 3) / 2).toBe(RENT_BURDEN_QUINTILE_COLORS.length);
  });

  it("builds 5 legend entries whose upper bound is the given break", () => {
    const entries = buildQuintileLegendEntries(BREAKS);
    expect(entries).toHaveLength(5);
    expect(entries[0].label).toBe("≤ 0.17");
    expect(entries[4].label).toContain("0.30");
  });

  it("quintileForValue places a value in the class whose break it does not exceed (ADR-004)", () => {
    // Mandurah - North, rent_burden 0.18807... -> rounds to 0.188, first
    // break >= it is 0.199 (class 3).
    expect(quintileForValue(0.18807092960773777, BREAKS)).toBe(3);
    // Claremont, rent_burden 0.2224... -> rounds to 0.222, above 0.215,
    // within the top class.
    expect(quintileForValue(0.22243713733075435, BREAKS)).toBe(5);
    // At the lowest break exactly.
    expect(quintileForValue(0.172, BREAKS)).toBe(1);
    expect(quintileForValue(null, BREAKS)).toBeNull();
  });
});

describe("dataUrl", () => {
  it("builds every data path from BASE_URL, not a hardcoded root", () => {
    expect(dataUrl("sa2_details.json")).toBe(`${import.meta.env.BASE_URL}data/sa2_details.json`);
  });
});

describe("LayerSwitch", () => {
  it("reports the newly chosen layer, and reflects the active one as checked", () => {
    const onChange = vi.fn();
    render(<LayerSwitch activeLayer="confidence" onChange={onChange} />);
    expect(screen.getByLabelText("Burden clusters")).toBeChecked();
    expect(screen.getByLabelText("Burden level")).not.toBeChecked();

    fireEvent.click(screen.getByLabelText("Burden level"));
    expect(onChange).toHaveBeenCalledWith("quintile");
  });
});

describe("Legend", () => {
  it("shows all seven confidence classes for the primary map, no quintile note", () => {
    render(<Legend activeLayer="confidence" quintileBreaks={BREAKS} />);
    GI_STAR_CONFIDENCE_CLASSES.forEach((c) => expect(screen.getByText(c.label)).toBeInTheDocument());
    expect(screen.queryByText(/relative ranking/)).not.toBeInTheDocument();
  });

  it("shows 5 quintile bands and the relative-ranking note for the secondary map", () => {
    render(<Legend activeLayer="quintile" quintileBreaks={BREAKS} />);
    expect(screen.getByText(/relative ranking within Perth/)).toBeInTheDocument();
    expect(screen.getByText("≤ 0.17")).toBeInTheDocument();
  });

  it("drops a confidence class this run has zero SA2s in (ADR-002/005: 'conflicting' in run 2)", () => {
    const present = new Set(["robust_hotspot", "not_significant", "not_analysed"]);
    render(<Legend activeLayer="confidence" quintileBreaks={BREAKS} presentConfidenceClasses={present} />);
    expect(screen.getByText("Part of a high-burden area")).toBeInTheDocument();
    expect(screen.queryByText("Result depends on method")).not.toBeInTheDocument();
    expect(screen.queryByText("Possibly part of a low-burden area")).not.toBeInTheDocument();
  });
});

describe("SidePanel", () => {
  const regions = [
    { code: "502011025", name: "Mandurah", coordinates: [115.74, -32.52] },
    { code: "999999999", name: "Example SA2", coordinates: [115.8, -32.0] },
  ];

  it("prompts for a selection when nothing is picked yet", () => {
    render(<SidePanel regions={regions} detail={null} selectedRegionCode={null} onSelectRegion={() => {}} quintileBreaks={BREAKS} />);
    expect(screen.getByText(/Click an SA2 on the map/)).toBeInTheDocument();
  });

  it("calls onSelectRegion with the chosen code (plan Section 6: keyboard-accessible selector)", () => {
    const onSelectRegion = vi.fn();
    render(<SidePanel regions={regions} detail={null} selectedRegionCode={null} onSelectRegion={onSelectRegion} quintileBreaks={BREAKS} />);
    fireEvent.change(screen.getByLabelText("Find an SA2"), { target: { value: "502011025" } });
    expect(onSelectRegion).toHaveBeenCalledWith("502011025");
  });

  it("explains a NULL burden via its status, rather than showing a number", () => {
    const detail = {
      region_name: "Example SA2",
      households: 40,
      renting: 5,
      mortgaged: 5,
      rent_status: "few_households",
      mortgage_status: "few_households",
      rent_burden: null,
      mortgage_burden: null,
      renter_share: 0.12,
      social_housing_share: 0,
      gi_star_confidence: "not_analysed",
      local_moran_quadrant: null,
      local_moran_class: null,
    };
    render(<SidePanel regions={regions} detail={detail} selectedRegionCode="999999999" onSelectRegion={() => {}} quintileBreaks={BREAKS} />);
    expect(screen.getAllByText(/Too few households/)[0]).toBeInTheDocument();
    expect(screen.getByText("Area-level estimate; likely understates renters' burden.")).toBeInTheDocument();
  });

  it("surfaces the spatial-outlier note for a Gi* hotspot below the Perth median (ADR-002 finding 2: Mandurah - North)", () => {
    const detail = {
      region_name: "Mandurah - North",
      households: 1000,
      renting: 300,
      mortgaged: 300,
      rent_status: "ok",
      mortgage_status: "ok",
      rent_burden: 0.18807092960773777,
      mortgage_burden: 0.25,
      renter_share: 0.3,
      social_housing_share: 0.05,
      gi_star_confidence: "robust_hotspot",
      local_moran_quadrant: "LH",
      local_moran_class: "spatial_outlier",
    };
    render(<SidePanel regions={regions} detail={detail} selectedRegionCode="502011025" onSelectRegion={() => {}} quintileBreaks={BREAKS} />);
    expect(screen.getByText(/own burden is in quintile 3.*mostly high-burden/)).toBeInTheDocument();
  });

  it("draws the quintile distribution strip with a dot at this SA2's value, only when its burden is valid", () => {
    const ok = {
      region_name: "Mandurah - North",
      households: 1000,
      renting: 300,
      mortgaged: 300,
      rent_status: "ok",
      mortgage_status: "ok",
      rent_burden: 0.18807092960773777,
      mortgage_burden: 0.25,
      renter_share: 0.3,
      social_housing_share: 0.05,
      gi_star_confidence: "robust_hotspot",
      local_moran_quadrant: "LH",
      local_moran_class: "spatial_outlier",
    };
    const { rerender, container } = render(
      <SidePanel regions={regions} detail={ok} selectedRegionCode="502011025" onSelectRegion={() => {}} quintileBreaks={BREAKS} />,
    );
    const dot = container.querySelector(".quintile-strip-dot");
    expect(dot).toHaveAttribute("title", "This SA2: 0.188 (quintile 3)");
    // Equal-width bands (ADR-005): quintile 3 of 5 occupies the 40-60%
    // span of the strip regardless of how wide that quintile's value
    // range is -- not a 0-based value scale, where it would sit near 63%
    // (0.188 / 0.3).
    const leftPercent = parseFloat(dot.style.left);
    expect(leftPercent).toBeGreaterThanOrEqual(40);
    expect(leftPercent).toBeLessThanOrEqual(60);

    rerender(
      <SidePanel
        regions={regions}
        detail={{ ...ok, rent_status: "few_households", rent_burden: null }}
        selectedRegionCode="502011025"
        onSelectRegion={() => {}}
        quintileBreaks={BREAKS}
      />,
    );
    expect(container.querySelector(".quintile-strip-dot")).not.toBeInTheDocument();
  });

  it("does not show an outlier note for an ordinary, not-significant SA2", () => {
    const detail = {
      region_name: "Melville",
      households: 1000,
      renting: 300,
      mortgaged: 300,
      rent_status: "ok",
      mortgage_status: "ok",
      rent_burden: 0.2,
      mortgage_burden: 0.25,
      renter_share: 0.3,
      social_housing_share: 0.05,
      gi_star_confidence: "not_significant",
      local_moran_quadrant: null,
      local_moran_class: "not_significant",
    };
    render(<SidePanel regions={regions} detail={detail} selectedRegionCode="502011025" onSelectRegion={() => {}} quintileBreaks={BREAKS} />);
    expect(screen.queryByText(/sits inside an area/)).not.toBeInTheDocument();
  });
});

describe("ZoomToClusterButton", () => {
  it("fits the map to the run's robust-hotspot bounding box, not a hardcoded extent", () => {
    const bbox = [115.71, -32.62, 115.81, -32.45];
    const map = { fitBounds: vi.fn() };
    render(<ZoomToClusterButton map={map} bbox={bbox} />);
    fireEvent.click(screen.getByText(/Zoom to robust hotspot cluster/));
    expect(map.fitBounds).toHaveBeenCalledWith(
      [
        [115.71, -32.62],
        [115.81, -32.45],
      ],
      expect.objectContaining({ padding: 40 }),
    );
  });

  it("renders nothing when no bounding box is available yet", () => {
    const { container } = render(<ZoomToClusterButton map={null} bbox={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
