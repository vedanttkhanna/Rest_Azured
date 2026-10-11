import {
  ArrowUpRight,
  CloudSun,
  Cpu,
  MapPin,
  ScanLine,
  Sun,
  Zap,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeading } from "../components/ui";

export default function About() {
  return (
    <div className="about-page page-enter">
      <PageHeading
        eyebrow="A LITTLE SCIENCE BEHIND THE SUNSHINE"
        title="From satellite pixels to solar possibility."
        description="An assessment built around Delhi’s rooftops, with the assumptions out in the open."
      />
      <section className="about-hero">
        <div>
          <Sun size={45} strokeWidth={1.3} />
          <h2>
            Know your roof.
            <br />
            Plan your next step.
          </h2>
          <p>
            SolarRooftop AI brings imagery, roof detection, and solar simulation
            into one report. It’s an early planning tool for homeowners and
            installers.
          </p>
          <Link to="/assess" className="button yellow">
            Explore your rooftop <ArrowUpRight size={18} />
          </Link>
        </div>
        <div className="method-flow">
          {[
            {
              icon: MapPin,
              title: "Find the building",
              text: "Esri imagery and building footprints",
            },
            {
              icon: ScanLine,
              title: "Understand the roof",
              text: "SegFormer-B2 roof and obstacle segmentation",
            },
            {
              icon: CloudSun,
              title: "Model a year of sun",
              text: "Shade geometry, PVGIS weather, and pvlib",
            },
            {
              icon: Zap,
              title: "Make it useful",
              text: "Panel layout, energy, savings, and payback",
            },
          ].map((step, index) => (
            <div key={step.title}>
              <span>
                <step.icon size={21} />
              </span>
              <div>
                <small>0{index + 1}</small>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
      <div className="about-cards">
        <section className="card">
          <Cpu size={24} />
          <h2>What the model knows</h2>
          <p>
            The roof model starts with RID aerial imagery, then adapts to Delhi
            using footprint labels. Delhi roof IoU is about 0.55 against those
            footprints.
          </p>
          <p>
            That score measures footprint agreement. We do not have
            independently surveyed accuracy. Small obstacles can be missed;
            tanks and stair rooms are currently grouped as “other”.
          </p>
        </section>
        <section className="card">
          <Sun size={25} />
          <h2>What the simulation assumes</h2>
          <p>
            The solar engine uses PVGIS typical-year weather, local shade,
            rooftop setbacks, panel spacing, and chosen orientation.
          </p>
          <p>
            Heights may be estimated. Tariff, installation cost, subsidy, and
            grid emissions are configurable assumptions shown in each report.
          </p>
        </section>
        <section className="card">
          <ShieldCheck size={24} />
          <h2>Built on AWS</h2>
          <p>
            Amazon Cognito secures sign-in. API Gateway and Cedar enforce
            access. Step Functions coordinates imagery, SageMaker inference, and
            Lambda simulation.
          </p>
          <p>
            Private S3 files are accessed through expiring links. An assessment
            belongs to its account; sharing a URL doesn’t make it public.
          </p>
        </section>
      </div>
      <section className="card about-limitations">
        <h2>Clarity is part of the report.</h2>
        <p>
          Available satellite imagery is roughly 0.26 m per source pixel.
          Upsampling adds pixels, not physical detail. Some rooftops lack
          reliable footprints, and neighboring building heights may be
          incomplete. Review the warnings and confirm structural suitability
          with a site survey before installation.
        </p>
        <div className="sources-row">
          <span>Esri World Imagery</span>
          <span>Overture Maps</span>
          <span>EU JRC PVGIS</span>
          <span>pvlib</span>
          <span>RID · TU Munich</span>
        </div>
      </section>
    </div>
  );
}
