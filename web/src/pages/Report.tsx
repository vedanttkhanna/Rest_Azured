import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowUpRight,
  Download,
  Leaf,
  MapPin,
  RefreshCw,
  Ruler,
  Share2,
  Sun,
  Wallet,
  Zap,
  Grid2X2,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { useJob } from "../api/queries";
import { Progress } from "../components/Progress";
import {
  Kpi,
  PageHeading,
  ErrorPanel,
  Loading,
  StatusBadge,
} from "../components/ui";
import { MapView } from "../components/MapView";
import { MonthlyChart } from "../components/MonthlyChart";
import { AssumptionsPanel } from "../components/AssumptionsPanel";
import { sampleJob } from "../mocks/fixtures";
import { config } from "../config";
import { money, number, payback, date } from "../lib/format";
import type { Job } from "../api/types";

export function ReportContent({
  job,
  sample,
  refresh,
}: {
  job: Job;
  sample: boolean;
  refresh?: () => void;
}) {
  const [shareMessage, setShareMessage] = useState("");
  useEffect(() => {
    let original: Array<[HTMLDetailsElement, boolean]> = [];
    const beforePrint = () => {
      original = [
        ...document.querySelectorAll<HTMLDetailsElement>(
          ".report-page details",
        ),
      ].map((element) => [element, element.open]);
      original.forEach(([element]) => {
        element.open = true;
      });
    };
    const afterPrint = () => {
      original.forEach(([element, open]) => {
        element.open = open;
      });
      original = [];
    };
    window.addEventListener("beforeprint", beforePrint);
    window.addEventListener("afterprint", afterPrint);
    return () => {
      window.removeEventListener("beforeprint", beforePrint);
      window.removeEventListener("afterprint", afterPrint);
      afterPrint();
    };
  }, []);
  const report = job.report!;
  const share = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setShareMessage(
        sample
          ? "Sample link copied."
          : config.localApi
            ? "Link copied. This report is saved in the local workspace on this Mac."
            : "Link copied. Only your signed-in account can open this report.",
      );
    } catch {
      setShareMessage("Copy this page’s URL from your address bar.");
    }
  };
  const print = async () => {
    await document.fonts.ready;
    window.print();
  };
  return (
    <div className="report-page page-enter">
      <Link to="/history" className="back-link">
        <ArrowLeft size={14} /> All assessments
      </Link>
      <PageHeading
        eyebrow={
          sample ? "EXAMPLE · MAYUR VIHAR FIXTURE" : "YOUR ROOFTOP, REIMAGINED"
        }
        title="A brighter outlook for your roof."
        description={job.address || "Your selected rooftop"}
        action={
          <div className="report-actions">
            <button className="button secondary small" onClick={share}>
              <Share2 size={15} /> Share link
            </button>
            <button className="button small" onClick={print}>
              <Download size={15} /> Save PDF
            </button>
          </div>
        }
      />
      {shareMessage && (
        <p className="share-message" role="status">
          {shareMessage}
        </p>
      )}
      {sample && (
        <div className="sample-report-note">
          <Sun size={17} />
          <p>
            This is the project’s real Mayur Vihar fixture, with simulated solar
            results. Demo submissions reuse this geometry; these numbers are not
            an assessment of another rooftop.
          </p>
        </div>
      )}
      <div className="report-meta">
        <span>
          <MapPin size={13} />
          {number(job.lat ?? 0, 6)}° N, {number(job.lng ?? 0, 6)}° E
        </span>
        <span>Assessed {date(job.created_at)}</span>
        <StatusBadge status="done" />
      </div>
      <div className="kpi-grid report-kpis">
        <Kpi
          icon={Ruler}
          label="Usable rooftop"
          value={number(report.building.usable_area_m2, 1)}
          unit="m²"
          note={`Of ${number(report.building.roof_area_m2, 1)} m² detected roof`}
        />
        <Kpi
          icon={Zap}
          label="System capacity"
          value={number(report.system.kw_dc, 2)}
          unit="kW"
          note={`${report.system.panel_count} × ${number(report.system.panel_wp)} Wp panels`}
        />
        <Kpi
          icon={Sun}
          label="Annual clean energy"
          value={number(report.energy.annual_kwh)}
          unit="kWh"
          note={`${number(report.energy.specific_yield_kwh_per_kwp)} kWh per kWp`}
          tone="sunny"
        />
        <Kpi
          icon={Wallet}
          label="Annual savings"
          value={money(report.finance.annual_savings_inr)}
          note={`Simple payback: ${payback(report.finance.payback_years)}`}
        />
      </div>
      <div className="report-map-grid">
        <section className="card map-report-card">
          <div className="section-heading compact">
            <div>
              <h2>Meet your solar rooftop</h2>
              <p>Panels and annual shade, in the right place.</p>
            </div>
            {refresh && (
              <button className="text-button" onClick={refresh}>
                <RefreshCw size={14} /> Refresh map
              </button>
            )}
          </div>
          <MapView
            report={report}
            heatmapUrl={job.heatmap_png_url}
            sample={sample}
            segmentation={job.segmentation}
            imageUrl={job.image_png_url}
            imageBounds={job.image_bounds}
          />
          {!sample && !job.segmentation && (
            <p className="map-caption">
              Roof and obstacle outlines are not supplied by this API. The map
              shows report panels and shade.
            </p>
          )}
        </section>
        <aside className="roof-summary card">
          <div className="eyebrow">YOUR ROOF AT A GLANCE</div>
          <span className="roof-summary-sun">
            <Sun size={40} strokeWidth={1.2} />
          </span>
          <h2>
            {report.system.panel_count === 0
              ? "A roof to revisit."
              : "Space to make a difference."}
          </h2>
          <p>
            {report.system.panel_count === 0
              ? "No panels fit under the current space, setback, and shading assumptions."
              : "A panel layout shaped around the available rooftop space and modeled shade."}
          </p>
          <dl>
            <div>
              <dt>
                <Grid2X2 size={16} /> Panels
              </dt>
              <dd>{report.system.panel_count}</dd>
            </div>
            <div>
              <dt>
                <Sun size={16} /> Shade loss
              </dt>
              <dd>{number(report.energy.shade_loss_pct, 1)}%</dd>
            </div>
            <div>
              <dt>Tilt / azimuth</dt>
              <dd>
                {number(report.system.tilt_deg, 1)}° /{" "}
                {number(report.system.azimuth_deg, 1)}°
              </dd>
            </div>
            <div>
              <dt>
                <Leaf size={16} /> CO₂ avoided
              </dt>
              <dd>{number(report.co2_t_per_year, 2)} t / yr</dd>
            </div>
          </dl>
          <span className="estimated-pill">
            Modeled estimate · heights may be estimated
          </span>
        </aside>
      </div>
      <div className="report-bottom-grid">
        <section className="card energy-card">
          <div className="section-heading compact">
            <div>
              <span className="eyebrow">A YEAR OF SUNSHINE</span>
              <h2>Your energy, month by month</h2>
            </div>
            <span className="chart-unit">kWh / month</span>
          </div>
          <MonthlyChart values={report.energy.monthly_kwh} />
          <div className="energy-total">
            <span>Estimated annual generation</span>
            <strong>
              {number(report.energy.annual_kwh)} <small>kWh</small>
            </strong>
          </div>
        </section>
        <section className="card finance-card">
          <div className="eyebrow">THE FINANCIAL PICTURE</div>
          <h2>Sunshine that adds up.</h2>
          <dl>
            <div>
              <dt>Estimated installation</dt>
              <dd>{money(report.finance.capex_inr)}</dd>
            </div>
            <div className="subsidy-row">
              <dt>Modeled subsidy</dt>
              <dd>− {money(report.finance.subsidy_inr)}</dd>
            </div>
            <div className="net-cost">
              <dt>Estimated net cost</dt>
              <dd>{money(report.finance.net_cost_inr)}</dd>
            </div>
          </dl>
          <div className="payback-box">
            <span>Simple payback</span>
            <strong>{payback(report.finance.payback_years)}</strong>
            <p>
              {report.finance.payback_years === null
                ? "No finite payback under these assumptions."
                : "Estimated net cost ÷ annual savings"}
            </p>
          </div>
          <p className="finance-note">
            Costs, tariff, subsidy eligibility, and usage can change your
            outcome. See the assumptions below.
          </p>
        </section>
      </div>
      <AssumptionsPanel report={report} />
      <div className="report-cta">
        <div>
          <h3>One roof is just the beginning.</h3>
          <p>
            Explore another rooftop or save this estimate for a site survey.
          </p>
        </div>
        <Link className="button" to="/assess">
          Check another roof <ArrowUpRight size={17} />
        </Link>
      </div>
      <div className="print-footer">
        SolarRooftop AI · {sample ? "Sample fixture · " : ""}
        {job.job_id} · Satellite-based modeled estimate. Review assumptions
        before making installation decisions.
      </div>
    </div>
  );
}
export default function ReportPage() {
  const { id } = useParams();
  const query = useJob(id);
  if (query.isPending)
    return <Loading text="Finding your rooftop assessment…" />;
  if (query.error)
    return (
      <ErrorPanel error={query.error} retry={() => void query.refetch()} />
    );
  const job = query.data;
  if (job.status === "failed")
    return (
      <div className="failed-assessment">
        <PageHeading
          title="This roof needs another look."
          description="The assessment couldn’t finish at this location."
        />
        <ErrorPanel
          error={
            job.error ||
            "The assessment failed. Please choose a rooftop and try again."
          }
        />
        <Link to="/assess" className="button">
          Move the pin & try again <ArrowUpRight size={17} />
        </Link>
      </div>
    );
  if (job.status !== "done") return <Progress job={job} />;
  if (!job.report)
    return (
      <ErrorPanel
        error="The job is complete but its report is unavailable. Refresh to try again."
        retry={() => void query.refetch()}
      />
    );
  return (
    <ReportContent
      job={job}
      sample={config.useMocks}
      refresh={() => void query.refetch()}
    />
  );
}
export function SampleReport() {
  return <ReportContent job={sampleJob} sample />;
}
