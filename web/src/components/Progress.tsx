import { useEffect, useState } from "react";
import {
  ArrowRight,
  Check,
  CircleDashed,
  LoaderCircle,
  MapPin,
  ScanLine,
  Sun,
  Zap,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { Job } from "../api/types";
import { StatusBadge } from "./ui";

const steps = [
  {
    status: "queued",
    title: "Getting things ready",
    text: "Your assessment is in the queue.",
    icon: CircleDashed,
  },
  {
    status: "fetching",
    title: "Finding your rooftop",
    text: "Fetching satellite imagery and building context.",
    icon: MapPin,
  },
  {
    status: "segmenting",
    title: "Making sense of the space",
    text: "Detecting the roof and visible obstacles.",
    icon: ScanLine,
  },
  {
    status: "simulating",
    title: "Following the sunshine",
    text: "Modeling shade, panels, energy, and savings.",
    icon: Sun,
  },
];
export function Progress({ job }: { job: Job }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const elapsed = Math.max(
    0,
    Math.floor((now - new Date(job.created_at || now).getTime()) / 1000),
  );
  const current = steps.findIndex((step) => step.status === job.status);
  return (
    <div className="progress-page page-enter">
      <div className="solar-loader">
        <Sun size={52} strokeWidth={1.2} />
        <span />
        <span />
      </div>
      <div className="eyebrow">A BRIGHTER PICTURE IS ON ITS WAY</div>
      <h1>
        Your roof meets
        <br />a year of sunshine.
      </h1>
      <p className="progress-address">
        <MapPin size={15} />
        {job.address || "Selected rooftop"}
      </p>
      <StatusBadge status={job.status} />
      <div className="progress-steps" aria-live="polite">
        {steps.map((step, index) => (
          <div
            key={step.status}
            className={`progress-step ${index < current ? "complete" : index === current ? "current" : ""}`}
          >
            <div className="progress-step-icon">
              {index < current ? (
                <Check size={20} />
              ) : index === current ? (
                <LoaderCircle size={21} className="spin" />
              ) : (
                <step.icon size={20} />
              )}
            </div>
            <div>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </div>
          </div>
        ))}
      </div>
      <p className="progress-timing">
        {elapsed > 60
          ? "The system may be warming up. Your assessment is still running; you can come back from My assessments."
          : "Most warm assessments finish in 15–25 seconds. Cold starts can take around 2 minutes."}
      </p>
      <span className="elapsed">
        {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}{" "}
        elapsed · updates every 3 seconds
      </span>
      <Link to="/history" className="text-button">
        You can safely leave this page <ArrowRight size={15} />
      </Link>
      <div className="progress-footnote">
        <Zap size={16} /> We’ll save your report in My assessments.
      </div>
    </div>
  );
}
