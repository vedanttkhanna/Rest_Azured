import reportFixture from "../../../contracts/fixtures/report_C.json";
import jobFixture from "../../../contracts/fixtures/job_A.json";
import segmentationFixture from "../../../contracts/fixtures/seg_B.json";
import type { Report, Job } from "../api/types";
import { validateReport } from "../api/validate";

export const sampleReport: Report = validateReport(reportFixture);
export const sampleLocation = jobFixture;
export const sampleSegmentation = segmentationFixture;
export const sampleJob: Job = {
  job_id: sampleReport.job_id,
  status: "done",
  address: jobFixture.address,
  lat: jobFixture.lat,
  lng: jobFixture.lng,
  created_at: "2026-10-11T04:30:00Z",
  kw_dc: sampleReport.system.kw_dc,
  annual_kwh: sampleReport.energy.annual_kwh,
  payback_years: sampleReport.finance.payback_years,
  report: sampleReport,
  heatmap_png_url: "/demo/shade.png",
};
