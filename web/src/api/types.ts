export type { RoofJob } from "./generated/A";
export type { Segmentation } from "./generated/B";
export type { Report } from "./generated/C";
import type { Report } from "./generated/C";
import type { Segmentation } from "./generated/B";

export type Role = "Homeowner" | "Installer";
export type JobStatus =
  "queued" | "fetching" | "segmenting" | "simulating" | "done" | "failed";
export type LocationInput =
  { address: string } | { lat: number; lng: number; address?: string };
export interface JobSummary {
  job_id: string;
  status: JobStatus;
  address?: string | null;
  lat?: number;
  lng?: number;
  created_at?: string;
  updated_at?: string;
  kw_dc?: number;
  annual_kwh?: number;
  payback_years?: number | null;
  error?: string;
}
export interface Job extends JobSummary {
  report?: Report;
  heatmap_png_url?: string | null;
  // Local development API additions; shared A/B/C contracts remain unchanged.
  segmentation?: Segmentation;
  image_png_url?: string;
  image_bounds?: [number, number, number, number];
}
export interface InvalidBatchEntry {
  index: number;
  input: unknown;
  error: string;
}
export interface ErrorBody {
  error?: string;
  message?: string;
  invalid?: InvalidBatchEntry[];
}
