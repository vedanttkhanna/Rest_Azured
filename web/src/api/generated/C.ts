/* Generated from contracts/schemas. Run npm run generate:types. */

export interface Report {
  job_id: string;
  status: "done";
  building: {
    roof_area_m2: number;
    usable_area_m2: number;
    [k: string]: unknown;
  };
  system: {
    panel_count: number;
    panel_wp: number;
    kw_dc: number;
    tilt_deg: number;
    azimuth_deg: number;
    [k: string]: unknown;
  };
  panels: {
    type: "FeatureCollection";
    features: {
      type: "Feature";
      geometry: {
        type: "Polygon";
        /**
         * @minItems 1
         */
        coordinates: [
          [[number, number], [number, number], [number, number], [number, number], ...[number, number][]],
          ...[[number, number], [number, number], [number, number], [number, number], ...[number, number][]][]
        ];
        [k: string]: unknown;
      };
      properties: {
        [k: string]: unknown;
      };
      [k: string]: unknown;
    }[];
    [k: string]: unknown;
  };
  energy: {
    annual_kwh: number;
    /**
     * @minItems 12
     * @maxItems 12
     */
    monthly_kwh: [number, number, number, number, number, number, number, number, number, number, number, number];
    specific_yield_kwh_per_kwp: number;
    shade_loss_pct: number;
    [k: string]: unknown;
  };
  finance: {
    capex_inr: number;
    subsidy_inr: number;
    net_cost_inr: number;
    annual_savings_inr: number;
    /**
     * Null when annual savings are zero; no finite payback.
     */
    payback_years: number | null;
    [k: string]: unknown;
  };
  co2_t_per_year: number;
  heatmap_png_s3_uri: string;
  /**
   * @minItems 4
   * @maxItems 4
   */
  heatmap_bounds: [number, number, number, number];
  assumptions: {
    [k: string]: unknown;
  };
  data_sources: {
    weather: string;
    heights: string;
    [k: string]: unknown;
  };
  model_version: string;
  [k: string]: unknown;
}
