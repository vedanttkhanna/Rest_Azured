import { describe, expect, it } from "vitest";
import { jobsCsv, parseAddresses } from "./csv";
import { inServiceArea, imageCoordinates } from "./geo";
import { payback } from "./format";

describe("installer CSV intake", () => {
  it("preserves quoted Delhi addresses", () =>
    expect(
      parseAddresses(
        'address\n"Sector 6, Dwarka, Delhi"\n"Mayur Vihar, Delhi"',
      ),
    ).toEqual(["Sector 6, Dwarka, Delhi", "Mayur Vihar, Delhi"]));
  it("accepts named coordinate columns in any order", () =>
    expect(parseAddresses("lng,address,lat\n77.29,Sample,28.60")).toEqual([
      { lat: 28.6, lng: 77.29, address: "Sample" },
    ]));
  it("accepts one-column addresses without a header", () =>
    expect(parseAddresses("Dwarka Delhi\nMayur Vihar Delhi")).toEqual([
      "Dwarka Delhi",
      "Mayur Vihar Delhi",
    ]));
  it("rejects out-of-area and incomplete coordinate rows", () => {
    expect(() => parseAddresses("lat,lng\n19.1,72.9")).toThrow("service area");
    expect(() => parseAddresses("lat,lng\n28.6,")).toThrow("both lat and lng");
  });
  it("rejects empty and oversized batches", () => {
    expect(() => parseAddresses("address")).toThrow("between 1 and 25");
    expect(() =>
      parseAddresses(["address", ...Array(26).fill("Delhi")].join("\n")),
    ).toThrow("between 1 and 25");
  });
  it("rejects unquoted comma addresses instead of truncating them", () =>
    expect(() => parseAddresses("Sector 6, Dwarka, Delhi")).toThrow(
      "double quotes",
    ));
});
describe("report interchange", () => {
  it("exports nullable payback as an empty CSV field and neutralizes formulas", () => {
    const result = jobsCsv([
      {
        job_id: "job",
        status: "done",
        address: '=HYPERLINK("bad")',
        payback_years: null,
      },
    ]);
    expect(result).toContain("'=HYPERLINK");
    expect(result).not.toContain("null");
    expect(result).toContain("payback_years");
  });
  it("places heatmap corners in MapLibre’s NW NE SE SW order", () =>
    expect(imageCoordinates([77, 28, 78, 29])).toEqual([
      [77, 29],
      [78, 29],
      [78, 28],
      [77, 28],
    ]));
  it("accepts Delhi boundaries and rejects non-finite coordinates", () => {
    expect(inServiceArea(28.4, 76.8)).toBe(true);
    expect(inServiceArea(28.9, 77.4)).toBe(true);
    expect(inServiceArea(NaN, 77)).toBe(false);
    expect(inServiceArea(28.91, 77)).toBe(false);
  });
  it("does not invent a payback for zero-generation reports", () => {
    expect(payback(null)).toBe("—");
    expect(payback(undefined)).toBe("—");
    expect(payback(4.8)).toBe("4.8 yrs");
  });
});
