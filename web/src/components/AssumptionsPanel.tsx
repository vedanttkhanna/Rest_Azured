import { ChevronDown, Info } from "lucide-react";
import type { Report } from "../api/types";
import { displayValue, humanize } from "../lib/format";

export function AssumptionsPanel({ report }: { report: Report }) {
  const assumptions = report.assumptions as Record<string, unknown>;
  const sources = report.data_sources as Record<string, unknown>;
  const warnings = Array.isArray(assumptions.warnings)
    ? assumptions.warnings
    : assumptions.warnings
      ? [assumptions.warnings]
      : [];
  return (
    <section className="assumptions-section">
      <div className="transparency-header">
        <span className="icon-tile">
          <Info size={20} />
        </span>
        <div>
          <h2>A clear view of the estimate</h2>
          <p>Every assumption and data source, right here.</p>
        </div>
      </div>
      {warnings.length > 0 && (
        <div className="warning-list">
          <strong>Things to keep in mind</strong>
          <ul>
            {warnings.map((warning, index) => (
              <li key={index}>{displayValue(warning)}</li>
            ))}
          </ul>
        </div>
      )}
      <details className="assumptions-accordion">
        <summary>
          Model assumptions <ChevronDown size={17} />
        </summary>
        <dl className="assumptions-data">
          {Object.entries(assumptions)
            .filter(([key]) => key !== "warnings")
            .map(([key, value]) => (
              <div key={key}>
                <dt>{humanize(key)}</dt>
                <dd>
                  <pre>{displayValue(value)}</pre>
                </dd>
              </div>
            ))}
        </dl>
      </details>
      <details className="assumptions-accordion">
        <summary>
          Data sources & model <ChevronDown size={17} />
        </summary>
        <dl className="assumptions-data">
          {Object.entries(sources).map(([key, value]) => (
            <div key={key}>
              <dt>{humanize(key)}</dt>
              <dd>{displayValue(value)}</dd>
            </div>
          ))}
          <div>
            <dt>Model version</dt>
            <dd>{report.model_version}</dd>
          </div>
        </dl>
      </details>
    </section>
  );
}
