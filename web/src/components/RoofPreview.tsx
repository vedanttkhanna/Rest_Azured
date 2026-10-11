import { ArrowUpRight, Check, MapPin } from "lucide-react";
import { Link } from "react-router-dom";
import { sampleLocation, sampleReport } from "../mocks/fixtures";

export function RoofPreview() {
  const [west, south, east, north] = sampleLocation.image_bounds;
  const project = (point: number[]) =>
    `${((point[0] - west) / (east - west)) * 512},${((north - point[1]) / (north - south)) * 512}`;
  return (
    <div className="roof-preview">
      <img
        src="/demo/rooftop.png"
        alt="Satellite image of the Mayur Vihar sample rooftop"
      />
      <div className="roof-preview-shade" />
      <svg
        viewBox="0 0 512 512"
        preserveAspectRatio="xMidYMid slice"
        aria-label="Example panel layout over the rooftop"
        className="preview-panels"
      >
        <polygon
          points={sampleLocation.footprint.coordinates[0]
            .map(project)
            .join(" ")}
          fill="rgba(245,207,87,.1)"
          stroke="#f5cf57"
          strokeWidth="2"
          strokeDasharray="5 3"
        />
        {sampleReport.panels.features.map((panel, index) => (
          <polygon
            key={index}
            points={panel.geometry.coordinates[0].map(project).join(" ")}
            fill="#416d91"
            stroke="#c4e7f8"
            strokeWidth=".8"
          />
        ))}
      </svg>
      <div className="preview-badge">
        <span className="live-dot" /> SATELLITE → SOLAR
      </div>
      <div className="preview-place">
        <MapPin size={14} /> Mayur Vihar, Delhi
      </div>
      <div className="roof-callout">
        <span className="callout-check">
          <Check size={15} />
        </span>
        <div>
          <strong>
            {sampleReport.system.panel_count} panels. One brighter roof.
          </strong>
          <span>Real model + simulated sample</span>
        </div>
      </div>
      <Link to="/sample" className="preview-link">
        Explore this rooftop <ArrowUpRight size={17} />
      </Link>
      <span className="preview-attribution">Imagery © Esri / Maxar</span>
    </div>
  );
}
