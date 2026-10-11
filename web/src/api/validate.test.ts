import { describe, expect, it } from "vitest";
import fixture from "../../../contracts/fixtures/report_C.json";
import { validateReport } from "./validate";
describe("report C validation", () => {
  it("accepts the real project fixture and nullable payback", () => {
    expect(validateReport(fixture).system.panel_count).toBe(30);
    expect(
      validateReport({
        ...fixture,
        finance: { ...fixture.finance, payback_years: null },
      }).finance.payback_years,
    ).toBeNull();
  });
  it("rejects malformed monthly arrays and nonnumeric GeoJSON", () => {
    expect(() =>
      validateReport({
        ...fixture,
        energy: { ...fixture.energy, monthly_kwh: [1] },
      }),
    ).toThrow("shared data contract");
    const invalid = structuredClone(fixture);
    invalid.panels.features[0].geometry.coordinates[0][0][0] =
      "bad" as unknown as number;
    expect(() => validateReport(invalid)).toThrow("shared data contract");
  });
});
