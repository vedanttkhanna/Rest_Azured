/* Generated from contracts/schemas. Run npm run generate:types. */

/**
 * @minItems 2
 * @maxItems 2
 */
export type Position = [number, number];
export type Confidence = number;

/**
 * Target building's roof and the obstacles on it, as a WGS84 GeoJSON FeatureCollection. Defined in the 'Shared team contract' section of the P*.md briefs.
 */
export interface Segmentation {
  job_id: string;
  model_version: string;
  type: "FeatureCollection";
  /**
   * Human-readable caveat. Set when no roof was found (features empty) or when the roof is approximate, e.g. no footprint was supplied and the roof was capped to a radius around the job point.
   */
  warning?: string;
  features: Feature[];
  [k: string]: unknown;
}
export interface Feature {
  type: "Feature";
  geometry: Polygon;
  properties: Roof | Obstacle;
  [k: string]: unknown;
}
export interface Polygon {
  type: "Polygon";
  /**
   * @minItems 1
   */
  coordinates: [
    [Position, Position, Position, Position, ...Position[]],
    ...[Position, Position, Position, Position, ...Position[]][]
  ];
  [k: string]: unknown;
}
export interface Roof {
  id: string;
  kind: "roof";
  roof_type: "flat" | "pitched";
  azimuth_deg: number | null;
  tilt_deg: number | null;
  confidence: Confidence;
  [k: string]: unknown;
}
export interface Obstacle {
  id: string;
  kind: "obstacle";
  roof_id: string;
  class: "water_tank" | "stair_room" | "ac_unit" | "solar_heater" | "existing_pv" | "parapet" | "tree" | "other";
  height_m: number | null;
  confidence: Confidence;
  [k: string]: unknown;
}
