/* Generated from contracts/schemas. Run npm run generate:types. */

/**
 * @minItems 2
 * @maxItems 2
 */
export type Position = [number, number];

/**
 * One assessment job. The api Lambda creates job_id/lat/lng/address; P2's fetch step adds the imagery fields and writes the completed document to s3://<jobs-bucket>/jobs/{job_id}/job_A.json. Defined in the 'Shared team contract' section of the P*.md briefs.
 */
export interface RoofJob {
  job_id: string;
  lat: number;
  lng: number;
  address?: string | null;
  /**
   * RGB tile for P1's model: 512x512 px, centred on (lat, lng), PNG or TIFF. s3://<bucket>/jobs/{job_id}/rgb.png in AWS; a repo-relative path in contracts/fixtures.
   */
  image_s3_uri: string;
  /**
   * [minLng, minLat, maxLng, maxLat] of the tile, WGS84.
   *
   * @minItems 4
   * @maxItems 4
   */
  image_bounds: [number, number, number, number];
  /**
   * Metres per pixel of the tile.
   */
  gsd_m: number;
  /**
   * Height raster if Google Solar provided one, else null.
   */
  dsm_s3_uri?: string | null;
  /**
   * Target building footprint (WGS84). Strongly recommended: without it P1 caps the roof to 12 m around the point.
   */
  footprint?: null | Polygon;
  imagery_source: "google_solar" | "esri" | "upload";
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
