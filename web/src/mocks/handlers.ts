import { http, HttpResponse, delay } from "msw";
import { config } from "../config";
import { inServiceArea } from "../lib/geo";
import type { Job, JobStatus, LocationInput } from "../api/types";
import { sampleJob, sampleReport, sampleLocation } from "./fixtures";

const jobs = new Map<string, Job>([[sampleJob.job_id, sampleJob]]);
const started = new Map<string, number>();
const steps: JobStatus[] = [
  "queued",
  "fetching",
  "segmenting",
  "simulating",
  "done",
];
const api = config.apiUrl;

function resolve(input: string | LocationInput) {
  if (typeof input === "string" || ("address" in input && !("lat" in input))) {
    const address = typeof input === "string" ? input : input.address;
    if (!address.trim()) throw new Error("Please add an address.");
    return {
      lat: sampleLocation.lat,
      lng: sampleLocation.lng,
      address: `${address.trim()} · demo fixture`,
    };
  }
  if (!inServiceArea(input.lat, input.lng))
    throw new Error("This location is outside the Delhi/NCR service area.");
  return {
    ...input,
    address: input.address || "Selected rooftop · demo fixture",
  };
}
function create(input: string | LocationInput) {
  const loc = resolve(input);
  const id = crypto.randomUUID();
  jobs.set(id, {
    job_id: id,
    status: "queued",
    ...loc,
    created_at: new Date().toISOString(),
  });
  started.set(id, Date.now());
  return id;
}
function refresh(id: string): Job | undefined {
  const job = jobs.get(id);
  const start = started.get(id);
  if (!job || start === undefined) return job;
  job.status = steps[Math.min(4, Math.floor((Date.now() - start) / 2300))];
  if (job.status === "done") {
    job.report = { ...sampleReport, job_id: id };
    job.heatmap_png_url = "/demo/shade.png";
    job.kw_dc = sampleReport.system.kw_dc;
    job.annual_kwh = sampleReport.energy.annual_kwh;
    job.payback_years = sampleReport.finance.payback_years;
    // Every demo uses the same fixture geometry, irrespective of submitted location.
    job.lat = sampleLocation.lat;
    job.lng = sampleLocation.lng;
  }
  return job;
}

export const handlers = [
  http.get(`${api}/jobs`, async () => {
    await delay(150);
    const summaries = [...jobs.keys()]
      .map((id) => {
        const {
          report: _report,
          heatmap_png_url: _url,
          ...summary
        } = refresh(id)!;
        return summary;
      })
      .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
    return HttpResponse.json({ jobs: summaries });
  }),
  http.get(`${api}/jobs/:id`, async ({ params }) => {
    await delay(150);
    const job = refresh(String(params.id));
    return job
      ? HttpResponse.json(job)
      : HttpResponse.json({ error: "Job not found." }, { status: 404 });
  }),
  http.post(`${api}/jobs`, async ({ request }) => {
    await delay(250);
    try {
      return HttpResponse.json(
        { job_id: create((await request.json()) as LocationInput) },
        { status: 201 },
      );
    } catch (error) {
      return HttpResponse.json(
        { error: (error as Error).message },
        { status: 400 },
      );
    }
  }),
  http.post(`${api}/jobs/batch`, async ({ request }) => {
    if (request.headers.get("X-Demo-Role") !== "Installer")
      return HttpResponse.json(
        {
          error: "Batch assessments are available to Installer accounts only.",
        },
        { status: 403 },
      );
    const body = (await request.json()) as {
      addresses: Array<string | LocationInput>;
    };
    if (
      !Array.isArray(body.addresses) ||
      !body.addresses.length ||
      body.addresses.length > config.maxBatch
    )
      return HttpResponse.json(
        { error: `Add 1–${config.maxBatch} addresses.` },
        { status: 400 },
      );
    const invalid = body.addresses.flatMap((input, index) => {
      try {
        resolve(input);
        return [];
      } catch (error) {
        return [{ index, input, error: (error as Error).message }];
      }
    });
    if (invalid.length)
      return HttpResponse.json(
        { error: "Some entries are invalid; nothing was created.", invalid },
        { status: 400 },
      );
    return HttpResponse.json(
      { job_ids: body.addresses.map(create) },
      { status: 201 },
    );
  }),
];
