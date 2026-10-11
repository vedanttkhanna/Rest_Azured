import { ArrowUpRight, MapPin } from "lucide-react";
import { Link } from "react-router-dom";
import type { JobSummary } from "../api/types";
import { number, payback, date } from "../lib/format";
import { StatusBadge } from "./ui";

export function JobsTable({ jobs }: { jobs: JobSummary[] }) {
  return (
    <div className="table-scroll">
      <table className="jobs-table">
        <thead>
          <tr>
            <th>Rooftop</th>
            <th>Status</th>
            <th>System</th>
            <th>Annual energy</th>
            <th>Payback</th>
            <th>
              <span className="sr-only">Open report</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.job_id}>
              <td>
                <Link className="job-title" to={`/jobs/${job.job_id}`}>
                  <span className="job-location-icon">
                    <MapPin size={17} />
                  </span>
                  <span>
                    <strong>
                      {job.address ||
                        `Rooftop at ${number(job.lat || 0, 5)}, ${number(job.lng || 0, 5)}`}
                    </strong>
                    <small>{date(job.created_at)}</small>
                  </span>
                </Link>
              </td>
              <td>
                <StatusBadge status={job.status} />
              </td>
              <td>{job.kw_dc == null ? "—" : `${number(job.kw_dc, 2)} kW`}</td>
              <td>
                {job.annual_kwh == null ? "—" : `${number(job.annual_kwh)} kWh`}
              </td>
              <td>{payback(job.payback_years)}</td>
              <td>
                <Link
                  className="table-open"
                  to={`/jobs/${job.job_id}`}
                  aria-label={`Open assessment for ${job.address || job.job_id}`}
                >
                  <ArrowUpRight size={18} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
