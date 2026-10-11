import {
  ArrowRight,
  ArrowUpRight,
  CircleCheck,
  Leaf,
  MapPin,
  ScanLine,
  Sun,
  Wallet,
  Zap,
} from "lucide-react";
import { Link } from "react-router-dom";
import { RoofPreview } from "../components/RoofPreview";
import { Kpi } from "../components/ui";
import { sampleReport } from "../mocks/fixtures";
import { money, number, payback } from "../lib/format";
import { useAuth } from "../auth/Auth";

export default function Overview() {
  const auth = useAuth();
  return (
    <div className="overview page-enter">
      <div className="overview-intro">
        <div>
          <div className="eyebrow">
            <Sun size={14} /> GOOD THINGS START WITH SUNSHINE
          </div>
          <h1>
            Make room for
            <br />
            <span>a brighter future.</span>
          </h1>
          <p>
            Your rooftop could power more than you think.
            <br />
            Discover its solar potential, one sunbeam at a time.
          </p>
        </div>
        <span className="intro-stamp">
          <Sun size={35} strokeWidth={1.2} />
          <span>
            SMALL CHANGE.
            <br />
            BRIGHT IMPACT.
          </span>
        </span>
      </div>
      <section className="hero-card">
        <div className="hero-copy">
          <span className="pill light">
            <span className="region-dot" /> MADE FOR DELHI ROOFTOPS
          </span>
          <h2>
            There’s a little
            <br />
            powerhouse
            <br />
            above your home<span>.</span>
          </h2>
          <p>
            Turn a satellite view into a clear picture of your roof’s panels,
            energy, and potential savings.
          </p>
          <Link className="button yellow" to="/assess">
            Check my rooftop <ArrowUpRight size={19} />
          </Link>
          <div className="hero-note">
            <CircleCheck size={14} /> No site visit to get started
          </div>
          <div className="hero-orbit" />
        </div>
        <RoofPreview />
      </section>
      <div className="section-heading">
        <div>
          <span className="eyebrow">A GLIMPSE OF WHAT’S POSSIBLE</span>
          <h2>One rooftop. Real potential.</h2>
        </div>
        <Link to="/sample">
          View sample report <ArrowRight size={16} />
        </Link>
      </div>
      <div className="sample-caption">
        <span className="sample-tag">EXAMPLE</span> Mayur Vihar fixture ·
        simulated results for this building, not your roof
      </div>
      <div className="kpi-grid overview-kpis">
        <Kpi
          icon={Zap}
          label="Clean energy / year"
          value={number(sampleReport.energy.annual_kwh)}
          unit="kWh"
          note={`${number(sampleReport.system.kw_dc, 1)} kW rooftop system`}
        />
        <Kpi
          icon={Wallet}
          label="Potential annual savings"
          value={money(sampleReport.finance.annual_savings_inr)}
          note="Using the sample tariff assumption"
          tone="sunny"
        />
        <Kpi
          icon={Sun}
          label="Simple payback"
          value={payback(sampleReport.finance.payback_years)}
          note="After the modeled subsidy"
        />
        <Kpi
          icon={Leaf}
          label="CO₂ avoided / year"
          value={number(sampleReport.co2_t_per_year, 1)}
          unit="tonnes"
          note="Using the sample grid factor"
        />
      </div>
      <section className="how-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">
              FROM ABOVE YOUR HOME TO INSIDE YOUR PLAN
            </span>
            <h2>Less guesswork. More sunshine.</h2>
          </div>
          <Link to="/about">
            See how it works <ArrowRight size={16} />
          </Link>
        </div>
        <div className="how-grid">
          <article>
            <span className="step-number">01</span>
            <div className="how-icon">
              <MapPin size={24} />
            </div>
            <h3>Find your rooftop</h3>
            <p>
              Enter an address or place a pin on your building. We focus on
              Delhi & NCR.
            </p>
          </article>
          <article>
            <span className="step-number">02</span>
            <div className="how-icon">
              <ScanLine size={24} />
            </div>
            <h3>Let the sun do the math</h3>
            <p>
              Our model finds the roof. Solar simulation considers space,
              obstacles, and shade.
            </p>
          </article>
          <article>
            <span className="step-number">03</span>
            <div className="how-icon">
              <Zap size={24} />
            </div>
            <h3>See your brighter picture</h3>
            <p>
              Explore a panel layout, monthly energy, estimated savings, and
              payback.
            </p>
          </article>
        </div>
      </section>
      <section className="installer-banner">
        <div className="installer-icon">
          <Sun size={27} />
        </div>
        <div>
          <h3>More rooftops on your list?</h3>
          <p>
            Installer accounts can assess up to 25 locations together and export
            their results.
          </p>
        </div>
        <Link
          className="button secondary"
          to={
            auth.role === "Installer" && auth.signedIn ? "/installer" : "/about"
          }
        >
          {auth.role === "Installer" && auth.signedIn
            ? "Open workspace"
            : "For installers"}
          <ArrowUpRight size={17} />
        </Link>
      </section>
    </div>
  );
}
