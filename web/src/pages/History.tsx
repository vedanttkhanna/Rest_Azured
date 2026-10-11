import { useState } from "react";
import { ArrowUpRight, Download, Search, Sun } from "lucide-react";
import { Link } from "react-router-dom";
import { useJobs } from "../api/queries";
import { JobsTable } from "../components/JobsTable";
import { Empty, ErrorPanel, Loading, PageHeading } from "../components/ui";
import { jobsCsv, downloadText } from "../lib/csv";

export default function History() {
  const query = useJobs();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const jobs = query.data?.jobs || [];
  const filtered = jobs.filter(
    (job) =>
      (status === "all" ||
        (status === "running"
          ? !["done", "failed"].includes(job.status)
          : job.status === status)) &&
      `${job.address || ""} ${job.job_id}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <div className="page-enter">
      <PageHeading
        eyebrow="YOUR GROWING SOLAR STORY"
        title="Every rooftop, in one place."
        description="Revisit your estimates and watch new assessments take shape."
        action={
          <Link to="/assess" className="button">
            New assessment <ArrowUpRight size={17} />
          </Link>
        }
      />
      <section className="card history-card">
        <div className="table-toolbar">
          <div className="search-field">
            <Search size={17} />
            <input
              aria-label="Search assessments"
              placeholder="Search a rooftop…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="table-tools">
            <select
              aria-label="Filter assessments by status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="all">All statuses</option>
              <option value="done">Ready</option>
              <option value="running">In progress</option>
              <option value="failed">Failed</option>
            </select>
            <button
              className="button secondary small"
              disabled={!filtered.length}
              onClick={() =>
                downloadText(jobsCsv(filtered), "solar-assessments.csv")
              }
            >
              <Download size={15} /> Export CSV
            </button>
          </div>
        </div>
        {query.isPending ? (
          <Loading />
        ) : query.error ? (
          <ErrorPanel error={query.error} retry={() => void query.refetch()} />
        ) : !filtered.length ? (
          <Empty
            title={
              jobs.length
                ? "No matching rooftops."
                : "Your first brighter roof awaits."
            }
            icon={Sun}
          >
            <p>
              {jobs.length
                ? "Try another search or status filter."
                : "Start an assessment and find out what your roof can do."}
            </p>
            {!jobs.length && (
              <Link className="button" to="/assess">
                Check my rooftop <ArrowUpRight size={16} />
              </Link>
            )}
          </Empty>
        ) : (
          <JobsTable jobs={filtered} />
        )}
        <div className="table-footer">
          {filtered.length} of {jobs.length} assessments{" "}
          <span>Only assessments owned by your account appear here.</span>
        </div>
      </section>
    </div>
  );
}
