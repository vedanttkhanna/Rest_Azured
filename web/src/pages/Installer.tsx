import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  BriefcaseBusiness,
  Check,
  Download,
  FileSpreadsheet,
  Upload,
  Zap,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/Auth";
import { ApiError, createBatch } from "../api/client";
import { useJobs } from "../api/queries";
import { JobsTable } from "../components/JobsTable";
import { Empty, ErrorPanel, Kpi, Loading, PageHeading } from "../components/ui";
import { parseAddresses, downloadText, jobsCsv } from "../lib/csv";
import { number } from "../lib/format";

export default function Installer() {
  const auth = useAuth();
  const query = useJobs();
  const queryClient = useQueryClient();
  const [csv, setCsv] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const mutation = useMutation({
    mutationFn: createBatch,
    onSuccess: (response) => {
      setResult(response.job_ids);
      setCsv("");
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  if (auth.role !== "Installer")
    return (
      <Empty icon={BriefcaseBusiness} title="A workspace for installers.">
        <p>
          Batch assessments need an Installer account. Ask your account
          administrator to enable access, then sign out and back in.
        </p>
        <Link className="button" to="/assess">
          Assess one roof <ArrowUpRight size={17} />
        </Link>
      </Empty>
    );
  const jobs = query.data?.jobs || [];
  const complete = jobs.filter((job) => job.status === "done");
  const submit = () => {
    setError("");
    setResult([]);
    // A CSV parse error must not appear next to the previous attempt's API error.
    mutation.reset();
    try {
      mutation.mutate(parseAddresses(csv));
    } catch (exception) {
      setError((exception as Error).message);
    }
  };
  const upload = async (file?: File) => {
    if (!file) return;
    // Clear the input so choosing the same file again still fires onChange.
    if (fileRef.current) fileRef.current.value = "";
    if (file.size > 1_000_000) {
      setError("Use a CSV smaller than 1 MB with at most 25 rows.");
      return;
    }
    try {
      setCsv(await file.text());
      setError("");
    } catch {
      setError("Could not read that file. Paste the CSV below instead.");
    }
  };
  return (
    <div className="page-enter">
      <PageHeading
        eyebrow="MORE ROOFTOPS. MORE POSSIBILITIES."
        title="Your installer workspace."
        description="Go from a list of locations to a shortlist of solar opportunities."
        action={
          <span className="pill">
            <BriefcaseBusiness size={15} /> INSTALLER ACCESS
          </span>
        }
      />
      <div className="kpi-grid installer-kpis">
        <Kpi
          icon={FileSpreadsheet}
          label="Total assessments"
          value={number(jobs.length)}
          note="Across your account"
        />
        <Kpi
          icon={Check}
          label="Reports ready"
          value={number(complete.length)}
          note="Available to view and export"
        />
        <Kpi
          icon={Zap}
          label="Assessed capacity"
          value={number(
            complete.reduce((sum, job) => sum + (job.kw_dc || 0), 0),
            1,
          )}
          unit="kW"
          note="Sum of completed estimates"
          tone="sunny"
        />
      </div>
      <section className="card batch-card">
        <div className="batch-intro">
          <span className="icon-tile">
            <Upload size={22} />
          </span>
          <h2>A whole list of brighter roofs.</h2>
          <p>
            Upload or paste a CSV with an <code>address</code> column, or{" "}
            <code>lat,lng</code> columns. Up to 25 locations per batch.
          </p>
          {auth.local && <p>For this local workspace, use <code>lat,lng</code> rows. Address-only rows need AWS geocoding credentials.</p>}
          <button
            className="text-button"
            onClick={() =>
              downloadText(
                'address,lat,lng\n"Mayur Vihar sample",28.6039825,77.2935395\n',
                "solar-batch-template.csv",
              )
            }
          >
            Download CSV template <Download size={14} />
          </button>
          <div className="batch-limit">
            {auth.local ? "Local assessments run one at a time on this Mac" : "Installer allowance: 100 assessments / IST day"}
          </div>
        </div>
        <div className="batch-editor">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            aria-label="Upload addresses CSV"
            onChange={(event) => void upload(event.target.files?.[0])}
          />
          <button
            className="upload-button"
            onClick={() => fileRef.current?.click()}
          >
            <Upload size={18} /> Choose a CSV file <span>or paste below</span>
          </button>
          <label className="sr-only" htmlFor="batch-csv">
            CSV addresses or coordinates
          </label>
          <textarea
            id="batch-csv"
            value={csv}
            onChange={(event) => setCsv(event.target.value)}
            placeholder={
              'address\n"Sector 6, Dwarka, New Delhi"\n"Pocket A, Mayur Vihar Phase 1, Delhi"'
            }
            rows={5}
          />
          <button
            className="button"
            disabled={mutation.isPending || !csv.trim()}
            onClick={submit}
          >
            {mutation.isPending
              ? "Starting assessments…"
              : "Assess these rooftops"}
            <ArrowUpRight size={17} />
          </button>
        </div>
      </section>
      {error && <ErrorPanel error={error} />}
      {mutation.error && (
        <>
          <ErrorPanel error={mutation.error} />
          {mutation.error instanceof ApiError &&
            mutation.error.body.invalid && (
              <ul className="invalid-batch">
                {mutation.error.body.invalid.map((entry) => (
                  <li key={entry.index}>
                    Entry {entry.index + 1}: {entry.error}
                  </li>
                ))}
              </ul>
            )}
        </>
      )}
      {result.length > 0 && (
        <div className="success-note" role="status">
          <Check size={18} />
          <div>
            <strong>{result.length} rooftop assessments started.</strong>
            <p>
              Follow their progress in the table below. Every successful report
              is saved.
            </p>
          </div>
        </div>
      )}
      <section className="card installer-table">
        <div className="section-heading compact">
          <div>
            <h2>Your rooftop pipeline</h2>
            <p>Fresh results appear as assessments finish.</p>
          </div>
          <button
            className="button secondary small"
            disabled={!jobs.length}
            onClick={() =>
              downloadText(jobsCsv(jobs), "installer-rooftops.csv")
            }
          >
            <Download size={15} /> Export CSV
          </button>
        </div>
        {query.isPending ? (
          <Loading />
        ) : query.error ? (
          <ErrorPanel error={query.error} retry={() => void query.refetch()} />
        ) : jobs.length ? (
          <JobsTable jobs={jobs} />
        ) : (
          <Empty title="Ready for your first batch.">
            <p>Add locations above to start your pipeline.</p>
          </Empty>
        )}
      </section>
    </div>
  );
}
