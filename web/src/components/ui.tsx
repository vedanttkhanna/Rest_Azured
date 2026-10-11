import {
  AlertCircle,
  ArrowRight,
  LoaderCircle,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import type { JobStatus } from "../api/types";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className="brand" aria-label="SolarRooftop AI home">
      <span className="brand-mark">
        <Sun size={24} strokeWidth={1.7} />
      </span>
      {!compact && (
        <span>
          SolarRooftop<span className="brand-ai">AI</span>
        </span>
      )}
    </Link>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}
export function Kpi({
  icon: Icon,
  label,
  value,
  unit,
  note,
  tone = "",
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  unit?: string;
  note?: string;
  tone?: string;
}) {
  return (
    <article className={`kpi ${tone}`}>
      <div className="kpi-top">
        <span>{label}</span>
        <Icon size={19} />
      </div>
      <div className="kpi-value">
        {value}
        <span>{unit}</span>
      </div>
      {note && <p>{note}</p>}
    </article>
  );
}
const labels: Record<JobStatus, string> = {
  queued: "Queued",
  fetching: "Fetching imagery",
  segmenting: "Detecting roof",
  simulating: "Simulating solar",
  done: "Ready",
  failed: "Failed",
};
export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span className={`status-badge ${status}`}>
      <i />
      {labels[status]}
    </span>
  );
}
export function ErrorPanel({
  error,
  retry,
}: {
  error: Error | string;
  retry?: () => void;
}) {
  return (
    <div className="error-panel" role="alert">
      <AlertCircle size={21} />
      <div>
        <strong>We couldn’t complete that request</strong>
        <p>{typeof error === "string" ? error : error.message}</p>
        {retry && (
          <button className="text-button" onClick={retry}>
            Try again <ArrowRight size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
export function Loading({
  text = "Loading your sunshine…",
}: {
  text?: string;
}) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={26} />
      <span>{text}</span>
    </div>
  );
}
export function Empty({
  icon: Icon = Sun,
  title,
  children,
}: {
  icon?: LucideIcon;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span>
        <Icon size={30} />
      </span>
      <h3>{title}</h3>
      {children}
    </div>
  );
}
