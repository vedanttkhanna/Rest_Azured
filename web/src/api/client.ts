import { fetchAuthSession } from "aws-amplify/auth";
import { config } from "../config";
import type { ErrorBody, Job, JobSummary, LocationInput } from "./types";
import { validateReport } from "./validate";

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ErrorBody,
  ) {
    super(body.error || body.message || `Request failed (${status})`);
    this.name = "ApiError";
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (config.useMocks) {
    headers.set(
      "X-Demo-Role",
      sessionStorage.getItem("solar-demo-role") || "Homeowner",
    );
  } else if (config.localApi) {
    headers.set("X-Local-Role", sessionStorage.getItem("solar-local-role") || "Homeowner");
  } else {
    const { tokens } = await fetchAuthSession();
    const token = tokens?.idToken?.toString();
    if (!token)
      throw new ApiError(401, { error: "Please sign in again to continue." });
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${config.apiUrl}${path}`, { ...init, headers });
  const body = await response
    .json()
    .catch(() => ({
      error:
        response.statusText || "The server returned an unreadable response.",
    }));
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}

export const createJob = (input: LocationInput) =>
  api<{ job_id: string }>("/jobs", {
    method: "POST",
    body: JSON.stringify(input),
  });
export const getJob = async (id: string, signal?: AbortSignal) => {
  const job = await api<Job>(`/jobs/${encodeURIComponent(id)}`, { signal });
  if (job.report) job.report = validateReport(job.report);
  return job;
};
export const getJobs = (signal?: AbortSignal) =>
  api<{ jobs: JobSummary[] }>("/jobs", { signal });
export const createBatch = (addresses: Array<string | LocationInput>) =>
  api<{ job_ids: string[] }>("/jobs/batch", {
    method: "POST",
    body: JSON.stringify({ addresses }),
  });

export const getLocalHealth = () =>
  api<{ status: string; mode: string; geocoding: boolean; model_version: string }>("/health");
