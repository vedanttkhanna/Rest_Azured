import {
  ArrowUpRight,
  FlaskConical,
  Home,
  LayoutGrid,
  LogOut,
  MapPin,
  Menu,
  Plus,
  Sun,
  X,
  BriefcaseBusiness,
  BookOpen,
} from "lucide-react";
import {
  NavLink,
  Outlet,
  Link,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "../auth/Auth";
import { Brand } from "./ui";

export function Layout() {
  const auth = useAuth();
  const [menu, setMenu] = useState(false);
  const [error, setError] = useState("");
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    setMenu(false);
    document.getElementById("main-content")?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [location.pathname]);
  const logout = async () => {
    try {
      await auth.logout();
      navigate("/");
    } catch {
      setError("Could not sign out. Please try again.");
    }
  };
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      {menu && (
        <button
          className="sidebar-scrim"
          onClick={() => setMenu(false)}
          aria-label="Close navigation"
        />
      )}
      <aside className={`sidebar ${menu ? "is-open" : ""}`}>
        <div className="sidebar-brand">
          <Brand />
          <button
            className="icon-button mobile-close"
            onClick={() => setMenu(false)}
            aria-label="Close navigation"
          >
            <X size={21} />
          </button>
        </div>
        <div className="workspace-label">YOUR SOLAR WORKSPACE</div>
        <nav aria-label="Main navigation">
          <NavLink to="/" end>
            <Home size={19} /> Overview
          </NavLink>
          <NavLink to="/assess">
            <MapPin size={19} /> Check a rooftop
          </NavLink>
          <NavLink to="/history">
            <LayoutGrid size={19} /> My assessments
          </NavLink>
          {auth.role === "Installer" && auth.signedIn && (
            <NavLink to="/installer">
              <BriefcaseBusiness size={19} /> Installer workspace
            </NavLink>
          )}
          <NavLink to="/about">
            <BookOpen size={19} /> How it works
          </NavLink>
        </nav>
        <div className="sidebar-sun-card">
          <Sun size={30} strokeWidth={1.4} />
          <h3>
            A brighter roof.
            <br />A lighter footprint.
          </h3>
          <p>
            Find the energy hiding
            <br />
            above your home.
          </p>
          <Link to="/assess">
            Let’s find out <ArrowUpRight size={17} />
          </Link>
          <div className="sun-card-orbit" />
        </div>
        <div className="sidebar-bottom">
          <span className="region-dot" /> Built for Delhi & NCR
          <span className="sidebar-version">SOLARROOFTOP AI · 2026</span>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMenu(true)}
              aria-label="Open navigation"
            >
              <Menu size={22} />
            </button>
            <span className="breadcrumb">Your rooftop. Your power.</span>
            <span className="topbar-location">
              <MapPin size={14} /> Delhi, India
            </span>
          </div>
          <div className="topbar-actions">
            {(auth.demo || auth.local) && (
              <span className="demo-badge">
                <FlaskConical size={13} /> {auth.local ? "Local model" : "Demo workspace"}
              </span>
            )}
            {auth.signedIn ? (
              <>
                <span className="role-badge">{auth.role}</span>
                <span className="avatar" title={auth.email}>
                  {auth.email.slice(0, 1).toUpperCase()}
                </span>
                {!auth.demo && !auth.local && (
                  <button
                    className="icon-button"
                    onClick={logout}
                    aria-label="Sign out"
                  >
                    <LogOut size={18} />
                  </button>
                )}
              </>
            ) : (
              <Link className="button small" to="/login">
                Sign in <ArrowUpRight size={15} />
              </Link>
            )}
          </div>
        </header>
        {(auth.demo || auth.local) && (
          <div className="demo-strip">
            <span>
              <FlaskConical size={14} /> {auth.local
                ? "Your trained model is connected. Select any rooftop in Delhi/NCR for a fresh assessment."
                : "Explore real project fixtures. New demo assessments reuse the Mayur Vihar sample."}
            </span>
            <label>
              {auth.local ? "Workspace" : "Try a role"}{" "}
              <select
                aria-label={auth.local ? "Local workspace role" : "Demo role"}
                value={auth.role}
                onChange={(event) =>
                  auth.setDemoRole(
                    event.target.value as "Homeowner" | "Installer",
                  )
                }
              >
                <option>Homeowner</option>
                <option>Installer</option>
              </select>
            </label>
          </div>
        )}
        {error && (
          <div role="alert" className="inline-error">
            {error}
          </div>
        )}
        <main id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
        <footer className="app-footer">
          <span>
            <Sun size={14} /> A little sunshine goes a long way.
          </span>
          <Link to="/about">
            Data, methods & assumptions <ArrowUpRight size={13} />
          </Link>
        </footer>
      </div>
      <Link
        to="/assess"
        className="mobile-assess"
        aria-label="New rooftop assessment"
      >
        <Plus size={23} />
      </Link>
    </div>
  );
}
